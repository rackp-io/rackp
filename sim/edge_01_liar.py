# edge_01_liar.py
# RFC Section 5 (Phase 1-4): a full, base_01-conformant assessment in which the Actor
# is a liar. Everything up to evidence submission is honest protocol participation —
# the Actor declares its Norm, anchors its real action, acknowledges the notification
# and deposits its fee, exactly like base_01. The lie is confined to ONE step (Phase 3
# evidence submission): the Actor submits an internally-consistent but FALSIFIED record
# whose stored_hash matches its own forged payload yet was never anchored to its Keeper.
#
# How the liar is handled (RFC §6.13, §7):
#   - The forged hash is the source of the lie, but the anchor is the source of TRUTH:
#     Keeper verification of that hash returns NOT_FOUND, so the Actor's evidence FAILS.
#   - FAILED(actor)/VERIFIED(claimant) → actor_fault=0.8, claimant_fault=0.2, MEDIUM (§7).
#   - The forgery is internally consistent (computed hash == self-reported hash), so it is
#     NOT a hash-discrepancy technical_violation — it is caught purely as a Keeper miss.
#   - Subtle point: the Actor's anchor CHAIN is intact (it really did anchor SESSION_START
#     + its action), so coverage is MEDIUM and the assessment is still DEFINITIVE. Honesty
#     is not measured by sufficiency; the lie surfaces in fault and evidence_provenance.
#   - The Referee still did its job, so fees settle exactly as in base_01: fault never
#     contaminates fee_compliance (STD-026), and both escrows reach SETTLED.
from classes.topology import standard_world
from scenario_actor.LiarActor import LiarActor


def run():
    # Same canonical topology as base_01 (Kr/Kc/Ka), but A is a LiarActor.
    world, R, A, C, Kr, Kc, Ka = standard_world(LiarActor)

    print("=== Scenario edge-01: Liar (tampered evidence over the full base flow) ===")
    INC_E01 = "0000e01a-0000-4000-8000-00000000e01a"

    # Phase 1: Norm declaration + evidence anchoring (the liar anchors its REAL action;
    # the forgery comes later, only at submission time).
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + fee deposit. The liar plays along with the protocol: it
    # acknowledges the notification and deposits its fee like any honest Actor.
    C.deposit_fee(INC_E01, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E01)
    R.notify_actor("A", incident_id=INC_E01)
    R.notify_actor_named("A", incident_id=INC_E01)
    A.acknowledge(INC_E01)
    R.notify_actor_keeper_open(INC_E01)
    A.deposit_fee(INC_E01, amount=100, currency="USD")

    # Phase 3: evidence collection. The liar (A) submits a forged hash; C submits honestly.
    R.request_evidence("A", incident_id=INC_E01)
    A.submit_evidence(INC_E01)   # LiarActor: forged stored_hash, never anchored → NOT_FOUND
    R.request_evidence("C", incident_id=INC_E01)
    C.submit_evidence(INC_E01)
    # Anchor-chain verification feeds evidence_sufficiency coverage (RFC §6.14). The liar's
    # chain is genuine (SESSION_START + move), so its coverage is intact — proving that
    # chain coverage and evidence verification are independent.
    R.verify_claim_chain("A", incident_id=INC_E01, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_E01, keeper_name="Kc")

    # Phase 4: assessment + settlement (identical orchestration to base_01).
    R.query_fee_status(INC_E01)
    R.issue_contribution_result(INC_E01)
    R.notify_assessment_complete(INC_E01)
    Kc.release_fee(INC_E01)
    Ka.release_fee(INC_E01)
    R.send_fee_receipt(INC_E01)

    # --- assertions: the forged evidence fails Keeper verification (RFC §6.13, §7) ---
    print("\n--- assertions ---")
    # The lie is caught at the Keeper: the liar's forged hash FAILS, the honest party verifies.
    results = R._incidents[INC_E01]["results"]
    assert results[A.terminal_id] is False, "the liar's forged hash must FAIL Keeper verification"
    assert results[C.terminal_id] is True,  "the honest party must verify"

    # One assessment, delivered identically to both parties (RFC §6.14).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), "both parties must receive the same cert_id"

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # FAILED(actor)/VERIFIED(claimant) → 0.8/0.2, MEDIUM; shares sum to 1.0 (RFC §7).
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.8, 0.2, 0.0), f"got {fault}"
    assert fault["confidence"] == "MEDIUM"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0
    # The forged payload is internally consistent (computed == self-reported hash), so it
    # is NOT a hash-discrepancy technical_violation — it is caught purely as a Keeper miss.
    assert verdict["technical_violation"] == [], f"detection is via Keeper miss, not discrepancy, got {verdict['technical_violation']}"
    ep = result["evidence_provenance"]
    assert "FAILED" in ep and "VERIFIED" in ep, f"one FAILED, one VERIFIED, got {ep}"

    # THE distinguishing point of this scenario: the liar's anchor CHAIN is intact
    # (SESSION_START + move → MEDIUM coverage), so the assessment is DEFINITIVE — yet the
    # SUBMITTED evidence still FAILED. Chain coverage ≠ evidence verification: anchoring a
    # chain does not rescue a forged submission whose hash is absent from that chain.
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "DEFINITIVE", f"intact chains -> DEFINITIVE, got {es['assessment_status']}"
    assert es["actor_coverage"] == "MEDIUM" and es["claimant_coverage"] == "MEDIUM", \
        f"two anchors each -> MEDIUM coverage, got {es['actor_coverage']}/{es['claimant_coverage']}"
    assert es["gaps"] == [], f"the liar's chain itself has no gaps, got {es['gaps']}"

    # Fault never contaminates fee compliance (STD-026): the liar still deposited, and that
    # is disclosed as-is — the 0.8 fault is the lie's only consequence, not a fee penalty.
    fc = verdict["fee_compliance"]
    assert fc["actor_fee_status"] == "DEPOSITED" and fc["claimant_fee_status"] == "DEPOSITED", \
        f"both parties deposited, got {fc}"
    assert verdict["actor_participation"]["status"] == "ACKNOWLEDGED", \
        "the liar participated (acknowledged); only its evidence was forged"

    # The Referee did its job, so fees settle exactly as in base_01 (STD-029, RFC §6.24):
    # each Keeper releases its own 100, and FEE_RECEIPT advances both escrows to SETTLED.
    per_keeper = R._received_fees[INC_E01]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, f"got {per_keeper}"
    assert sum(per_keeper.values()) == 200, "released total must equal total deposited"
    assert Kc._escrow[INC_E01]["state"] == "SETTLED" and Ka._escrow[INC_E01]["state"] == "SETTLED"

    print("[OK] full base flow with a liar: A acknowledged + deposited like an honest party,"
          " but its forged hash -> Keeper NOT_FOUND -> A FAILED / C VERIFIED -> 0.8/0.2/MEDIUM"
          " (sum 1.0); no technical_violation (caught by the anchor, not the self-report);"
          " chain intact (DEFINITIVE/MEDIUM) yet evidence FAILED; fee uncontaminated;"
          " 200 released across {Kc, Ka}; escrows SETTLED.")


if __name__ == "__main__":
    run()
