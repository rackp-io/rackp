# edge_02_selective.py
# RFC Section 5 (Phase 1-4): a full, base_01-conformant assessment in which the
# Claimant practises SELECTIVE DISCLOSURE. The Claimant files the incident and pays
# its fee like any honest party, and it anchors its own action — but when the Referee
# asks for that action as evidence, it stays silent, hoping to withhold an unfavorable
# record. The honest Actor, by contrast, both anchors and submits.
#
# How selective disclosure is handled (RFC §6.13, §6.14, §7):
#   - Withholding evidence is NOT rewarded: a queried party that submits nothing is
#     treated as FAILED (RFC §7, symmetric for Actor and Claimant). A silent filing
#     party is NOT credited by default — so VERIFIED(actor)/silent(claimant) →
#     actor_fault=0.2, claimant_fault=0.8, MEDIUM.
#   - Withholding does not actually HIDE anything: the Referee's ANCHOR_CHAIN_QUERY to
#     the Claimant's Keeper still surfaces the very anchors it declined to submit, so
#     its coverage is MEDIUM and the assessment is DEFINITIVE. The Keeper, not the
#     party's submission, is the source of truth about what was anchored.
#   - The lie is in disclosure, not funding: the Claimant still deposited its fee, so
#     fee_compliance shows DEPOSITED and fees settle exactly as in base_01.
from classes.topology import standard_world
from scenario_actor.SelectiveClaimant import SelectiveClaimant

def run():
    # Same canonical topology as base_01 (Kr/Kc/Ka), but C is a SelectiveClaimant.
    world, R, A, C, Kr, Kc, Ka = standard_world(claimant_cls=SelectiveClaimant)

    print("=== Scenario edge-02: Selective disclosure over the full base flow ===")
    INC_E02 = "0000e02a-0000-4000-8000-00000000e02a"

    # Phase 1: Norm declaration + evidence anchoring. The selective Claimant anchors its
    # action here — the very record it will later refuse to submit.
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + fee deposit. The selective Claimant files and pays normally —
    # the withholding is confined to the evidence step in Phase 3.
    C.deposit_fee(INC_E02, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E02)
    R.notify_actor("A", incident_id=INC_E02)
    R.notify_actor_named("A", incident_id=INC_E02)
    A.acknowledge(INC_E02)
    R.notify_actor_keeper_open(INC_E02)
    A.deposit_fee(INC_E02, amount=100, currency="USD")

    # Phase 3: evidence collection. Honest Actor submits and verifies; selective Claimant
    # ignores the EVIDENCE_QUERY_REQUEST (no EVIDENCE_SUBMISSION) — but its anchors remain
    # visible to the Referee via the Keeper's anchor-chain query.
    R.request_evidence("A", incident_id=INC_E02)
    A.submit_evidence(INC_E02)
    R.request_evidence("C", incident_id=INC_E02)
    C.submit_evidence(INC_E02)   # SelectiveClaimant never queued the query → no-op
    R.verify_claim_chain("A", incident_id=INC_E02, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E02, keeper_name="Kc")  # surfaces withheld anchors

    # Phase 4: assessment + settlement (identical orchestration to base_01).
    R.query_fee_status(INC_E02)
    R.issue_contribution_result(INC_E02)
    R.notify_assessment_complete(INC_E02)
    Kc.release_fee(INC_E02)
    Ka.release_fee(INC_E02)
    R.send_fee_receipt(INC_E02)

    # --- assertions: anchoring is visible even when submission is withheld ---
    print("\n--- assertions ---")
    # The selective Claimant submitted nothing; the honest Actor did.
    submissions = world.all_of("R", "EVIDENCE_SUBMISSION")
    submitters  = {m["submitter_id"] for m in submissions}
    assert C.terminal_id not in submitters, "the selective Claimant must NOT submit evidence"
    assert A.terminal_id in submitters,     "the honest Actor must submit evidence"
    # The honest Actor's submission verifies against its Keeper; the silent Claimant has no
    # verification result recorded at all (it never submitted).
    results = R._incidents[INC_E02]["results"]
    assert results.get(A.terminal_id) is True, "Actor must verify"
    assert results.get(C.terminal_id) is None, "the silent Claimant has no verification result"

    # One assessment, delivered identically to both parties (RFC §6.14).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), "both parties must receive the same cert_id"

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # THE regression lock (RFC §7): a silent filing party is treated as FAILED, NOT credited
    # by default. VERIFIED(actor)/silent(claimant) → 0.2/0.8, MEDIUM; shares sum to 1.0.
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.2, 0.8, 0.0), \
        f"withholding must penalise the silent party, got {fault}"
    assert fault["confidence"] == "MEDIUM"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0
    # Non-submission is not an integrity violation — there is no forged hash to flag.
    assert verdict["technical_violation"] == [], f"withholding is not a technical_violation, got {verdict['technical_violation']}"
    ep = result["evidence_provenance"]
    assert "VERIFIED" in ep, f"the honest Actor must appear VERIFIED, got {ep}"

    # THE point of the scenario: withholding hides nothing. The anchor-chain query surfaces
    # the Claimant's anchors at the Keeper despite non-submission, so its coverage is MEDIUM
    # and the assessment is still DEFINITIVE. The party DID anchor work it chose not to send.
    chains  = world.all_of("R", "ANCHOR_CHAIN_RESULT")
    c_chain = next((m for m in chains if m["target_terminal_id"] == C.terminal_id), None)
    assert c_chain is not None and c_chain["count"] >= 2, \
        "ANCHOR_CHAIN_QUERY must surface the Claimant's anchors despite non-submission"
    coverage = R._incidents[INC_E02]["anchor_coverage"]
    assert coverage[C.terminal_id]["count"] >= 2, "Claimant coverage is recorded from the anchor chain"
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "DEFINITIVE", f"surfaced anchors -> DEFINITIVE, got {es['assessment_status']}"
    assert es["claimant_coverage"] == "MEDIUM", \
        f"the withheld anchors are still counted as coverage, got {es['claimant_coverage']}"
    assert es["gaps"] == [], f"the Claimant's chain itself has no gaps, got {es['gaps']}"

    # The lie is in disclosure, not funding: the Claimant still deposited, so fee_compliance
    # shows DEPOSITED, and fees settle exactly as in base_01 (STD-026/029, RFC §6.24).
    fc = verdict["fee_compliance"]
    assert fc["actor_fee_status"] == "DEPOSITED" and fc["claimant_fee_status"] == "DEPOSITED", \
        f"both parties deposited, got {fc}"
    per_keeper = R._received_fees[INC_E02]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, f"got {per_keeper}"
    assert sum(per_keeper.values()) == 200, "released total must equal total deposited"
    assert Kc._escrow[INC_E02]["state"] == "SETTLED" and Ka._escrow[INC_E02]["state"] == "SETTLED"

    print("[OK] full base flow with selective disclosure: silent Claimant filed + paid but"
          " withheld its evidence -> treated as FAILED, NOT credited -> 0.2/0.8/MEDIUM (sum 1.0);"
          " ANCHOR_CHAIN_QUERY surfaced its anchors anyway (DEFINITIVE/MEDIUM, hides nothing);"
          " fee disclosed DEPOSITED; 200 released across {Kc, Ka}; escrows SETTLED.")

if __name__ == "__main__":
    run()
