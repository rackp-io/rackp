# edge_16_technical_violation.py
# RFC §6.10, §9.5 (rackp#15/rackp#18): a Claimant submits genuine evidence but
# self-reports a stored_hash that does not match what the Referee independently
# computes from the payload (§6.10: "the discrepancy MUST be recorded in
# CONTRIBUTION_RESULT.assessment.technical_violation"). No other scenario in this
# suite exercises this path -- technical_violation is [] everywhere else, including
# edge_01_liar, whose forgery is caught as a Keeper miss rather than a self-report
# mismatch (see its own note on that distinction).
#
# The point: technical_violation entries are {profile_id, norm_id, detail}, not a
# bare norm_id or a free-text string. A norm_id is unique only within its profile
# (§9.1 layers every profile on the Standard Norm, so more than one is normally in
# play), and the norm actually violated here -- RACKP-STD-001 "Evidence Integrity",
# "the hash of data submitted in EVIDENCE_SUBMISSION must match the data_hash of the
# corresponding CLAIM_ANCHOR" -- belongs to rackp.standard.v1 specifically, not to
# whatever domain profile the parties may also have declared.
from datetime import datetime, timezone

from classes.topology import standard_world

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario edge-16: technical_violation on a self-reported hash mismatch ===")
    INC_E16 = "0000e16a-0000-4000-8000-00000000e16a"

    print("\n--- session start + honest anchoring ---")
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/rackp-standard-v1.json"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/rackp-standard-v1.json"}])
    A.act("lane_change", {"speed_kmh": 80, "signal_used": True})
    C.act("lane_change", {"speed_kmh": 80, "signal_used": True})

    print("\n--- incident INC-E16 ---")
    C.deposit_fee(INC_E16, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E16)
    R.notify_actor("A", incident_id=INC_E16)
    R.notify_actor_named("A", incident_id=INC_E16)
    A.acknowledge(INC_E16)
    R.notify_actor_keeper_open(INC_E16)
    A.deposit_fee(INC_E16, amount=100, currency="USD")

    print("\n--- evidence: A honest, C's self-reported stored_hash is wrong ---")
    R.request_evidence("A", incident_id=INC_E16)
    A.submit_evidence(INC_E16)
    R.request_evidence("C", incident_id=INC_E16)
    # C's own claim -- the anchored record itself is genuine. What is forged is only
    # the stored_hash C self-reports in verification_info, not the payload or the
    # anchor: this is exactly the case §6.10 requires the Referee to catch by
    # independent recomputation, distinct from a payload that never matches its
    # own claim (which edge_01/edge_03 exercise via other paths).
    claim = C._last_claim
    query = C._pending_queries[INC_E16]
    forged_submission = {
        "type": "EVIDENCE_SUBMISSION",
        "incident_id": INC_E16,
        "submitter_id": C.terminal_id,
        "payload": {
            "raw_data": claim.to_dict(),
            "metadata": {"terminal_id": C.terminal_id, "firmware_version": "sim-v1.0"},
        },
        "statement": {"summary": "C performed action 'lane_change'.", "raw_log_reference": claim.claim_id},
        "verification_info": {
            "keeper_endpoint": f"sim://{C._keeper_name}",
            "claim_id": claim.claim_id,
            "sequence_number": claim.seq,
            "stored_hash": "f" * 64,  # wrong on purpose; the real hash is claim.hash
        },
        "signature": f"SIG_{C.terminal_id}_{claim.seq}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    world.send("C", query["_sender"], forged_submission)

    R.verify_claim_chain("A", incident_id=INC_E16, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E16, keeper_name="Kc")

    print("\n--- assessment ---")
    R.query_fee_status(INC_E16)
    R.issue_contribution_result(INC_E16)
    R.notify_assessment_complete(INC_E16)
    Kc.release_fee(INC_E16)
    Ka.release_fee(INC_E16)
    R.send_fee_receipt(INC_E16)

    # --- assertions: the mismatch surfaces as a structured, profile-qualified entry ---
    print("\n--- assertions ---")
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    verdict = result["assessment"]

    # THE point: profile_id + norm_id, not a bare string. RACKP-STD-001 lives in
    # rackp.standard.v1, which both parties are assessed under here.
    assert verdict["technical_violation"] == [
        {
            "profile_id": "rackp.standard.v1",
            "norm_id": "RACKP-STD-001",
            "detail": (
                f"{C.terminal_id}: payload hash mismatch"
                f" (computed={claim.hash[:8]}... reported={'f' * 8}...)"
            ),
        }
    ], f"got {verdict['technical_violation']}"

    # The anchored record itself is genuine and reachable via the Keeper, so
    # Keeper-side VERIFICATION_QUERY still succeeds -- this is a self-report
    # discrepancy, not a missing or forged anchor (unlike edge_01/edge_03).
    results = R._incidents[INC_E16]["results"]
    assert results.get(A.terminal_id) is True and results.get(C.terminal_id) is True, \
        f"the anchor itself verifies for both parties, got {results}"

    # A self-reported discrepancy is an integrity finding, not a verification failure:
    # it does not by itself change the VERIFIED/VERIFIED fault baseline (RFC §7). The
    # Referee's independently *computed* hash -- not the forged stored_hash -- is what
    # Keeper verification checked, which is why both parties still show VERIFIED above.
    fault = verdict["fault"]
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.5, 0.5, 0.0), \
        f"a self-reported hash mismatch does not itself move the honest baseline, got {fault}"
    assert fault["confidence"] == "HIGH"

    per_keeper = R._received_fees[INC_E16]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, f"got {per_keeper}"
    assert Kc._escrow[INC_E16]["state"] == "SETTLED" and Ka._escrow[INC_E16]["state"] == "SETTLED"

    print("[OK] C's self-reported stored_hash disagreed with the Referee's independently"
          " computed hash: technical_violation carries {profile_id: rackp.standard.v1,"
          " norm_id: RACKP-STD-001, detail}, not a bare norm_id or free-text string;"
          " Keeper verification (against the computed hash, not the forged one) still"
          " passes for both parties -> honest 0.5/0.5/HIGH baseline unchanged; fees"
          " SETTLED.")

if __name__ == "__main__":
    run()
