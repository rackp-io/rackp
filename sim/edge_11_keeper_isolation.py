# edge_11_keeper_isolation.py
# A single Keeper may legitimately serve multiple terminals of ONE operator. This is
# NOT the cross-party concentration anti-pattern (RFC-0002 §2.5) — that is using one
# Keeper for all PARTIES of an incident. A Keeper that holds several terminals' records
# MUST scope every response to the requested terminal. Because every other scenario now
# uses one Keeper per party, none exercises this; edge_11 pins it directly:
#   1. ANCHOR_CHAIN_QUERY for T1 returns only T1's anchors (T2's never leak) — and only
#      to an AUTHORIZED requester (RFC-0001 §6.27): the Referee bound to the incident
#      (G1 binding) or the target terminal itself. An unregistered probe gets
#      UNKNOWN_TERMINAL; a registered co-tenant spying on its neighbour gets
#      PROTOCOL_REJECTED; a self-query needs no binding at all.
#   2. VERIFICATION_QUERY for T1 must NOT match a hash anchored by T2 (a party cannot
#      claim another terminal's anchored work as its own evidence).
#   3. REFEREE_STATS_QUERY for one Referee returns only that Referee's stats.
import uuid
from datetime import datetime, timezone
from classes.World import World
from classes.Agent import Agent
from classes.Actor import Actor
from classes.Referee import Referee
from classes.Keeper import Keeper

WIDE_RANGE = {"start": "2000-01-01T00:00:00Z", "end": "2099-12-31T23:59:59Z"}


