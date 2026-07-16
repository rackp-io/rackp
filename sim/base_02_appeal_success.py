# base_02_appeal_success.py
# RFC Section 5 (Phase 2–4): AppealActor submits falsified evidence; subsequent appeal with genuine evidence revises assessment
# Phase 2: Claimant files ASSESSMENT_REQUEST + FEE_DEPOSIT; Referee sends ACTOR_NOTIFICATION; Actor deposits FEE_DEPOSIT
# Phase 3: Referee requests evidence; Actor submits falsified hash → FAILED → actor_fault=0.8
# Phase 4: initial CONTRIBUTION_RESULT; Actor files ASSESSMENT_APPEAL with genuine evidence → verified → assessment revised
from classes.topology import standard_world
from scenario_actor.AppealActor import AppealActor

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world(AppealActor)

    print("=== Scenario 02: appeal success ===")
    INC_002 = "00000002-0000-4000-8000-000000000002"

    # Phase 1: Norm declaration + evidence anchoring
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + fee deposit
    C.deposit_fee(INC_002, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_002)
    R.notify_actor("A", incident_id=INC_002)
    R.notify_actor_named("A", incident_id=INC_002)
    A.acknowledge(INC_002)
    R.notify_actor_keeper_open(INC_002)
    A.deposit_fee(INC_002, amount=100, currency="USD")

    # Phase 3: evidence collection (A submits falsified evidence as LiarActor → FAILED)
    R.request_evidence("A", incident_id=INC_002)
    A.submit_evidence(INC_002)
    R.request_evidence("C", incident_id=INC_002)
    C.submit_evidence(INC_002)
    # Anchor-chain verification → evidence_sufficiency coverage (RFC §6.14). Coverage is
    # about anchoring, independent of whether the submitted evidence verifies: A's chain
    # is intact even though its falsified evidence will FAIL verification.
    R.verify_claim_chain("A", incident_id=INC_002, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_002, keeper_name="Kc")

    # Phase 4: initial assessment — actor_fault=0.8 (A's evidence FAILED)
    # fees not released here: appeal window remains open
    print("\n--- initial assessment ---")
    R.query_fee_status(INC_002)
    R.issue_contribution_result(INC_002)
    R.notify_assessment_complete(INC_002)

    # --- assertions: initial verdict (A's evidence FAILED vs C VERIFIED) ---
    initial_result = world.last("C", "CONTRIBUTION_RESULT")
    initial = initial_result["assessment"]
    initial_cert = initial["certification"]["cert_id"]
    ifault = initial["fault"]
    # Section 7 Outcome Table: actor FAILED, claimant VERIFIED → 0.8 / 0.2 / 0.0, MEDIUM.
    assert (ifault["actor_fault"], ifault["claimant_fault"], ifault["external_factor"]) == (0.8, 0.2, 0.0), \
        f"FAILED/VERIFIED must be 0.8/0.2/0.0, got {ifault}"
    assert ifault["confidence"] == "MEDIUM"
    assert round(sum(v for k, v in ifault.items() if k != "confidence"), 10) == 1.0
    ep = initial_result["evidence_provenance"]
    assert "FAILED" in ep and "VERIFIED" in ep, f"actor FAILED, claimant VERIFIED expected, got {ep}"
    # Coverage is DEFINITIVE despite the FAILED evidence: anchoring ≠ evidence verification.
    assert initial["evidence_sufficiency"]["assessment_status"] == "DEFINITIVE"

    # Appeal phase
    print("\n--- appeal ---")
    A.file_appeal(use_real_evidence=True)          # A → R: ASSESSMENT_APPEAL (stored)
    # Appeal is now pending — FEE_CLAIM must be rejected (RFC §6.22)
    R.claim_fee(INC_002)
    R.request_evidence("C", incident_id=INC_002)   # R → C: EVIDENCE_QUERY_REQUEST (appeal round)
    C.submit_evidence(INC_002)                     # C → R: EVIDENCE_SUBMISSION; R → K: VERIFICATION_QUERY
    R.verify_appeal_evidence(INC_002)              # R → K: VERIFICATION_QUERY for A's evidence → VERIFIED
    R.accept_appeal(INC_002)                       # R anchors APPEAL_ACCEPTED, updates A's result
    R.issue_contribution_result(INC_002)           # R → A, C: revised CONTRIBUTION_RESULT (actor_fault=0.5)
    R.notify_assessment_complete(INC_002)          # R → K: INCIDENT_NOTICE(ASSESSMENT_COMPLETE)

    # --- assertions: appeal outcome (genuine NEW evidence moved the verdict) ---
    print("\n--- assertions: successful appeal ---")
    # A FEE_CLAIM raised while the appeal was pending was rejected (RFC §6.22).
    fcr = world.last("R", "FEE_CLAIM_RESULT")
    assert fcr is not None and fcr["status"] == "REJECTED"
    assert fcr["rejection_reason"] == "APPEAL_PENDING", \
        f"a claim during an open appeal must be APPEAL_PENDING, got {fcr.get('rejection_reason')}"

    # The successful appeal revised the verdict: A's genuine evidence now VERIFIES.
    revised_result = world.last("C", "CONTRIBUTION_RESULT")
    revised = revised_result["assessment"]
    revised_cert = revised["certification"]["cert_id"]
    rfault  = revised["fault"]
    assert (rfault["actor_fault"], rfault["claimant_fault"], rfault["external_factor"]) == (0.5, 0.5, 0.0), \
        f"revised VERIFIED/VERIFIED must be 0.5/0.5/0.0, got {rfault}"
    assert rfault["confidence"] == "HIGH"
    assert round(sum(v for k, v in rfault.items() if k != "confidence"), 10) == 1.0
    assert "FAILED" not in revised_result["evidence_provenance"], "after appeal both parties verify"
    # The revision is a new, distinct verdict (its own cert), not the initial one.
    assert revised_cert != initial_cert, "revised verdict must carry a new cert_id"

    # Re-appeal phase: A, now an honest/verified party, is still unhappy with the 50/50
    # split and presses again — but with NO new evidence (its genuine record was already
    # assessed). This is the honest-but-futile re-litigation pattern. An appeal succeeds
    # on new verifiable FACTS, never on mere persistence: with nothing new to verify, the
    # Referee rejects it and the revised verdict stands. (Still within the open appeal
    # window, so this resolves before escrow settles.)
    print("\n--- re-appeal with no new evidence (must not move the verdict) ---")
    A.file_appeal_disputing_split()                # A → R: ASSESSMENT_APPEAL, no additional_evidence
    R.verify_appeal_evidence(INC_002)              # R: nothing to verify → "no evidence provided"
    R.reject_pending_appeal(INC_002)               # R → A, C: APPEAL_REJECTED; anchors APPEAL_REJECTED

    # appeal window expires → each Keeper releases its own escrow → Referee acknowledges FEE_RECEIPT (RFC §6.24)
    Kc.release_fee(INC_002)
    Ka.release_fee(INC_002)
    R.send_fee_receipt(INC_002)

    # --- assertions: futile re-appeal left the verdict unmoved ---
    print("\n--- assertions: futile re-appeal ---")
    # The re-appeal was rejected for introducing no new verifiable evidence.
    av = R._appeal_verification_results[INC_002]
    assert av[0] is False and av[2] == "no evidence provided", \
        f"a re-appeal with no new evidence must not verify, got {av}"
    rej = world.last("A", "APPEAL_REJECTED")
    assert rej is not None and rej["reason"] == "no evidence provided", f"got {rej}"
    # It was the SECOND appeal on this incident; persistence is counted and recorded
    # (each ASSESSMENT_APPEAL is anchored), but it does not accumulate into a change.
    assert R._appeal_counts[INC_002][A.terminal_id] == 2, "this is the appellant's second appeal"
    # No third verdict was minted: only the initial and the revised exist, and the latest
    # verdict the parties hold is still the revised one — unchanged by the re-appeal.
    all_results = world.all_of("C", "CONTRIBUTION_RESULT")
    assert len(all_results) == 2, f"a rejected re-appeal must not mint a new verdict, got {len(all_results)}"
    stands = world.last("C", "CONTRIBUTION_RESULT")["assessment"]
    assert stands["certification"]["cert_id"] == revised_cert, "the revised verdict must stand unchanged"
    assert (stands["fault"]["actor_fault"], stands["fault"]["claimant_fault"]) == (0.5, 0.5), \
        "fault must be unchanged after a rejected re-appeal"
    # Escrow settles only after the appeals resolve — both parties' Keepers.
    assert Kc._escrow[INC_002]["state"] == "SETTLED" and Ka._escrow[INC_002]["state"] == "SETTLED"

    print("[OK] initial FAILED/VERIFIED -> 0.8/0.2/MEDIUM; FEE_CLAIM during appeal denied"
          " (APPEAL_PENDING); genuine NEW evidence revised it to 0.5/0.5/HIGH (new cert);"
          " a second honest re-appeal with NO new evidence was rejected (no evidence"
          " provided) -> revised verdict stands, no third cert; escrow SETTLED.")

if __name__ == "__main__":
    run()
