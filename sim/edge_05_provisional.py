# edge_05_provisional.py
# RFC Section 5 (Phase 1-4): a full, base_01-conformant assessment in which the Actor
# participates in the PROCEDURE honestly — it is reached, acknowledges the notification
# and deposits its fee, exactly like base_01 — but it never anchored a single action to
# its Keeper. The ONLY deviation is the missing anchor trail: the Actor never called
# session_start or act, so its Keeper (Ka) holds zero anchors for it.
#
# How a missing anchor trail is handled (RFC-0001 §6.14, §7, RFC-0002 §2.3):
#   - The Actor has nothing genuine to submit (no anchored claim), so its EVIDENCE
#     submission is a no-op → it is treated as FAILED (RFC §7, the same rule that
#     penalises the silent Claimant in edge_02). FAILED(actor)/VERIFIED(claimant) →
#     0.8/0.2, MEDIUM (§7).
#   - The decisive, scenario-defining consequence is in evidence_sufficiency: the
#     Referee's ANCHOR_CHAIN_QUERY to Ka returns COUNT 0 → actor_coverage=NONE, so the
#     assessment_status is PROVISIONAL, not DEFINITIVE. There is no chain for the query
#     to surface — the Keeper-as-source-of-truth has nothing to offer.
#   - This is THE contrast with edge_01 (liar) and edge_02 (selective disclosure): in
#     BOTH of those the FAILED/silent party had still ANCHORED a chain, which the
#     ANCHOR_CHAIN_QUERY surfaced (MEDIUM coverage) → DEFINITIVE despite the evidence
#     failure. Here the Actor never anchored at all, so the same 0.8 fault is only
#     PROVISIONAL. The anchor trail — not payment, not acknowledgment — is what lets a
#     verdict be definitive.
#   - The deviation is isolated to anchoring: the Actor still acknowledged and still
#     deposited its fee, so actor_participation=ACKNOWLEDGED, fee_compliance shows
#     DEPOSITED, and fees settle exactly as in base_01 (200 across {Kc, Ka}).
from classes.topology import standard_world

