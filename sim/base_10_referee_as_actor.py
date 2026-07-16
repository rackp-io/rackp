# base_10_referee_as_actor.py
# R1 (a Referee) previously issued an assessment for INC_A.
# C disputes R1's judgment and files INC_010 against R1 with R2 as the new Referee.
# R1 submits its own action anchors as evidence and is assessed like any Actor.
# R2's Keeper (K2) tracks R1's named_as_actor_count via REFEREE_STATS_QUERY.
# §4.1 (Referee anchors all actions; MAY be named as Actor and assessed by another Referee), §6.21 (named_as_actor_count stat)
# Custom topology (not the standard helper): two Referees plus an Actor and Claimant,
# each with its own Keeper. R1's "named_as_actor" stat is anchored by R2 to R2's Keeper.
from classes.World import World
from classes.Actor import Actor
from classes.Claimant import Claimant
from classes.Referee import Referee
from classes.Keeper import Keeper
from scenario_actor.RefActor import RefActor
from datetime import datetime, timezone

def run():
    world = World()
    R1 = RefActor("R1", keeper_name="K1")   # Referee-under-scrutiny (acts as Actor in INC_010)
    R2 = Referee("R2",  keeper_name="K2")   # Assessing Referee
    A  = Actor("A",     keeper_name="Ka")
    C  = Claimant("C",  keeper_name="Kc")
    K1 = Keeper("K1"); K2 = Keeper("K2"); Ka = Keeper("Ka"); Kc = Keeper("Kc")
    for ag in [R1, R2, A, C, K1, K2, Ka, Kc]:
        world.register(ag)

    print("=== Scenario 10: Referee assessed as Actor ===")

    # --- Phase 1: R1 does a normal assessment for INC_A ---
    INC_A   = "0000001a-0000-4000-8000-00000000001a"
    INC_010 = "00000010-0000-4000-8000-000000000010"

    print("\n--- Phase 1: R1 conducts INC_A assessment ---")
    A.act("drive", {"speed_kmh": 60, "road": "highway"})
    C.act("drive", {"speed_kmh": 60, "road": "highway"})

    R1.request_evidence("A", incident_id=INC_A)
    R1.request_evidence("C", incident_id=INC_A)
    R1.finalize_incident(INC_A)
    # R1 now has an ASSESSMENT_ISSUED anchor in its own Keeper K1 (stored as _last_anchor_info)

    # --- Phase 2: C disputes R1's judgment, files INC_010 against R1 with R2 ---
    print("\n--- Phase 2: C files INC_010 against R1 (R2 is the new Referee) ---")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # C deposits escrow; R1 also deposits (as respondent, using direct send)
    C.deposit_fee(INC_010, 100, "USD")
    world.send("R1", "K1", {
        "type":         "FEE_DEPOSIT",
        "incident_id":  INC_010,
        "depositor_id": R1.terminal_id,
        "amount":       100,
        "currency":     "USD",
        "timestamp":    now_str,
        "signature":    f"SIG_{R1.terminal_id}"
    })

    C.act("file_complaint", {"against": "R1", "incident_ref": INC_A, "grounds": "biased_assessment"})

    # R2 notifies Keeper that R1 has been named as Actor (for stats tracking)
    R2.notify_actor_named("R1", INC_010)

    # R2 requests evidence from R1 (as Actor) and C (as Claimant). R1 (a RefActor)
    # auto-submits its last anchor; C must submit explicitly — and does, so both sides
    # are genuinely verified rather than relying on a default.
    R2.request_evidence("R1", incident_id=INC_010)
    R2.request_evidence("C",  incident_id=INC_010)
    C.submit_evidence(INC_010)

    # R2 queries anchor chains for evidence sufficiency (each party's own Keeper)
    R2.verify_claim_chain("R1", incident_id=INC_010, keeper_name="K1")
    R2.verify_claim_chain("C",  incident_id=INC_010, keeper_name="Kc")

    R2.finalize_incident(INC_010)

    # --- Phase 3: Query Keeper for R1's reputation stats ---
    print("\n--- Phase 3: Querying Keeper for R1 stats ---")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats_query = {
        "type":         "REFEREE_STATS_QUERY",
        "terminal_id":  R1.terminal_id,
        "requester_id": C.terminal_id,
        "timestamp":    now
    }
    # R1's named_as_actor anchor was written by R2 to R2's Keeper (K2), so query there.
    world.send("C", "K2", stats_query)

    # --- assertions: a Referee can be named and assessed as an Actor (RFC §4.1; stats via §6.21) ---
    print("\n--- assertions ---")

    # 1) R1 was assessed exactly like any Actor: it received a CONTRIBUTION_RESULT for
    #    INC_010 in which it occupies the actor slot. Both R1 (its anchored action) and C
    #    (its complaint anchor) submitted and genuinely verified → VERIFIED/VERIFIED
    #    0.5/0.5/HIGH (RFC §7).
    verdict_msg = world.last("R1", "CONTRIBUTION_RESULT")
    assert verdict_msg is not None and verdict_msg["incident_id"] == INC_010, \
        "R1 must receive a CONTRIBUTION_RESULT as the assessed Actor"
    # Same single verdict reaches the Claimant too.
    assert world.last("C", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"] \
        == verdict_msg["assessment"]["certification"]["cert_id"], "both parties share one cert_id"
    fault = verdict_msg["assessment"]["fault"]
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.5, 0.5, 0.0), f"got {fault}"
    assert fault["confidence"] == "HIGH"
    assert round(sum((fault["actor_fault"], fault["claimant_fault"], fault["external_factor"])), 10) == 1.0
    ep = verdict_msg["evidence_provenance"]
    assert "VERIFIED" in ep and "FAILED" not in ep, f"both parties verified, got {ep}"

    # 2) The "named as Actor" event is recorded on R2's Keeper (K2) — where R2 anchored
    #    it — and is keyed to R1's terminal, returning named_as_actor_count == 1.
    stats = world.last("C", "REFEREE_STATS_RESULT")
    assert stats is not None and stats["found"] is True, "R1 stats must be found on K2"
    assert stats["terminal_id"] == R1.terminal_id
    assert stats["named_as_actor_count"] == 1, f"R1 named as Actor once, got {stats['named_as_actor_count']}"

    # 3) Reputation is custody-local: K2 saw R1 only as a named Actor, NOT its prior
    #    assessment history (INC_A) — that lives on R1's own Keeper, K1. The split is the
    #    point: a Referee's track record does not aggregate across independent Keepers.
    assert stats["assessment_count"] == 0, \
        f"K2 holds no assessment history for R1, got {stats['assessment_count']}"
    assert K1._j_stats[R1.terminal_id]["assessment_count"] == 1, \
        "R1's INC_A assessment is recorded on its own Keeper K1"

    print("[OK] R1 assessed as Actor (0.5/0.5/HIGH, both verified); named_as_actor_count=1 on K2;"
          " assessment history isolated to K1 (per-Keeper reputation).")

if __name__ == "__main__":
    run()