def run():
    world = World()
    K  = Keeper("K")                  # one Keeper, shared by two terminals of one operator
    T1 = Actor("T1", keeper_name="K")
    T2 = Actor("T2", keeper_name="K")
    R  = Referee("R", keeper_name="K")
    PROBE = Agent("PROBE")            # neutral test observer; ignores all inbound messages
    for ag in [K, T1, T2, R, PROBE]:
        world.register(ag)

    # Observation goes through the harness recorder (world.last / world.all_of) — no
    # test-only state is added to any agent for this.

    print("=== Scenario edge_11: single-Keeper terminal isolation ===")
    INC = "000000eb-0000-4000-8000-0000000000eb"

    # T1 anchors 2 records, T2 anchors 3 — all to the same Keeper K.
    T1.act("draft", {"n": 1}); T1.act("draft", {"n": 2})
    T2.act("draft", {"n": 1}); T2.act("draft", {"n": 2}); T2.act("draft", {"n": 3})

    # The chain query is gated (§6.27): register R's key at K (profile publication) and
    # bind INC to R via a signed INCIDENT_OPEN — the same G1 binding that gates
    # INCIDENT_NOTICE / FEE_CLAIM authorizes ledger disclosure.
    R.publish_profile()
    world.send("R", "K", {
        "type": "INCIDENT_NOTICE", "incident_id": INC, "referee_id": R.terminal_id,
        "recipient_id": K.terminal_id, "event_type": "INCIDENT_OPEN",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "signature": f"SIG_{R.terminal_id}",
    })

    # (1) Anchor-chain isolation, queried by the bound Referee.
    print("\n--- anchor-chain query scoping ---")
    R.verify_claim_chain("T1", incident_id=INC, keeper_name="K")
    R.verify_claim_chain("T2", incident_id=INC, keeper_name="K")
    chains = {m["target_terminal_id"]: m for m in world.all_of("R", "ANCHOR_CHAIN_RESULT")}
    t1, t2 = chains[T1.terminal_id], chains[T2.terminal_id]
    assert t1["count"] == 2, f"T1 must see only its 2 anchors, got {t1['count']}"
    assert t2["count"] == 3, f"T2 must see only its 3 anchors, got {t2['count']}"
    assert all(a["terminal_id"] == T1.terminal_id for a in t1["anchors"]), "T2 anchors leaked into T1's chain"
    assert all(a["terminal_id"] == T2.terminal_id for a in t2["anchors"]), "T1 anchors leaked into T2's chain"

    # (1b) Authorization boundary (§6.27). A chain query is not public data:
    #   - PROBE never registered a key at K -> UNKNOWN_TERMINAL, no ledger.
    #   - T2 is registered (its anchors) but is neither the bound Referee nor the
    #     target -> PROTOCOL_REJECTED: co-tenancy at a Keeper grants no read right
    #     on the neighbour's chain.
    #   - T1 reading its OWN chain needs no incident binding (self-query).
    print("\n--- anchor-chain query authorization ---")
    def chain_query(requester_tid, target_tid):
        return {
            "type": "ANCHOR_CHAIN_QUERY", "incident_id": INC,
            "requester_id": requester_tid, "target_terminal_id": target_tid,
            "range": {"start": "2000-01-01T00:00:00Z", "end": "2099-12-31T23:59:59Z"},
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "signature": f"SIG_{requester_tid}",
        }
    world.send("PROBE", "K", chain_query(PROBE.terminal_id, T1.terminal_id))
    rej = world.last("PROBE", "DELIVERY_REJECTION")
    assert rej and rej["reason"] == "UNKNOWN_TERMINAL", f"unregistered probe must get UNKNOWN_TERMINAL, got {rej}"
    assert not world.all_of("PROBE", "ANCHOR_CHAIN_RESULT"), "no ledger may reach an unregistered requester"

    world.send("T2", "K", chain_query(T2.terminal_id, T1.terminal_id))
    rej = world.last("T2", "DELIVERY_REJECTION")
    assert rej and rej["reason"] == "PROTOCOL_REJECTED", f"unbound co-tenant must get PROTOCOL_REJECTED, got {rej}"
    assert not world.all_of("T2", "ANCHOR_CHAIN_RESULT"), "no ledger may reach an unbound requester"

    world.send("T1", "K", chain_query(T1.terminal_id, T1.terminal_id))
    own = world.last("T1", "ANCHOR_CHAIN_RESULT")
    assert own and own["count"] == 2, f"self-query must return T1's own 2 anchors, got {own}"

    # (2) Verification scoping: T1 must not be able to claim T2's anchored hash.
    print("\n--- verification cross-terminal scoping ---")
    t2_hash = T2._last_claim.hash    # a hash that exists in K, but belongs to T2
    t1_hash = T1._last_claim.hash    # T1's own hash
    world.send("PROBE", "K", {
        "type": "VERIFICATION_QUERY",
        "incident_id": INC,
        "requester_id": R.terminal_id,
        "target_terminal_id": T1.terminal_id,
        "target_hashes": [t2_hash, t1_hash],
        "original_timestamp_range": WIDE_RANGE,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    vres = world.last("PROBE", "VERIFICATION_RESULT")
    matched = {r["target_hash"]: r["matched"] for r in vres["results"]}
    assert matched[t2_hash] is False, "T1 must NOT verify a hash anchored by T2 (work theft)"
    assert matched[t1_hash] is True, "T1's own anchored hash must verify"

    # (3) Stats isolation: two Referees' assessment anchors on the same Keeper.
    print("\n--- referee-stats query scoping ---")
    ref1, ref2 = str(uuid.uuid4()), str(uuid.uuid4())
    def assessment_anchor(tid, seq):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        msg = {
            "type": "CLAIM_ANCHOR", "terminal_id": tid, "claim_id": str(uuid.uuid4()),
            "sequence_number": seq, "timestamp": now, "data_hash": "a" * 64,
            "signature": f"SIG_{tid}_{seq}", "action_type": "ASSESSMENT_ISSUED",
        }
        if seq == 1:  # schema: the first anchor registers the terminal's public key
            msg["public_key"] = f"PUBKEY_{tid}"
        return msg
    world.send("PROBE", "K", assessment_anchor(ref1, 1))
    world.send("PROBE", "K", assessment_anchor(ref1, 2))   # ref1: 2 assessments
    world.send("PROBE", "K", assessment_anchor(ref2, 1))   # ref2: 1 assessment

    for ref in (ref1, ref2):
        world.send("PROBE", "K", {
            "type": "REFEREE_STATS_QUERY", "terminal_id": ref,
            "requester_id": R.terminal_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    stats = {m["terminal_id"]: m for m in world.all_of("PROBE", "REFEREE_STATS_RESULT")}
    assert stats[ref1]["found"] and stats[ref1]["assessment_count"] == 2, \
        f"ref1 must report only its own 2 assessments, got {stats[ref1].get('assessment_count')}"
    assert stats[ref2]["found"] and stats[ref2]["assessment_count"] == 1, \
        f"ref2 must report only its own 1 assessment, got {stats[ref2].get('assessment_count')}"

    print("\n[OK] anchor chains, verification, and stats are each scoped to the queried"
          " terminal on a shared Keeper; no cross-terminal leakage or work theft. Chain"
          " disclosure is gated (bound Referee or self-query only): unregistered probe ->"
          " UNKNOWN_TERMINAL, unbound co-tenant -> PROTOCOL_REJECTED.")


if __name__ == "__main__":
    run()
