# edge_04_fee_nonpayment.py
# RFC Section 5 (Phase 1-4): a full, base_01-conformant assessment in which the Actor
# never sends its FEE_DEPOSIT. The Actor otherwise participates honestly — it declares
# its Norm, anchors its action, acknowledges the notification and submits genuine
# evidence; the ONLY deviation is that it does not fund its half of the fee.
#
# How non-payment is handled (STD-010, STD-026; RFC-0001 §7, RFC-0002 §1.6):
#   - The assessment proceeds normally. Both parties' evidence VERIFIES → 0.5/0.5/HIGH.
#   - Fee compliance is DISCLOSED ONLY: actor_fee_status=NOT_DEPOSITED is recorded in
#     assessment.fee_compliance and the unpaid amount is quantified in fee_snapshot, but
#     it has NO effect on the fault values and is NOT a technical_violation. The fault
#     measures deviation from the Norm in the incident, never participation funding —
#     this is the Economic Boundary (RFC-0002 §1.6).
#   - Only the Claimant's escrow exists (the Actor's Keeper holds nothing), so the
#     Referee receives only the Claimant's 100, not 200 — settlement reflects what was
#     actually deposited.
from classes.topology import standard_world

def run():
    # Same canonical topology as base_01 (Kr/Kc/Ka); the Actor simply never deposits.
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario edge-04: Actor fee non-payment (disclosure only, STD-010/026) ===")
    INC_E04 = "0000e04a-0000-4000-8000-00000000e04a"

    # Phase 1: Norm declaration + evidence anchoring (the Actor participates honestly).
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + fee deposit. The Claimant deposits; the Actor acknowledges (so it
    # is a reached, participating party) but never sends its own FEE_DEPOSIT.
    C.deposit_fee(INC_E04, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E04)
    R.notify_actor("A", incident_id=INC_E04)
    R.notify_actor_named("A", incident_id=INC_E04)
    A.acknowledge(INC_E04)
    R.notify_actor_keeper_open(INC_E04)
    # (no A.deposit_fee — THIS is the deviation)

    # Phase 3: evidence collection — both parties submit genuine evidence and verify.
    R.request_evidence("A", incident_id=INC_E04)
    A.submit_evidence(INC_E04)
    R.request_evidence("C", incident_id=INC_E04)
    C.submit_evidence(INC_E04)
    R.verify_claim_chain("A", incident_id=INC_E04, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E04, keeper_name="Kc")

    # Phase 4: assessment + settlement. Only the Claimant's escrow (Kc) holds funds.
    R.query_fee_status(INC_E04)
    R.issue_contribution_result(INC_E04)
    R.notify_assessment_complete(INC_E04)
    Kc.release_fee(INC_E04)          # only the Claimant's 100 is in escrow
    R.send_fee_receipt(INC_E04)

    # --- assertions: non-payment is disclosed only, never a fault input ---
    print("\n--- assertions ---")
    # One assessment, delivered identically to both parties (RFC §6.14).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), "both parties must receive the same cert_id"

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # THE point (STD-010, §7): both parties verified, so fault is the honest
    # 0.5/0.5/HIGH — IDENTICAL to base_01. Non-payment did NOT move it by even a hair.
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.5, 0.5, 0.0), \
        f"non-payment must not change fault, got {fault}"
    assert fault["confidence"] == "HIGH"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0
    # Non-payment is NOT an integrity/norm violation.
    assert verdict["technical_violation"] == [], f"non-payment is not a technical_violation, got {verdict['technical_violation']}"
    ep = result["evidence_provenance"]
    assert "VERIFIED" in ep and "FAILED" not in ep, f"both parties verified, got {ep}"

    # The non-payment surfaces ONLY here: actor NOT_DEPOSITED, claimant DEPOSITED, and the
    # unpaid amount is quantified in the fee_snapshot (the Economic Boundary disclosure).
    fc = verdict["fee_compliance"]
    assert fc["actor_fee_status"] == "NOT_DEPOSITED", f"actor never deposited, got {fc['actor_fee_status']}"
    assert fc["claimant_fee_status"] == "DEPOSITED", f"claimant deposited, got {fc['claimant_fee_status']}"
    assert fc["fee_snapshot"]["actor_expected"] == 100, f"the unpaid half is quantified, got {fc['fee_snapshot']}"
    # The Actor was reached and acknowledged — non-payment is orthogonal to participation.
    assert verdict["actor_participation"]["status"] == "ACKNOWLEDGED", \
        f"the Actor participated; only its fee is missing, got {verdict['actor_participation']}"

    # Both chains are intact (anchoring is unaffected by non-payment) → DEFINITIVE.
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "DEFINITIVE", f"got {es['assessment_status']}"
    assert es["actor_coverage"] == "MEDIUM" and es["claimant_coverage"] == "MEDIUM", \
        f"got {es['actor_coverage']}/{es['claimant_coverage']}"

    # Settlement reflects what was actually deposited: only Kc releases 100. The Actor's
    # Keeper (Ka) has an escrow shell from the INCIDENT_OPEN notice but holds NO funds, so
    # it never releases and the Referee receives 100, not 200.
    ka_escrow = Ka._escrow.get(INC_E04, {})
    assert sum(ka_escrow.get("deposits", {}).values()) == 0, "the Actor's Keeper holds no funds (it never deposited)"
    assert ka_escrow.get("state") == "ESCROWED", f"Ka's empty escrow is never released, got {ka_escrow.get('state')}"
    per_keeper = R._received_fees[INC_E04]["keepers"]
    assert per_keeper.get("Kc") == 100 and "Ka" not in per_keeper, f"only the Claimant's 100 is released, got {per_keeper}"
    assert sum(per_keeper.values()) == 100, "the Referee receives only the deposited 100, not 200"
    assert Kc._escrow[INC_E04]["state"] == "SETTLED", "the Claimant's escrow settles"

    print("[OK] full base flow, Actor never paid its fee: both verified -> 0.5/0.5/HIGH"
          " (fault UNCHANGED by non-payment); disclosed only as fee_compliance"
          " actor_fee_status=NOT_DEPOSITED (unpaid 100 quantified); not a"
          " technical_violation; Actor still ACKNOWLEDGED; only Kc's 100 settled (not 200).")

if __name__ == "__main__":
    run()
