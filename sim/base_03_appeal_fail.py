# base_03_appeal_fail.py
# After high-fault initial assessment, appeal is filed without valid evidence and rejected.
# RFC Section 5 (Phase 4): ASSESSMENT_APPEAL with unverifiable hash → APPEAL_REJECTED, initial assessment stands
from classes.topology import standard_world
from scenario_actor.AppealActor import AppealActor

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world(AppealActor)

    print("=== Scenario 03: Appeal Fail ===")
    INC_003 = "00000003-0000-4000-8000-000000000003"

    # Phase 1: Norm declaration + evidence anchoring
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + fee deposit
    C.deposit_fee(INC_003, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_003)
    R.notify_actor("A", incident_id=INC_003)
    R.notify_actor_named("A", incident_id=INC_003)
    A.acknowledge(INC_003)
    R.notify_actor_keeper_open(INC_003)
    A.deposit_fee(INC_003, amount=100, currency="USD")

    # Phase 3: evidence collection (A submits falsified evidence as AppealActor → FAILED)
    print("\n--- evidence collection ---")
    R.request_evidence("A", incident_id=INC_003)
    A.submit_evidence(INC_003)
    R.request_evidence("C", incident_id=INC_003)
    C.submit_evidence(INC_003)
    R.verify_claim_chain("A", incident_id=INC_003, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_003, keeper_name="Kc")

    # Phase 4: initial assessment — actor_fault=0.8 (A's evidence FAILED)
    print("\n--- initial assessment ---")
    R.query_fee_status(INC_003)
    R.issue_contribution_result(INC_003)
    R.notify_assessment_complete(INC_003)

    # --- assertions: initial verdict (A's evidence FAILED) ---
    initial_result = world.last("C", "CONTRIBUTION_RESULT")
    initial = initial_result["assessment"]
    initial_cert = initial["certification"]["cert_id"]
    ifault = initial["fault"]
    assert (ifault["actor_fault"], ifault["claimant_fault"], ifault["external_factor"]) == (0.8, 0.2, 0.0), \
        f"FAILED/VERIFIED must be 0.8/0.2/0.0, got {ifault}"
    assert ifault["confidence"] == "MEDIUM"
    assert round(sum(v for k, v in ifault.items() if k != "confidence"), 10) == 1.0
    assert "FAILED" in initial_result["evidence_provenance"]
    assert initial["evidence_sufficiency"]["assessment_status"] == "DEFINITIVE"

    # Appeal phase: A submits fake hash not present in Keeper → APPEAL_REJECTED, initial result stands
    print("\n--- appeal ---")
    A.file_appeal(use_real_evidence=False)         # A → R: ASSESSMENT_APPEAL (fake hash, stored)
    R.request_evidence("C", incident_id=INC_003)   # R → C: EVIDENCE_QUERY_REQUEST (appeal round)
    C.submit_evidence(INC_003)                     # C → R: EVIDENCE_SUBMISSION; R → K: VERIFICATION_QUERY
    R.verify_appeal_evidence(INC_003)              # R → K: VERIFICATION_QUERY for A's evidence → NOT_FOUND
    R.reject_pending_appeal(INC_003)               # R → A, C: APPEAL_REJECTED; anchors APPEAL_REJECTED
    # appeal window resumes and expires → each Keeper releases its own escrow → Referee acknowledges FEE_RECEIPT (RFC §6.24)
    Kc.release_fee(INC_003)                        # initial result stands, fees released to Referee
    Ka.release_fee(INC_003)
    R.send_fee_receipt(INC_003)

    # --- assertions: appeal failed, initial verdict stands ---
    print("\n--- assertions ---")
    # The appeal's fake evidence did not verify against the Keeper (NOT_FOUND).
    av = R._appeal_verification_results[INC_003]
    assert av[0] is False and av[2] == "NOT_FOUND", f"fake appeal evidence must not verify, got {av[2]}"
    # The appellant received an APPEAL_REJECTED carrying that reason.
    rej = world.last("A", "APPEAL_REJECTED")
    assert rej is not None
    assert rej["reason"] == "NOT_FOUND"
    # No revised verdict was issued: the initial assessment stands unchanged.
    stands = world.last("C", "CONTRIBUTION_RESULT")["assessment"]
    assert stands["certification"]["cert_id"] == initial_cert, "a rejected appeal must not mint a new verdict"
    assert (stands["fault"]["actor_fault"], stands["fault"]["claimant_fault"]) == (0.8, 0.2), \
        "fault must be unchanged after a rejected appeal"
    # Escrow settles to the Referee (the standing assessment is payable).
    assert Kc._escrow[INC_003]["state"] == "SETTLED" and Ka._escrow[INC_003]["state"] == "SETTLED"

    print("[OK] FAILED/VERIFIED -> 0.8/0.2/MEDIUM; fake appeal evidence NOT_FOUND ->"
          " APPEAL_REJECTED; initial verdict stands (same cert); escrow SETTLED.")

if __name__ == "__main__":
    run()