def run():
    # Same canonical topology as base_01 (Kr/Kc/Ka); the Actor simply never anchors.
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario edge-05: PROVISIONAL verdict (Actor never anchored) ===")
    INC_E05 = "0000e05a-0000-4000-8000-00000000e05a"

    # Phase 1: Norm declaration + evidence anchoring. The Claimant anchors honestly
    # (SESSION_START + act → an intact chain). The Actor anchors NOTHING — no session_start,
    # no act — so its Keeper (Ka) will hold zero anchors for it. THIS is the deviation.
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.act("move", {"x": 1, "y": 2})
    # (no A.session_start, no A.act — the Actor never builds an anchor trail)
    #
    # STD-033: FEE_DEPOSIT is signed, and a terminal registers its key exclusively via
    # its own seq-1 CLAIM_ANCHOR (RFC-0001 §4.4) — so a genuinely zero-anchor Actor could
    # not produce a Ka-verifiable deposit in the real protocol. This scenario isolates the
    # anchor-coverage variable on purpose (fee deposit and evidence coverage are meant to
    # be independent axes, RFC-0002 §1.2.1), so the key is registered directly rather than
    # via an anchor — an anchor would give Ka a non-zero record and defeat the scenario.
    Ka._register_key(A.terminal_id, "PUBKEY_A")

    # Phase 2: filing + fee deposit. The Actor participates in the procedure like any honest
    # party: the Claimant deposits and files, the Actor is notified, acknowledges, and
    # deposits its own fee. Only the anchor trail is missing — everything else is base_01.
    C.deposit_fee(INC_E05, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_E05)
    R.notify_actor("A", incident_id=INC_E05)
    R.notify_actor_named("A", incident_id=INC_E05)
    A.acknowledge(INC_E05)
    R.notify_actor_keeper_open(INC_E05)
    A.deposit_fee(INC_E05, amount=100, currency="USD")

    # Phase 3: evidence collection. The Claimant submits its anchored work and verifies.
    # The Actor is asked too, but having anchored nothing it has nothing genuine to submit:
    # submit_evidence finds no _last_claim and sends NOTHING (a no-op) → the Actor records
    # no verification result and is treated as FAILED (RFC §7), exactly like edge_02's
    # silent party — but here the silence is forced by the absent trail, not chosen.
    R.request_evidence("A", incident_id=INC_E05)
    A.submit_evidence(INC_E05)   # no anchor on record → no EVIDENCE_SUBMISSION (no-op)
    R.request_evidence("C", incident_id=INC_E05)
    C.submit_evidence(INC_E05)
    # Anchor-chain verification feeds evidence_sufficiency coverage (RFC §6.14). The query
    # to Ka returns 0 anchors → actor_coverage=NONE; the query to Kc surfaces C's intact
    # chain → claimant_coverage=MEDIUM.
    R.verify_claim_chain("A", incident_id=INC_E05, keeper_name="Ka")  # → NONE (0 anchors)
    R.verify_claim_chain("C", incident_id=INC_E05, keeper_name="Kc")  # → MEDIUM (2 anchors)

    # Phase 4: assessment + settlement (identical orchestration to base_01; both deposited).
    R.query_fee_status(INC_E05)
    R.issue_contribution_result(INC_E05)
    R.notify_assessment_complete(INC_E05)
    Kc.release_fee(INC_E05)
    Ka.release_fee(INC_E05)
    R.send_fee_receipt(INC_E05)

    # --- assertions: a missing anchor trail makes the verdict PROVISIONAL ---
    print("\n--- assertions ---")
    # The Actor submitted nothing (no anchor to submit); the honest Claimant did. The
    # Actor therefore has NO verification result (like edge_02's silent party), while C
    # verifies against its Keeper.
    submissions = world.all_of("R", "EVIDENCE_SUBMISSION")
    submitters  = {m["submitter_id"] for m in submissions}
    assert A.terminal_id not in submitters, "the Actor has no anchor to submit -> no EVIDENCE_SUBMISSION"
    assert C.terminal_id in submitters,     "the honest Claimant must submit evidence"
    results = R._incidents[INC_E05]["results"]
    assert results.get(A.terminal_id) is None, "the Actor never submitted -> no verification result"
    assert results.get(C.terminal_id) is True, "the Claimant must verify"

    # One assessment, delivered identically to both parties (RFC §6.14).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and world.last("A", "CONTRIBUTION_RESULT") is not None
    assert (world.last("A", "CONTRIBUTION_RESULT")["assessment"]["certification"]["cert_id"]
            == result["assessment"]["certification"]["cert_id"]), "both parties must receive the same cert_id"

    verdict = result["assessment"]
    fault   = verdict["fault"]
    # A silent/unsubmitted party is treated as FAILED (RFC §7). FAILED(actor)/VERIFIED(claimant)
    # → 0.8/0.2, MEDIUM; shares sum to 1.0 (§7). The fault is identical to edge_01/edge_02;
    # what differs is the CONFIDENCE BASIS below.
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.8, 0.2, 0.0), \
        f"unsubmitted Actor must be FAILED, got {fault}"
    assert fault["confidence"] == "MEDIUM"
    assert round(fault["actor_fault"] + fault["claimant_fault"] + fault["external_factor"], 10) == 1.0
    # Not anchoring is not an integrity violation — there is no forged hash to flag.
    assert verdict["technical_violation"] == [], f"a missing trail is not a technical_violation, got {verdict['technical_violation']}"
    ep = result["evidence_provenance"]
    assert "VERIFIED" in ep, f"the honest Claimant must appear VERIFIED, got {ep}"

    # THE point of the scenario: with no anchor trail there is nothing for the
    # ANCHOR_CHAIN_QUERY to surface → actor_coverage=NONE → PROVISIONAL. This is the
    # razor contrast with edge_01 (liar) and edge_02 (selective): there the FAILED/silent
    # party had ANCHORED a chain (MEDIUM) → DEFINITIVE; here the empty chain caps the
    # Referee's confidence even though the fault value is the same 0.8.
    es = verdict["evidence_sufficiency"]
    assert es["assessment_status"] == "PROVISIONAL", \
        f"a NONE-coverage party must yield a PROVISIONAL verdict, got {es['assessment_status']}"
    assert es["actor_coverage"] == "NONE", \
        f"the Actor never anchored -> NONE coverage, got {es['actor_coverage']}"
    assert es["claimant_coverage"] == "MEDIUM", \
        f"the Claimant's intact chain -> MEDIUM coverage, got {es['claimant_coverage']}"
    # NONE means "no chain to inspect", which is not the same as a sequence gap WITHIN a
    # chain (LOW). With nothing anchored there is no gap to report.
    assert es["gaps"] == [], f"an absent chain reports no in-chain gap, got {es['gaps']}"
    # The Actor's empty chain is real at the Keeper: Ka holds zero anchors for it.
    ka_actor_anchors = [a for a in Ka.anchors.values() if a["terminal_id"] == A.terminal_id]
    assert ka_actor_anchors == [], f"Ka must hold no anchors for the Actor, got {len(ka_actor_anchors)}"

    # The deviation is isolated to anchoring: the Actor still acknowledged and still paid,
    # so participation/fee disclosure are UNAFFECTED — proving PROVISIONAL is driven by the
    # missing trail alone, not by non-participation or non-payment (STD-026, STD-030).
    assert verdict["actor_participation"]["status"] == "ACKNOWLEDGED", \
        f"the Actor participated; only its anchor trail is missing, got {verdict['actor_participation']}"
    fc = verdict["fee_compliance"]
    assert fc["actor_fee_status"] == "DEPOSITED" and fc["claimant_fee_status"] == "DEPOSITED", \
        f"both parties deposited, got {fc}"

    # Because both deposited, fees settle exactly as in base_01 (STD-029, RFC §6.24): each
    # Keeper releases its own 100, and FEE_RECEIPT advances both escrows to SETTLED. The
    # PROVISIONAL status concerns evidence sufficiency, never settlement.
    per_keeper = R._received_fees[INC_E05]["keepers"]
    assert per_keeper.get("Kc") == 100 and per_keeper.get("Ka") == 100, f"got {per_keeper}"
    assert sum(per_keeper.values()) == 200, "released total must equal total deposited"
    assert Kc._escrow[INC_E05]["state"] == "SETTLED" and Ka._escrow[INC_E05]["state"] == "SETTLED"

    print("[OK] full base flow, Actor never anchored: it acknowledged + paid like an honest"
          " party but built no anchor trail -> nothing to submit -> FAILED / C VERIFIED ->"
          " 0.8/0.2/MEDIUM (sum 1.0); no technical_violation; ANCHOR_CHAIN_QUERY to Ka"
          " returned 0 -> actor_coverage=NONE -> PROVISIONAL (the contrast with edge_01/02's"
          " DEFINITIVE); participation ACKNOWLEDGED, fee DEPOSITED; 200 settled across {Kc, Ka}.")

if __name__ == "__main__":
    run()
