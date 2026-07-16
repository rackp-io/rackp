# edge_06_norm_mismatch.py
# RFC Section 5 (Phase 1-4): a full, base_01-conformant assessment in which the two
# parties declare Norms from DIFFERENT jurisdictions. The Actor declares a US automotive
# norm; the Claimant declares the JP automotive norm. Both otherwise participate honestly
# — they anchor, acknowledge, deposit their fees and submit genuine, verifiable evidence.
# The ONLY unusual feature is that their declared Norms share no common jurisdiction.
#
# How a jurisdiction mismatch is handled (§9.3, §9.5):
#   - The Referee does NOT invalidate the assessment, does NOT pick a "winning" Norm, and
#     does NOT silently fall back to the Standard Norm. It assesses, records BOTH declared
#     Norms in `norms_used` (read back from each party's declaration), and surfaces the
#     disagreement as a `norm_jurisdiction_mismatch` disclosure (§9.5). Choosing which
#     jurisdiction governs is the parties'/judicial layer's job — Norms live OUTSIDE the
#     protocol, so the Referee discloses the conflict rather than resolving it.
#   - The mismatch is disclosure only: it is NOT a `technical_violation` and it does NOT
#     move the fault. Both parties verified, so the fault is the honest 0.5/0.5/HIGH —
#     IDENTICAL to base_01. A jurisdictional disagreement is orthogonal to whether either
#     party deviated; it changes which standard applies, not who anchored what.
#   - Sim abstraction: evidence here is verified by anchor presence/hash (did the party
#     anchor what it submitted), not by mechanically applying each Norm's rule content
#     (which is the Norm authority's domain). So both VERIFY regardless of which Norm they
#     declared; the mismatch surfaces purely as the jurisdiction-metadata disclosure that
#     RACKP is responsible for — exactly the §9.5 obligation.
from classes.topology import standard_world

