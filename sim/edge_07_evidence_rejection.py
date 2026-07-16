# edge_07_evidence_rejection.py
# RFC Section 5 (Phase 1-4) + §6.11 (EVIDENCE_REJECTION): three full, base_01-conformant
# assessments in which a party EXPLICITLY refuses to submit evidence (sends an
# EVIDENCE_REJECTION with a reason) instead of simply staying silent. Everything else is
# honest participation — the parties anchor, acknowledge, deposit their fees; the only
# deviation is the formal refusal at the evidence step.
#
# How an explicit rejection is handled (§6.11, §7, §4.1):
#   - On receiving EVIDENCE_REJECTION the Referee records the refusing party's result as
#     FAILED *explicitly* AND self-anchors an EVIDENCE_REJECTED CLAIM_ANCHOR to its own
#     Keeper (§4.1). So the declination is not lost — it leaves an auditable trail (the
#     anchor) carrying the incident, plus the stated reason on the message itself.
#   - Refusing is treated exactly like failing: a queried party that declines is FAILED
#     (§7). Declining is a valid choice, but its consequence is borne by the party that
#     makes it (the protocol's "silence is not a right an AI can hold" stance).
#   - The contrast with edge_02 (silent withholding) is the audit trail: edge_02's party
#     said NOTHING (no message, result absent-defaulted to False, no rejection anchor);
#     here the party formally refuses, so results[party] is set False *and* the Referee
#     anchors EVIDENCE_REJECTED with the reason on record. Same fault, richer trail.
#   - Coverage != submission: each party still ANCHORED its action, so the Referee's
#     ANCHOR_CHAIN_QUERY surfaces an intact chain (MEDIUM) → DEFINITIVE. Refusing to
#     SUBMIT is not the same as having no record (contrast edge_05, NONE → PROVISIONAL).
#   - The three cases sweep the Verification Outcome Table (§7):
#       A: Actor refuses    → FAILED/VERIFIED → 0.8/0.2 MEDIUM
#       B: Claimant refuses → VERIFIED/FAILED → 0.2/0.8 MEDIUM
#       C: both refuse       → FAILED/FAILED  → 0.5/0.5 LOW
#     Case C's 0.5/0.5 is NOT base_01's 0.5/0.5: the confidence (LOW vs HIGH) is what
#     distinguishes "neither side verified" from "both sides verified".
#   - Fee and participation are orthogonal to the refusal: both parties deposited (→ 200
#     settled, escrows SETTLED) and the Actor acknowledged (→ ACKNOWLEDGED) in every case.
from classes.topology import standard_world

INC_E07A = "0000e07a-0000-4000-8000-00000000e07a"
INC_E07B = "0000e07b-0000-4000-8000-00000000e07b"
INC_E07C = "0000e07c-0000-4000-8000-00000000e07c"

