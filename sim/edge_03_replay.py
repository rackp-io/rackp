# edge_03_replay.py
# RFC Section 5 (Phase 1-4) + RFC-0002 §2.2 (Replay Attacks): a full, base_01-conformant assessment in which
# the Actor mounts a REPLAY attack. Before the incident, the Actor legitimately anchors a
# routine action (an hour ago). When the incident happens it anchors its REAL action too,
# but at evidence time it conceals that and instead replays the older, genuine anchor —
# betting that a real, Keeper-verifiable hash will pass.
#
# How the replay is handled (RFC §6.13, RFC-0002 §2.2):
#   - The replayed anchor is genuine, so it is NOT caught as a forgery (no hash mismatch,
#     no NOT_FOUND — that is the liar's failure mode in edge_01). Its hash really is in
#     the Keeper.
#   - It is caught by the evidence WINDOW instead: the Referee's VERIFICATION_QUERY carries
#     the incident's target_period, and the stale anchor's timestamp falls outside it, so
#     the Keeper rejects it as TIMESTAMP_OUT_OF_RANGE → the Actor's evidence FAILS.
#   - FAILED(actor)/VERIFIED(claimant) → actor_fault=0.8, claimant_fault=0.2, MEDIUM (§7).
#   - The Actor DID anchor its real incident action; that record sits in the Keeper too —
#     so continuous anchoring means concealment by replay simply surfaces a stale record
#     while the truth remains on the chain.
from classes.topology import standard_world
from scenario_actor.ReplayActor import ReplayActor
from datetime import datetime, timezone, timedelta