def run():
    # Same canonical topology as base_01 (Kr/Kc/Ka); the parties simply declare Norms
    # from different jurisdictions.
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario edge-06: Norm jurisdiction mismatch (disclosure only, §9.5) ===")
    INC_E06 = "0000e06a-0000-4000-8000-00000000e06a"
    ACTOR_NORM    = "us.nhtsa.automotive.v2"
    CLAIMANT_NORM = "jp.go.mlit.automotive.v1"

    # Phase 1: Norm declaration + evidence anchoring. The Actor declares a US automotive
    # Norm; the Claimant declares the JP automotive Norm — no common jurisdiction. Each
    # then anchors its own action honestly.
    A.session_start([{"norm_profile_id": ACTOR_NORM,    "norm_fetch_url": "https://norm.example/us-nhtsa-auto-v2.json"}])
    C.session_start([{"norm_profile_id": CLAIMANT_NORM, "norm_fetch_url": "https://norm.example/jp-mlit-auto-v1.json"}])
    A.act("lane_change", {"speed_kmh": 80, "signal_used": False})
    C.act("lane_change", {"speed_kmh": 80, "signal_used": True})

    # Phase 2: filing + fee deposit. The Claimant's ASSESSMENT_REQUEST carries its declared
    # Norm; the Actor's ACTOR_ACKNOWLEDGMENT carries its own — this is how the Referee
    # learns each party's Norm and detects that they are disjoint.
    C.deposit_fee(INC_E06, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E06)
    R.notify_actor("A", incident_id=INC_E06)
    R.notify_actor_named("A", incident_id=INC_E06)
    A.acknowledge(INC_E06)
    R.notify_actor_keeper_open(INC_E06)
    A.deposit_fee(INC_E06, amount=100, currency="USD")

    # Phase 3: evidence collection — both parties submit genuine evidence and verify.
    R.request_evidence("A", incident_id=INC_E06)
    A.submit_evidence(INC_E06)
    R.request_evidence("C", incident_id=INC_E06)
    C.submit_evidence(INC_E06)
    # Anchor-chain verification feeds evidence_sufficiency coverage (RFC §6.14); it also
    # reads each SESSION_START's declared Norm back from the chain, reinforcing the
    # mismatch detection. Both chains are intact (SESSION_START + act → MEDIUM).
    R.verify_claim_chain("A", incident_id=INC_E06, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E06, keeper_name="Kc")

    # Phase 4: assessment + settlement (identical orchestration to base_01).
    print("\n--- assessment ---")
    R.query_fee_status(INC_E06)
    R.issue_contribution_result(INC_E06)
    R.notify_assessment_complete(INC_E06)
    Kc.release_fee(INC_E06)
    Ka.release_fee(INC_E06)
    R.send_fee_receipt(INC_E06)

    # --- assertions: the mismatch is recorded and disclosed, never resolved or penalised ---
    print("\n--- assertions ---")
    # Both parties submitted genuine evidence and verified against their own Keepers.
    results = R._incidents[INC_E06]["results"]
    assert results.get(A.terminal_id) is True and results.get(C.terminal_id) is True, \
        f"both honest parties must verify, got {results}"

    # One assessment, delivered identically to both parties (RFC §6.14).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), "both parties must receive the same cert_id"

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # THE point (§9.5): the jurisdiction mismatch does NOT move the fault. Both parties
    # verified, so the fault is the honest 0.5/0.5/HIGH — IDENTICAL to base_01.
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.5, 0.5, 0.0), \
        f"a norm mismatch must not change fault, got {fault}"
    assert fault["confidence"] == "HIGH"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0
    # A jurisdiction disagreement is NOT an integrity/norm violation — there is no forged
    # hash and no broken rule to flag; it is a separate, dedicated disclosure field.
    assert verdict["technical_violation"] == [], \
        f"a norm mismatch is not a technical_violation, got {verdict['technical_violation']}"
    ep = result["evidence_provenance"]
    assert "VERIFIED" in ep and "FAILED" not in ep, f"both parties verified, got {ep}"

    # THE distinguishing feature: the Referee records BOTH declared Norms in norms_used
    # (never a fixed constant, never one party's pick) and surfaces the conflict as a
    # norm_jurisdiction_mismatch disclosure. This is the §9.3 declaration read-back plus
    # the §9.5 disclosure obligation working together.
    assert verdict["norms_used"] == sorted([ACTOR_NORM, CLAIMANT_NORM]), \
        f"both declared Norms must be recorded, got {verdict['norms_used']}"
    assert "norm_jurisdiction_mismatch" in verdict, \
        "a disjoint-Norm assessment must surface a norm_jurisdiction_mismatch disclosure"
    mismatch = verdict["norm_jurisdiction_mismatch"]
    assert ACTOR_NORM in mismatch and CLAIMANT_NORM in mismatch, \
        f"the disclosure must name both declared Norms, got: {mismatch}"

    # The mismatch did not degrade evidence quality: both chains are intact, so the
    # assessment is DEFINITIVE with MEDIUM coverage on both sides (the conflict is about
    # WHICH standard applies, not about the completeness of the record).
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "DEFINITIVE", f"intact chains -> DEFINITIVE, got {es['assessment_status']}"
    assert es["actor_coverage"] == "MEDIUM" and es["claimant_coverage"] == "MEDIUM", \
        f"got {es['actor_coverage']}/{es['claimant_coverage']}"
    assert es["gaps"] == [], f"honest chains have no gaps, got {es['gaps']}"

    # The mismatch is orthogonal to funding: both parties deposited, so fee_compliance
    # shows DEPOSITED and fees settle exactly as in base_01 (STD-026/029, RFC §6.24).
    fc = verdict["fee_compliance"]
    assert fc["actor_fee_status"] == "DEPOSITED" and fc["claimant_fee_status"] == "DEPOSITED", \
        f"both parties deposited, got {fc}"
    per_keeper = R._received_fees[INC_E06]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, f"got {per_keeper}"
    assert sum(per_keeper.values()) == 200, "released total must equal total deposited"
    assert Kc._escrow[INC_E06]["state"] == "SETTLED" and Ka._escrow[INC_E06]["state"] == "SETTLED"

    print("[OK] full base flow with a jurisdiction mismatch: A declared a US Norm, C the JP"
          " Norm (no common jurisdiction); both honest -> both VERIFIED -> 0.5/0.5/HIGH"
          " (fault UNCHANGED by the mismatch); the Referee recorded BOTH Norms in norms_used"
          " and disclosed a norm_jurisdiction_mismatch (§9.5) WITHOUT invalidating, picking a"
          " winner, or falling back to Standard; not a technical_violation; DEFINITIVE/MEDIUM;"
          " fee DEPOSITED; 200 settled across {Kc, Ka}.")

if __name__ == "__main__":
    run()
