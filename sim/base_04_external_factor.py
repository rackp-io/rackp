# base_04_external_factor.py
# Both parties are verified and both submit an external_factor_claim.
# RFC Section 7 Verification Outcome Table: VERIFIED/VERIFIED, both parties claim external → external_factor=0.8
# Expected: actor_fault=0.1  claimant_fault=0.1  external_factor=0.8  confidence=HIGH
from classes.topology import standard_world

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario 04: both parties claim external factor ===")
    INC_004 = "00000004-0000-4000-8000-000000000004"

    EXT_DESC = "Third-party infrastructure failure caused the incident."

    # Phase 1: Norm declaration + evidence anchoring (both parties include external_factor_claim)
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})
    # An external_factor_claim with claimed=True MUST cite supporting_evidence_refs:
    # claim_id values of anchored CLAIM_ANCHOR records the Referee can verify against
    # the Keeper (evidence_submission.json external_factor_claim if/then). Each party
    # references its own just-anchored record.
    A._external_factor_claim = {"claimed": True, "description": EXT_DESC,
                                "supporting_evidence_refs": [A._last_claim.claim_id]}
    C._external_factor_claim = {"claimed": True, "description": EXT_DESC,
                                "supporting_evidence_refs": [C._last_claim.claim_id]}

    # Phase 2: filing + fee deposit
    C.deposit_fee(INC_004, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_004)
    R.notify_actor("A", incident_id=INC_004)
    R.notify_actor_named("A", incident_id=INC_004)
    A.acknowledge(INC_004)
    R.notify_actor_keeper_open(INC_004)
    A.deposit_fee(INC_004, amount=100, currency="USD")

    # Phase 3: evidence collection (both submit honest evidence with external_factor_claim)
    R.request_evidence("A", incident_id=INC_004)
    A.submit_evidence(INC_004)
    R.request_evidence("C", incident_id=INC_004)
    C.submit_evidence(INC_004)
    R.verify_claim_chain("A", incident_id=INC_004, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_004, keeper_name="Kc")

    # Phase 4: assessment — VERIFIED/VERIFIED, both claim external → external_factor=0.8
    print("\n--- assessment ---")
    R.query_fee_status(INC_004)
    R.issue_contribution_result(INC_004)
    R.notify_assessment_complete(INC_004)
    # appeal window expires → each Keeper releases its own escrow → Referee acknowledges FEE_RECEIPT (RFC §6.24)
    Kc.release_fee(INC_004)
    Ka.release_fee(INC_004)
    R.send_fee_receipt(INC_004)

    # --- assertions: a shared external factor displaces fault from both parties ---
    print("\n--- assertions ---")
    result  = world.last("C", "CONTRIBUTION_RESULT")
    verdict = result["assessment"]
    fault   = verdict["fault"]
    # Both VERIFIED + both claim external → external_factor=0.8, each party's 0.5 scaled
    # by (1-0.8) → 0.1 / 0.1 / 0.8. The three shares still sum to 1.0 (§7).
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.1, 0.1, 0.8), \
        f"both-claim external must be 0.1/0.1/0.8, got {fault}"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0
    assert fault["confidence"] == "HIGH"
    # External factor is only credited because BOTH parties' evidence verified.
    assert "FAILED" not in result["evidence_provenance"]
    assert verdict["evidence_sufficiency"]["assessment_status"] == "DEFINITIVE"
    assert Kc._escrow[INC_004]["state"] == "SETTLED" and Ka._escrow[INC_004]["state"] == "SETTLED"

    print("[OK] both parties VERIFIED and claiming external -> 0.1/0.1/0.8 (sum 1.0), HIGH;"
          " DEFINITIVE; escrow SETTLED.")

if __name__ == "__main__":
    run()
