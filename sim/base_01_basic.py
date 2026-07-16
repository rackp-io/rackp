# base_01_basic.py
# RFC Section 5 (Phase 2–4): complete basic honest-actor assessment flow
# Kc = Claimant's Keeper, Ka = Actor's Keeper (standard split-Keeper configuration per RFC §4.4)
# Phase 1: Actor and Claimant declare Norm via SESSION_START, then anchor actions to their respective Keepers
# Phase 2: Claimant files ASSESSMENT_REQUEST + FEE_DEPOSIT; Referee sends ACTOR_NOTIFICATION; Actor deposits FEE_DEPOSIT
# Phase 3: Referee requests evidence from both parties; each submits and Keeper verifies
# Phase 4: Referee issues CONTRIBUTION_RESULT
# Section 7 Verification Outcome Table: VERIFIED/VERIFIED → actor_fault=0.5, claimant_fault=0.5, confidence=HIGH
from classes.topology import standard_world

def run():
    # Canonical topology: Kr/Kc/Ka, one Keeper per party; R's profile published.
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario 01: basic incident flow ===")
    INC_001 = "00000001-0000-4000-8000-000000000001"

    # Phase 1: Norm declaration + evidence anchoring
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + fee deposit
    C.deposit_fee(INC_001, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_001)
    R.notify_actor("A", incident_id=INC_001)
    R.notify_actor_named("A", incident_id=INC_001)
    A.acknowledge(INC_001)
    R.notify_actor_keeper_open(INC_001)
    A.deposit_fee(INC_001, amount=100, currency="USD")

    # Phase 3: evidence collection
    R.request_evidence("A", incident_id=INC_001)
    A.submit_evidence(INC_001)
    R.request_evidence("C", incident_id=INC_001)
    C.submit_evidence(INC_001)
    # Anchor-chain verification feeds evidence_sufficiency coverage (RFC §6.14): the
    # Referee queries each party's own Keeper for that terminal's anchor chain.
    R.verify_claim_chain("A", incident_id=INC_001, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_001, keeper_name="Kc")

    # Phase 4: assessment
    R.query_fee_status(INC_001)
    R.issue_contribution_result(INC_001)
    R.notify_assessment_complete(INC_001)
    # appeal window expires → Keeper releases escrow → Referee acknowledges FEE_RECEIPT (RFC §6.24)
    Kc.release_fee(INC_001)
    Ka.release_fee(INC_001)
    R.send_fee_receipt(INC_001)

    # --- assertions: the verifiable outcome of a VERIFIED/VERIFIED honest flow ---
    print("\n--- assertions ---")
    # One assessment, all parties: both sides receive the SAME single verdict.
    for party in (A, C):
        rcv = world.last(party.name, "CONTRIBUTION_RESULT")
        assert rcv is not None, f"{party.name} received no CONTRIBUTION_RESULT"
        assert rcv["incident_id"] == INC_001
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), \
        "both parties must receive the same cert_id"
    # First assessment for this Referee → reputation snapshot count is 1 (§6.19).
    assert result["referee_reputation_snapshot"]["total_assessments"] == 1

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # Section 7 Verification Outcome Table: VERIFIED/VERIFIED → 0.5 / 0.5 / 0.0, HIGH.
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.5, 0.5, 0.0), \
        f"VERIFIED/VERIFIED must be 0.5/0.5/0.0, got {fault}"
    assert fault["confidence"] == "HIGH"
    # Fault is a distribution: the three shares always sum to 1.0 (§7, schema).
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0, \
        f"fault shares must sum to 1.0, got {fault}"
    assert verdict["technical_violation"] == [], "an honest flow has no technical violations"
    # The Referee assessed under exactly the declared Norm (§9.3).
    assert verdict["norms_used"] == ["rackp.standard.v1"], f"got {verdict['norms_used']}"
    # Each party's provenance ratios partition 1.0 (§8).
    for role in ("actor_provenance", "claimant_provenance"):
        p = verdict["provenance_score"][role]
        assert round(p["human_ratio"] + p["ai_ratio"], 10) == 1.0, f"{role} ratios must sum to 1.0, got {p}"
    # Both parties' evidence was verified against their Keepers (RFC-0002 §2.3).
    ep = result["evidence_provenance"]
    assert "VERIFIED" in ep and "FAILED" not in ep, f"both parties must verify, got: {ep}"

    # Evidence sufficiency (RFC §6.14): both chains are intact and adequately covered,
    # so the assessment is DEFINITIVE, not PROVISIONAL, with no detected gaps.
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "DEFINITIVE", f"got {es['assessment_status']}"
    assert es["actor_coverage"] not in ("UNKNOWN", "NONE", "LOW")
    assert es["claimant_coverage"] not in ("UNKNOWN", "NONE", "LOW")
    assert es["gaps"] == [], f"an honest chain has no gaps, got {es['gaps']}"

    # Fee compliance is disclosed only and never contaminates fault (STD-026): both deposited.
    fc = verdict["fee_compliance"]
    assert fc["actor_fee_status"] == "DEPOSITED" and fc["claimant_fee_status"] == "DEPOSITED", \
        f"both parties deposited, got {fc}"
    assert verdict["actor_participation"]["status"] == "ACKNOWLEDGED"

    # Split-Keeper release (STD-029): each Keeper releases only its own 100; sum == total.
    per_keeper = R._received_fees[INC_001]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, \
        f"each Keeper releases its own 100, got {per_keeper}"
    assert sum(per_keeper.values()) == 200, "released total must equal total deposited"
    # FEE_RECEIPT advances each released escrow to SETTLED.
    assert Kc._escrow[INC_001]["state"] == "SETTLED" and Ka._escrow[INC_001]["state"] == "SETTLED"

    print("[OK] same verdict to both parties; VERIFIED/VERIFIED -> 0.5/0.5/HIGH (sum 1.0);"
          " DEFINITIVE coverage, no gaps; fee disclosed, fault uncontaminated;"
          " 200 released across {Kc, Ka}; escrows SETTLED.")

if __name__ == "__main__":
    run()