def run():
    # Same canonical topology as base_01 (Kr/Kc/Ka).
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Edge 07: Evidence Rejection (explicit refusal, §6.11) ===")

    # Phase 1 (session): each party declares its Norm once. Both anchor honestly across the
    # three incidents below, so every chain stays intact — the only deviation per case is
    # the explicit evidence refusal, never a missing chain.
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])

    # ============================================================== Case A: Actor refuses
    print("\n--- Case A: Actor rejects evidence submission ---")
    A.act("maneuver", {"type": "evasive"})
    C.act("observe",  {"target": "maneuver"})

    C.deposit_fee(INC_E07A, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E07A)
    R.notify_actor("A", incident_id=INC_E07A)
    R.notify_actor_named("A", incident_id=INC_E07A)
    A.acknowledge(INC_E07A)
    R.notify_actor_keeper_open(INC_E07A)
    A.deposit_fee(INC_E07A, amount=100, currency="USD")

    R.request_evidence("A", incident_id=INC_E07A)
    A.reject_evidence(INC_E07A, reason="Data under maintenance; cannot provide at this time.")
    R.request_evidence("C", incident_id=INC_E07A)
    C.submit_evidence(INC_E07A)
    R.verify_claim_chain("A", incident_id=INC_E07A, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E07A, keeper_name="Kc")

    R.query_fee_status(INC_E07A)
    R.issue_contribution_result(INC_E07A)
    R.notify_assessment_complete(INC_E07A)
    Kc.release_fee(INC_E07A)
    Ka.release_fee(INC_E07A)
    R.send_fee_receipt(INC_E07A)

    print("\n--- Case A assertions ---")
    resA = world.last("C", "CONTRIBUTION_RESULT")
    assert resA["incident_id"] == INC_E07A
    # The Actor's refusal is recorded FAILED *explicitly* (not absent-defaulted); the
    # honest Claimant verifies.
    resultsA = R._incidents[INC_E07A]["results"]
    assert resultsA[A.terminal_id] is False, "the refusing Actor is recorded FAILED"
    assert resultsA[C.terminal_id] is True,  "the honest Claimant verifies"
    # A FORMAL rejection (with a reason) was actually sent — the audit-trail difference
    # from edge_02's silence.
    rejA = [m for m in world.all_of("R", "EVIDENCE_REJECTION") if m["incident_id"] == INC_E07A]
    assert len(rejA) == 1 and rejA[0]["submitter_id"] == A.terminal_id, "the Actor formally refused"
    assert rejA[0].get("reason"), "a formal rejection carries a reason"
    # The Referee anchored EVIDENCE_REJECTED to its OWN Keeper — the declination is on record.
    anchA = [a for a in Kr.anchors.values()
             if a.get("action_type") == "EVIDENCE_REJECTED" and a.get("incident_id") == INC_E07A]
    assert len(anchA) == 1, "the Referee anchors the declination as EVIDENCE_REJECTED"
    # FAILED(actor)/VERIFIED(claimant) → 0.8/0.2 MEDIUM; shares sum to 1.0 (§7).
    fA = resA["assessment"]["fault"]
    assert (fA["actor_fault"], fA["claimant_fault"], fA["external_factor"]) == (0.8, 0.2, 0.0), f"got {fA}"
    assert fA["confidence"] == "MEDIUM"
    assert round(fA["actor_fault"] + fA["claimant_fault"] + fA["external_factor"], 10) == 1.0
    # Refusing to SUBMIT is not the same as having no record: the Actor's anchored chain
    # still surfaces (MEDIUM) → DEFINITIVE. A refusal is not a technical_violation.
    esA = resA["assessment"]["evidence_sufficiency"]
    assert esA["assessment_status"] == "DEFINITIVE", f"intact chains -> DEFINITIVE, got {esA['assessment_status']}"
    assert esA["actor_coverage"] == "MEDIUM" and esA["claimant_coverage"] == "MEDIUM", \
        f"got {esA['actor_coverage']}/{esA['claimant_coverage']}"
    assert resA["assessment"]["technical_violation"] == [], "a refusal is not a technical_violation"
    # Participation and fee are orthogonal to the refusal: the Actor acknowledged and both
    # deposited, so fees settle exactly as in base_01.
    assert resA["assessment"]["actor_participation"]["status"] == "ACKNOWLEDGED"
    fcA = resA["assessment"]["fee_compliance"]
    assert fcA["actor_fee_status"] == "DEPOSITED" and fcA["claimant_fee_status"] == "DEPOSITED"
    perA = R._received_fees[INC_E07A]["keepers"]
    assert perA.get("Kc") == 100 and perA.get("Ka") == 100 and sum(perA.values()) == 200
    assert Kc._escrow[INC_E07A]["state"] == "SETTLED" and Ka._escrow[INC_E07A]["state"] == "SETTLED"
    print("[OK] Case A: Actor formally refused (reason on record + EVIDENCE_REJECTED anchored) ->"
          " FAILED / C VERIFIED -> 0.8/0.2/MEDIUM; chain intact (DEFINITIVE/MEDIUM); ACKNOWLEDGED;"
          " 200 settled.")

    # =========================================================== Case B: Claimant refuses
    # Realistic trigger: the Claimant fears its own evidence would confirm an unfavorable
    # finding, so it declines rather than submit.
    print("\n--- Case B: Claimant rejects evidence submission ---")
    A.act("stop",   {"zone": "intersection"})
    C.act("report", {"severity": "minor"})

    C.deposit_fee(INC_E07B, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E07B)
    R.notify_actor("A", incident_id=INC_E07B)
    R.notify_actor_named("A", incident_id=INC_E07B)
    A.acknowledge(INC_E07B)
    R.notify_actor_keeper_open(INC_E07B)
    A.deposit_fee(INC_E07B, amount=100, currency="USD")

    R.request_evidence("A", incident_id=INC_E07B)
    A.submit_evidence(INC_E07B)
    R.request_evidence("C", incident_id=INC_E07B)
    C.reject_evidence(INC_E07B, reason="Evidence would be self-incriminating; declining participation.")
    R.verify_claim_chain("A", incident_id=INC_E07B, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E07B, keeper_name="Kc")

    R.query_fee_status(INC_E07B)
    R.issue_contribution_result(INC_E07B)
    R.notify_assessment_complete(INC_E07B)
    Kc.release_fee(INC_E07B)
    Ka.release_fee(INC_E07B)
    R.send_fee_receipt(INC_E07B)

    print("\n--- Case B assertions ---")
    resB = world.last("C", "CONTRIBUTION_RESULT")
    assert resB["incident_id"] == INC_E07B
    # Mirror of Case A: now the Claimant is the one refused-FAILED; the honest Actor verifies.
    resultsB = R._incidents[INC_E07B]["results"]
    assert resultsB[A.terminal_id] is True,  "the honest Actor verifies"
    assert resultsB[C.terminal_id] is False, "the refusing Claimant is recorded FAILED"
    rejB = [m for m in world.all_of("R", "EVIDENCE_REJECTION") if m["incident_id"] == INC_E07B]
    assert len(rejB) == 1 and rejB[0]["submitter_id"] == C.terminal_id, "the Claimant formally refused"
    assert rejB[0].get("reason"), "a formal rejection carries a reason"
    anchB = [a for a in Kr.anchors.values()
             if a.get("action_type") == "EVIDENCE_REJECTED" and a.get("incident_id") == INC_E07B]
    assert len(anchB) == 1, "the Referee anchors the declination as EVIDENCE_REJECTED"
    # VERIFIED(actor)/FAILED(claimant) → 0.2/0.8 MEDIUM; the filing party is NOT credited
    # for declining (§7 — withholding is unrewarded in both directions).
    fB = resB["assessment"]["fault"]
    assert (fB["actor_fault"], fB["claimant_fault"], fB["external_factor"]) == (0.2, 0.8, 0.0), f"got {fB}"
    assert fB["confidence"] == "MEDIUM"
    assert round(fB["actor_fault"] + fB["claimant_fault"] + fB["external_factor"], 10) == 1.0
    esB = resB["assessment"]["evidence_sufficiency"]
    assert esB["assessment_status"] == "DEFINITIVE", f"got {esB['assessment_status']}"
    assert esB["actor_coverage"] == "MEDIUM" and esB["claimant_coverage"] == "MEDIUM", \
        f"got {esB['actor_coverage']}/{esB['claimant_coverage']}"
    assert resB["assessment"]["technical_violation"] == []
    perB = R._received_fees[INC_E07B]["keepers"]
    assert perB.get("Kc") == 100 and perB.get("Ka") == 100 and sum(perB.values()) == 200
    assert Kc._escrow[INC_E07B]["state"] == "SETTLED" and Ka._escrow[INC_E07B]["state"] == "SETTLED"
    print("[OK] Case B: Claimant formally refused -> A VERIFIED / FAILED -> 0.2/0.8/MEDIUM"
          " (filing party not credited for declining); DEFINITIVE/MEDIUM; 200 settled.")

    # ============================================================== Case C: both refuse
    print("\n--- Case C: Both parties reject evidence submission ---")
    A.act("idle", {"position": "junction_4"})
    C.act("idle", {"position": "junction_4"})

    C.deposit_fee(INC_E07C, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E07C)
    R.notify_actor("A", incident_id=INC_E07C)
    R.notify_actor_named("A", incident_id=INC_E07C)
    A.acknowledge(INC_E07C)
    R.notify_actor_keeper_open(INC_E07C)
    A.deposit_fee(INC_E07C, amount=100, currency="USD")

    R.request_evidence("A", incident_id=INC_E07C)
    A.reject_evidence(INC_E07C, reason="No comment.")
    R.request_evidence("C", incident_id=INC_E07C)
    C.reject_evidence(INC_E07C, reason="No comment.")
    R.verify_claim_chain("A", incident_id=INC_E07C, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E07C, keeper_name="Kc")

    R.query_fee_status(INC_E07C)
    R.issue_contribution_result(INC_E07C)
    R.notify_assessment_complete(INC_E07C)
    Kc.release_fee(INC_E07C)
    Ka.release_fee(INC_E07C)
    R.send_fee_receipt(INC_E07C)

    print("\n--- Case C assertions ---")
    resC = world.last("C", "CONTRIBUTION_RESULT")
    assert resC["incident_id"] == INC_E07C
    resultsC = R._incidents[INC_E07C]["results"]
    assert resultsC[A.terminal_id] is False and resultsC[C.terminal_id] is False, \
        "both refusing parties are recorded FAILED"
    # Both formally refused → two EVIDENCE_REJECTION messages and two EVIDENCE_REJECTED anchors.
    rejC = [m for m in world.all_of("R", "EVIDENCE_REJECTION") if m["incident_id"] == INC_E07C]
    assert len(rejC) == 2 and {m["submitter_id"] for m in rejC} == {A.terminal_id, C.terminal_id}, \
        "both parties formally refused"
    anchC = [a for a in Kr.anchors.values()
             if a.get("action_type") == "EVIDENCE_REJECTED" and a.get("incident_id") == INC_E07C]
    assert len(anchC) == 2, "the Referee anchors BOTH declinations"
    # THE point of Case C: FAILED/FAILED → 0.5/0.5 but confidence LOW. This is NOT base_01's
    # 0.5/0.5/HIGH — the same split, but the confidence distinguishes "neither side verified"
    # (LOW) from "both sides verified" (HIGH).
    fC = resC["assessment"]["fault"]
    assert (fC["actor_fault"], fC["claimant_fault"], fC["external_factor"]) == (0.5, 0.5, 0.0), f"got {fC}"
    assert fC["confidence"] == "LOW", \
        f"neither side verified -> LOW, NOT base_01's HIGH for the same 0.5/0.5, got {fC['confidence']}"
    assert round(fC["actor_fault"] + fC["claimant_fault"] + fC["external_factor"], 10) == 1.0
    # Coverage and confidence are orthogonal axes: both chains are intact (DEFINITIVE/MEDIUM)
    # even though NEITHER submission verified (LOW). A complete record does not imply a
    # confident verdict.
    esC = resC["assessment"]["evidence_sufficiency"]
    assert esC["assessment_status"] == "DEFINITIVE", f"intact chains -> DEFINITIVE, got {esC['assessment_status']}"
    assert esC["actor_coverage"] == "MEDIUM" and esC["claimant_coverage"] == "MEDIUM", \
        f"got {esC['actor_coverage']}/{esC['claimant_coverage']}"
    assert resC["assessment"]["technical_violation"] == []
    perC = R._received_fees[INC_E07C]["keepers"]
    assert perC.get("Kc") == 100 and perC.get("Ka") == 100 and sum(perC.values()) == 200
    assert Kc._escrow[INC_E07C]["state"] == "SETTLED" and Ka._escrow[INC_E07C]["state"] == "SETTLED"
    print("[OK] Case C: both formally refused (2 EVIDENCE_REJECTED anchored) -> FAILED/FAILED ->"
          " 0.5/0.5/LOW (the same split as base_01 but LOW, NOT HIGH; confidence disambiguates);"
          " chains intact (DEFINITIVE/MEDIUM) yet unverified; 200 settled.")

if __name__ == "__main__":
    run()
