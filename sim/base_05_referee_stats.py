# base_05_referee_stats.py
# Referee anchors ASSESSMENT_ISSUED/APPEAL_RECEIVED/APPEAL_REJECTED actions to Keeper.
# Keeper responds to REFEREE_STATS_QUERY.
# Expected: assessment_count=2, appeal_count=1, appeal_rejected_count=1, anchor_continuity=True
# RFC Section 5 (Phase 1–4): full honest-actor flow × 2; Referee self-anchors all protocol actions to Keeper
# §4.1: a Referee's action history is queryable by anyone via REFEREE_STATS_QUERY (§6.20/§6.21) — the transparency/disclosure obligation
from classes.topology import standard_world
from datetime import datetime, timezone

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario 05: Referee stats tracking ===")

    INC_005a = "00000005-000a-4000-8000-00000000005a"
    INC_005b = "00000005-000b-4000-8000-00000000005b"

    # Phase 1: Norm declaration (once per session)
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])

    # case 1: standard assessment
    print("\n--- incident INC-005a ---")
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + fee deposit
    C.deposit_fee(INC_005a, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_005a)
    R.notify_actor("A", incident_id=INC_005a)
    R.notify_actor_named("A", incident_id=INC_005a)
    A.acknowledge(INC_005a)
    R.notify_actor_keeper_open(INC_005a)
    A.deposit_fee(INC_005a, amount=100, currency="USD")

    # Phase 3: evidence collection
    R.request_evidence("A", incident_id=INC_005a)
    A.submit_evidence(INC_005a)
    R.request_evidence("C", incident_id=INC_005a)
    C.submit_evidence(INC_005a)

    # Phase 4: assessment — VERIFIED/VERIFIED → actor_fault=0.5, claimant_fault=0.5, confidence=HIGH
    R.finalize_incident(INC_005a)
    R.send_fee_receipt(INC_005a)

    # case 2: assessment + appeal rejected
    print("\n--- incident INC-005b ---")
    A.act("brake", {"force": 0.8})
    C.act("brake", {"force": 0.8})

    # Phase 2: filing + fee deposit
    C.deposit_fee(INC_005b, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_005b)
    R.notify_actor("A", incident_id=INC_005b)
    R.notify_actor_named("A", incident_id=INC_005b)
    A.acknowledge(INC_005b)
    R.notify_actor_keeper_open(INC_005b)
    A.deposit_fee(INC_005b, amount=100, currency="USD")

    # Phase 3: evidence collection
    R.request_evidence("A", incident_id=INC_005b)
    A.submit_evidence(INC_005b)
    R.request_evidence("C", incident_id=INC_005b)
    C.submit_evidence(INC_005b)

    # Phase 4: assessment — fees NOT released here; appeal window remains open
    print("\n--- initial assessment ---")
    R.query_fee_status(INC_005b)
    R.issue_contribution_result(INC_005b)
    R.notify_assessment_complete(INC_005b)

    # Appeal phase: A submits no additional evidence → APPEAL_REJECTED, initial result stands
    print("\n--- appeal ---")
    appeal = {
        "type": "ASSESSMENT_APPEAL",
        "incident_id": INC_005b,
        "submitter_id": A.terminal_id,
        "target_assessment_id": A._last_assessment_cert_id or "UNKNOWN",
        "appeal_grounds": {
            "category": "FACTUAL_ERROR",
            "description": "No additional evidence provided; testing rejection path."
        },
        "signature": f"SIG_{A.terminal_id}_APPEAL",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    world.send("A", "R", appeal)
    R.verify_appeal_evidence(INC_005b)
    R.reject_pending_appeal(INC_005b)
    # appeal window expires → each Keeper releases its own escrow → Referee acknowledges FEE_RECEIPT (RFC §6.24)
    Kc.release_fee(INC_005b)
    Ka.release_fee(INC_005b)
    R.send_fee_receipt(INC_005b)

    # query Referee stats from the Referee's own Keeper (where R self-anchors its actions)
    print("\n--- querying Referee stats ---")
    C.query_referee_stats("R", "Kr")

    # --- assertions: the Keeper's view of R's track record (§6.20/§6.21) ---
    print("\n--- assertions ---")
    stats = world.last("C", "REFEREE_STATS_RESULT")
    assert stats is not None and stats["found"], "R's stats must be on record at its Keeper"
    # Two incidents assessed; one of them was appealed and that appeal was rejected.
    assert stats["assessment_count"] == 2, f"expected 2 assessments, got {stats['assessment_count']}"
    assert stats["appeal_count"] == 1, f"expected 1 appeal, got {stats['appeal_count']}"
    assert stats["appeal_rejected_count"] == 1, f"expected 1 rejected appeal, got {stats['appeal_rejected_count']}"
    # R self-anchored every action to its own Keeper with no sequence gaps.
    assert stats["anchor_continuity"] is True, "R's anchor chain at its Keeper must be gap-free"

    print("[OK] R's Keeper reports assessment_count=2, appeal_count=1,"
          " appeal_rejected_count=1, anchor_continuity=True.")

if __name__ == "__main__":
    run()
