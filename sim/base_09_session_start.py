# base_09_session_start.py
# §9.3 (Norm declaration & "Referee obligation"), §9.5 (norms_used disclosure),
#           §4.1 (SESSION_START anchor)
# Distinct from base_01: both parties declare a NON-standard Norm Profile at session
# start. The Referee MUST read that declared Norm back from the anchor chain and report
# it in norms_used — which therefore differs from the rackp.standard.v1 default. This
# regression-locks the §9.3/§9.5 derivation: a hardcoded norms_used would wrongly report
# the Standard Norm here. base_01 cannot show this because its declared Norm happens to
# equal the default fallback.
from datetime import datetime, timedelta, timezone

from classes.topology import standard_world

# A non-default, domain-specific Norm both parties agree on. Deliberately NOT the
# Standard Norm, so norms_used must follow the declaration rather than the fallback.
NORM_PROFILE_ID = "rackp.robotics.navigation.v1"
NORM_FETCH_URL  = "https://rackp.example/norms/robotics-navigation-v1.json"
STANDARD_NORM   = "rackp.standard.v1"  # the §9.3 default — must NOT appear here

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario 09: SESSION_START / non-default Norm Declaration ===")
    INC_009 = "00000009-0000-4000-8000-000000000009"

    # Pre-incident: each party anchors its (non-standard) Norm Profile then acts.
    print("\n--- session start ---")
    A.session_start([{"norm_profile_id": NORM_PROFILE_ID, "norm_fetch_url": NORM_FETCH_URL}])
    A.act("navigate", {"destination": "zone_B"})
    C.session_start([{"norm_profile_id": NORM_PROFILE_ID, "norm_fetch_url": NORM_FETCH_URL}])
    C.act("observe",  {"target": "zone_B"})

    print("\n--- incident INC-009 ---")

    # Phase 2: filing + fee deposit (full handshake, matching base_01's completeness)
    C.deposit_fee(INC_009, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_009)
    R.notify_actor("A", incident_id=INC_009)
    R.notify_actor_named("A", incident_id=INC_009)
    A.acknowledge(INC_009)
    R.notify_actor_keeper_open(INC_009)
    A.deposit_fee(INC_009, amount=100, currency="USD")

    # Phase 3: evidence collection
    R.request_evidence("A", incident_id=INC_009)
    A.submit_evidence(INC_009)
    R.request_evidence("C", incident_id=INC_009)
    C.submit_evidence(INC_009)

    # R fetches anchor chains — includes SESSION_START anchors for norm detection
    R.verify_claim_chain("A", incident_id=INC_009, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_009, keeper_name="Kc")

    # Phase 4: assessment + full escrow settlement
    R.query_fee_status(INC_009)
    R.issue_contribution_result(INC_009)
    R.notify_assessment_complete(INC_009)
    Kc.release_fee(INC_009)
    Ka.release_fee(INC_009)
    R.send_fee_receipt(INC_009)

    # --- assertions: a non-default Norm is read from the chain and honored in norms_used ---
    print("\n--- assertions ---")
    A_tid, C_tid = A.terminal_id, C.terminal_id

    # The core: the Referee learns each party's declared Norm by reading its SESSION_START
    # anchor from the Keeper, not from any inline field.
    chain_results = world.all_of("R", "ANCHOR_CHAIN_RESULT")
    for tid in (A_tid, C_tid):
        anchors = next((m["anchors"] for m in chain_results if m["target_terminal_id"] == tid), [])
        ss = [a for a in anchors if a.get("action_type") == "SESSION_START"]
        assert ss, f"no SESSION_START anchor on record for {tid[:8]}..."
        ids = [p["norm_profile_id"] for a in ss for p in a.get("norm_profiles", [])]
        assert ids == [NORM_PROFILE_ID], f"SESSION_START must declare {NORM_PROFILE_ID}, got {ids}"
    # …and the Referee extracted those declarations into its incident state.
    declared = R._incidents[INC_009]["declared_norms"]
    assert declared.get(A_tid) == [NORM_PROFILE_ID] and declared.get(C_tid) == [NORM_PROFILE_ID], \
        f"Referee must extract both parties' declared Norm from SESSION_START, got {declared}"

    # Governing SESSION_START (§6.28): every query above used the sim's wide default
    # window, so the SESSION_START anchors surfaced IN-window and the result's
    # `session_start` field stayed null. Narrow the window to start AFTER everything
    # anchored so far: nothing is in-window, and the Keeper must instead attach the
    # most recent SESSION_START at or before range.start — the §9.3 declaration stays
    # readable without widening the window. This also drives the Referee's
    # session_start-field extraction branch (the wide queries only exercised the
    # in-window path). Post-verdict, so the narrowed coverage cannot disturb the
    # issued result. (The keeper integration suite pins the same branch over HTTP.)
    future_start = (datetime.now(timezone.utc) + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    R.verify_claim_chain("A", incident_id=INC_009, keeper_name="Ka",
                         range_start=future_start, range_end="2099-12-31T23:59:59Z")
    narrow = world.all_of("R", "ANCHOR_CHAIN_RESULT")[-1]
    assert narrow["target_terminal_id"] == A_tid and narrow["count"] == 0, \
        f"the narrowed window must contain no anchors, got count={narrow['count']}"
    gov = narrow["session_start"]
    assert gov is not None and gov.get("action_type") == "SESSION_START", \
        "the governing SESSION_START must be attached from before the window"
    assert [p["norm_profile_id"] for p in gov["norm_profiles"]] == [NORM_PROFILE_ID], \
        f"the governing declaration must carry {NORM_PROFILE_ID}, got {gov.get('norm_profiles')}"
    assert R._incidents[INC_009]["declared_norms"][A_tid] == [NORM_PROFILE_ID], \
        "the Referee must read the declaration from the governing session_start field too"

    # Both parties receive the same single verdict (RFC §6.14).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), "both parties must receive the same cert_id"

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # VERIFIED/VERIFIED honest flow → 0.5/0.5/0.0, HIGH; shares sum to 1.0 (RFC §7).
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.5, 0.5, 0.0), f"got {fault}"
    assert fault["confidence"] == "HIGH"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0

    # THE regression lock (RFC §9.3, §9.5): norms_used follows the DECLARED Norm, which is
    # non-standard here — so it must equal the declared profile and must NOT fall back to
    # the Standard Norm. A hardcoded norms_used would fail this assertion.
    assert verdict["norms_used"] == [NORM_PROFILE_ID], \
        f"norms_used must reflect the declared Norm, got {verdict['norms_used']}"
    assert STANDARD_NORM not in verdict["norms_used"], \
        "norms_used must NOT fall back to the Standard Norm when a Norm was declared"
    # Both declared the SAME Norm → assessed under it, with NO jurisdiction mismatch (§9.3).
    assert "norm_jurisdiction_mismatch" not in verdict, \
        f"matching Norms must not raise a mismatch, got {verdict.get('norm_jurisdiction_mismatch')}"

    # Anchor chains present (SESSION_START + action = 2 each) → DEFINITIVE, no gaps (RFC §6.14).
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "DEFINITIVE", f"got {es['assessment_status']}"
    assert es["actor_coverage"] == "MEDIUM" and es["claimant_coverage"] == "MEDIUM", \
        f"two anchors each -> MEDIUM coverage, got {es['actor_coverage']}/{es['claimant_coverage']}"
    assert es["gaps"] == [], f"consistent chains have no gaps, got {es['gaps']}"

    # Full settlement (matching base_01): each Keeper released its own 100, then FEE_RECEIPT
    # advanced both escrows to SETTLED (STD-029, RFC §6.24).
    per_keeper = R._received_fees[INC_009]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, f"got {per_keeper}"
    assert Kc._escrow[INC_009]["state"] == "SETTLED" and Ka._escrow[INC_009]["state"] == "SETTLED"

    print(f"[OK] non-default Norm {NORM_PROFILE_ID} read from SESSION_START anchors and"
          " honored in norms_used (no Standard-Norm fallback); no mismatch;"
          " VERIFIED/VERIFIED -> 0.5/0.5/HIGH; DEFINITIVE/MEDIUM coverage; escrows SETTLED;"
          " a narrowed window still yields the declaration via the governing session_start"
          " (S6.28).")

if __name__ == "__main__":
    run()