def run():
    # Same canonical topology as base_01 (Kr/Kc/Ka), but A is a ReplayActor.
    world, R, A, C, Kr, Kc, Ka = standard_world(ReplayActor)

    print("=== Scenario edge-03: Replay attack over the full base flow ===")
    INC_E03 = "0000e03a-0000-4000-8000-00000000e03a"
    now = datetime.now(timezone.utc)
    old_timestamp = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Phase 1: Norm declaration + anchoring.
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    # An hour ago: a routine, legitimately anchored action. The Actor remembers it to
    # replay later as a stale-but-genuine record.
    A.act("patrol", {"x": 0, "y": 0}, timestamp=old_timestamp)
    A.remember_as_old()
    # Now: the incident. The Actor anchors its REAL action (which it will conceal) and the
    # Claimant anchors its own.
    A.act("collision", {"x": 5, "y": 3})
    C.act("move", {"x": 5, "y": 3})

    # Phase 2: filing + fee deposit (the replay Actor participates normally otherwise).
    C.deposit_fee(INC_E03, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E03)
    R.notify_actor("A", incident_id=INC_E03)
    R.notify_actor_named("A", incident_id=INC_E03)
    A.acknowledge(INC_E03)
    R.notify_actor_keeper_open(INC_E03)
    A.deposit_fee(INC_E03, amount=100, currency="USD")

    # Phase 3: evidence collection. request_evidence stamps the incident's target_period
    # (last 10 minutes); the Actor replays the 1-hour-old anchor, which is outside it.
    R.request_evidence("A", incident_id=INC_E03)
    A.submit_evidence(INC_E03)   # ReplayActor: stale anchor → TIMESTAMP_OUT_OF_RANGE
    R.request_evidence("C", incident_id=INC_E03)
    C.submit_evidence(INC_E03)
    R.verify_claim_chain("A", incident_id=INC_E03, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E03, keeper_name="Kc")

    # Phase 4: assessment + settlement (identical orchestration to base_01).
    R.query_fee_status(INC_E03)
    R.issue_contribution_result(INC_E03)
    R.notify_assessment_complete(INC_E03)
    Kc.release_fee(INC_E03)
    Ka.release_fee(INC_E03)
    R.send_fee_receipt(INC_E03)

    # --- assertions: a genuine-but-stale anchor is rejected by the evidence window ---
    print("\n--- assertions ---")
    # The replayed anchor is REAL: its hash is stored in the Actor's Keeper (not a forgery).
    replay_hash    = A._replay_claim.hash
    ka_hashes      = {a["data_hash"] for a in Ka.anchors.values()}
    assert replay_hash in ka_hashes, "the replayed anchor must genuinely exist in the Keeper"
    # The Actor really did submit that stale hash as its evidence.
    a_sub = next(m for m in world.all_of("R", "EVIDENCE_SUBMISSION") if m["submitter_id"] == A.terminal_id)
    assert a_sub["verification_info"]["stored_hash"] == replay_hash, "the Actor must replay the old anchor's hash"
    # The stale anchor's timestamp lies BEFORE the incident's evidence window — the reason
    # it is rejected (this is the replay's only flaw; the hash itself is valid).
    window_start = R._incidents[INC_E03]["target_period"]["start"]
    assert A._replay_claim.timestamp < window_start, \
        f"the replayed anchor must predate the evidence window ({A._replay_claim.timestamp} !< {window_start})"

    # Despite the hash EXISTING in the Keeper, the Actor's evidence FAILS — rejected by the
    # timestamp window, not by absence. This is the distinction from edge_01 (forgery →
    # NOT_FOUND): here the record is real but out of scope.
    results = R._incidents[INC_E03]["results"]
    assert results[A.terminal_id] is False, "a stale anchor must FAIL the evidence-window check"
    assert results[C.terminal_id] is True,  "the honest party must verify"

    # Continuous anchoring: the Actor's REAL incident action is on the chain too, yet it
    # chose to replay the stale one instead — the truth it concealed is still in the Keeper.
    collision_hash = A._last_claim.hash
    assert collision_hash in ka_hashes, "the concealed real action is nonetheless anchored"
    assert collision_hash != replay_hash, "the Actor submitted the stale anchor, not the real one"

    # One assessment, delivered identically to both parties (RFC §6.14).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), "both parties must receive the same cert_id"

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # FAILED(actor)/VERIFIED(claimant) → 0.8/0.2, MEDIUM; shares sum to 1.0 (RFC §7).
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.8, 0.2, 0.0), f"got {fault}"
    assert fault["confidence"] == "MEDIUM"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0
    # The replay is a genuine anchor (computed hash == stored hash), so there is NO hash
    # discrepancy — it is caught by the window, not flagged as a technical_violation.
    assert verdict["technical_violation"] == [], f"a genuine replay is not a hash discrepancy, got {verdict['technical_violation']}"
    ep = result["evidence_provenance"]
    assert "FAILED" in ep and "VERIFIED" in ep, f"one FAILED, one VERIFIED, got {ep}"

    # Coverage ≠ verification: the Actor genuinely has a chain (SESSION_START + patrol +
    # collision → MEDIUM), so the assessment is DEFINITIVE even though its submitted
    # evidence was rejected.
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "DEFINITIVE", f"intact chains -> DEFINITIVE, got {es['assessment_status']}"
    assert es["actor_coverage"] == "MEDIUM" and es["claimant_coverage"] == "MEDIUM", \
        f"got {es['actor_coverage']}/{es['claimant_coverage']}"
    assert es["gaps"] == [], f"the Actor's chain itself has no gaps, got {es['gaps']}"

    # The replay is a disclosure trick, not a funding default: the Actor still deposited,
    # so fee_compliance shows DEPOSITED and fees settle exactly as in base_01 (STD-026/029).
    fc = verdict["fee_compliance"]
    assert fc["actor_fee_status"] == "DEPOSITED" and fc["claimant_fee_status"] == "DEPOSITED", f"got {fc}"
    per_keeper = R._received_fees[INC_E03]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, f"got {per_keeper}"
    assert sum(per_keeper.values()) == 200, "released total must equal total deposited"
    assert Kc._escrow[INC_E03]["state"] == "SETTLED" and Ka._escrow[INC_E03]["state"] == "SETTLED"

    print("[OK] full base flow with a replay attack: Actor replayed a genuine 1-hour-old"
          " anchor (hash present in Keeper) -> rejected as out-of-window -> A FAILED /"
          " C VERIFIED -> 0.8/0.2/MEDIUM (sum 1.0); no technical_violation (real anchor, not"
          " a forgery); the concealed real action is still on the chain; chain intact"
          " (DEFINITIVE/MEDIUM); fee disclosed DEPOSITED; 200 released; escrows SETTLED.")

if __name__ == "__main__":
    run()
