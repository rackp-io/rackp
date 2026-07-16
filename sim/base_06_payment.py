# base_06_payment.py
# Two payment flows in one scenario.
#
# Act 1 — Pull-based payment under a DECLARED 50/50 split. The Referee sends FEE_CLAIM to
# each Keeper instead of waiting for push-based FEE_RELEASE (contrast base_01, push). Both
# parties deposit their declared half (STD-029 opt-in split), so each Keeper pays out 100.
#   RFC §6.22: Referee MAY send FEE_CLAIM (Referee → Keeper).
#   RFC §6.23: Keeper validates cert_id / appeal state / released state → FEE_CLAIM_RESULT(ACCEPTED).
#   RFC §6.24: Referee sends FEE_RECEIPT(triggered_by=FEE_CLAIM_RESULT) to settle escrow.
#
# Act 2 — DEFAULT allocation (requester pays full; Actor NOT_REQUIRED). A second Referee R2
# declares NO fee.deposit allocation, so the STD-029 default applies: the requesting party
# (the Claimant) bears the full fee.amount and the Actor owes nothing. The Actor is present
# and participates (acknowledges, submits evidence) — NOT_REQUIRED is about funding, not
# participation. Only the Claimant's Keeper holds escrow, so the full 200 settles from Kc
# alone. This is the post-STD-029 default; Act 1's 50/50 is the declared opt-in alternative.
from classes.topology import standard_world
from classes.Referee import Referee
from classes.Keeper import Keeper

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario 06: payment flows (pull FEE_CLAIM; requester-full default) ===")
    INC_006  = "00000006-0000-4000-8000-000000000006"
    INC_006B = "0000006b-0000-4000-8000-00000000006b"

    # ===================== Act 1: pull-based payment, declared 50/50 split =====================
    print("\n--- Act 1: pull-based FEE_CLAIM under a declared 50/50 split ---")
    # Phase 1: Norm declaration + evidence anchoring
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 3, "y": 4})
    C.act("move", {"x": 3, "y": 4})

    # Phase 2: filing + fee deposit (R declares a 50/50 split → each party deposits 100)
    C.deposit_fee(INC_006, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_006)
    R.notify_actor("A", incident_id=INC_006)
    R.notify_actor_named("A", incident_id=INC_006)
    A.acknowledge(INC_006)
    R.notify_actor_keeper_open(INC_006)
    A.deposit_fee(INC_006, amount=100, currency="USD")

    # Phase 3: evidence collection
    R.request_evidence("A", incident_id=INC_006)
    A.submit_evidence(INC_006)
    R.request_evidence("C", incident_id=INC_006)
    C.submit_evidence(INC_006)
    R.verify_claim_chain("A", incident_id=INC_006, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_006, keeper_name="Kc")

    # Phase 4: assessment — no FEE_RELEASE; Referee uses FEE_CLAIM (pull) instead
    R.query_fee_status(INC_006)
    R.issue_contribution_result(INC_006)
    R.notify_assessment_complete(INC_006)
    R.claim_fee(INC_006)          # pull: Referee claims payment from each party's Keeper (RFC §6.22)
    R.send_fee_receipt(INC_006)

    # --- assertions: pull-based payment via FEE_CLAIM, declared 50/50 ---
    print("\n--- Act 1 assertions ---")
    fault = world.last("C", "CONTRIBUTION_RESULT")["assessment"]["fault"]
    assert (fault["actor_fault"], fault["claimant_fault"]) == (0.5, 0.5) and fault["confidence"] == "HIGH"
    # Both deposited their declared half; fee_compliance shows DEPOSITED for both, 100 each.
    fc1 = world.last("C", "CONTRIBUTION_RESULT")["assessment"]["fee_compliance"]
    assert fc1["actor_fee_status"] == "DEPOSITED" and fc1["claimant_fee_status"] == "DEPOSITED", f"got {fc1}"
    assert fc1["fee_snapshot"]["claimant_expected"] == 100 and fc1["fee_snapshot"]["actor_expected"] == 100
    # The last FEE_CLAIM was accepted, and payment came via the pull path (not FEE_RELEASE).
    fcr = world.last("R", "FEE_CLAIM_RESULT")
    assert fcr is not None and fcr["status"] == "ACCEPTED"
    entry = R._received_fees[INC_006]
    assert entry["triggered_by"] == "FEE_CLAIM_RESULT", f"payment must be pull-based, got {entry['triggered_by']}"
    # Each Keeper paid out its own 100; the sum equals the total deposited (STD-029).
    assert entry["keepers"].get("Kc") == 100 and entry["keepers"].get("Ka") == 100
    assert sum(entry["keepers"].values()) == 200
    assert Kc._escrow[INC_006]["state"] == "SETTLED" and Ka._escrow[INC_006]["state"] == "SETTLED"
    # §6.24 receipt copy: Kr released nothing (escrow lives at Kc/Ka), yet reputation is
    # queried at Kr (§6.20) — so the Referee must copy its FEE_RECEIPT there, carrying the
    # incident total, and the copy closes the unreceived_count obligation opened by the
    # ASSESSMENT_ISSUED anchor.
    kr_receipts = world.all_of("Kr", "FEE_RECEIPT")
    assert len(kr_receipts) == 1, f"exactly one receipt copy at the Referee's own Keeper, got {len(kr_receipts)}"
    assert kr_receipts[0]["received_amount"] == 200, f"the copy carries the incident total, got {kr_receipts[0]['received_amount']}"
    C.query_referee_stats("R", keeper_name="Kr")
    stats = world.last("C", "REFEREE_STATS_RESULT")
    assert stats["unreceived_count"] == 0, \
        f"the receipt copy must close the obligation at Kr, got {stats['unreceived_count']}"
    print("[OK] Act 1: VERIFIED/VERIFIED -> 0.5/0.5/HIGH; pull-based FEE_CLAIM accepted at both"
          " Keepers (100+100=200); escrow SETTLED; receipt copy at Kr -> unreceived_count 0.")

    # ===================== Act 2: requester-full default (Actor NOT_REQUIRED) =====================
    print("\n--- Act 2: requester-full default allocation (Actor NOT_REQUIRED) ---")
    # A second Referee that declares NO fee.deposit allocation → STD-029 default: the
    # requester (Claimant) bears the full fee.amount and the Actor is NOT_REQUIRED.
    R2 = Referee("R2", keeper_name="Kr2")
    R2._fee_profile = {"amount": 200.0, "currency": "USD", "cancellation_fee": 0.1}
    Kr2 = Keeper("Kr2")
    world.register(R2)
    world.register(Kr2)
    R2.publish_profile(keeper_name="Kr2")

    # Phase 1: fresh actions for the new incident.
    A.act("move", {"x": 5, "y": 6})
    C.act("move", {"x": 5, "y": 6})

    # Phase 2: filing + fee deposit. The Claimant funds the FULL amount; the Actor
    # acknowledges and participates but deposits NOTHING — it is NOT_REQUIRED.
    C.deposit_fee(INC_006B, amount=200, currency="USD")          # requester bears the full fee
    C.send_assessment_request(actor_name="A", incident_id=INC_006B, referee_name="R2")
    R2.notify_actor("A", incident_id=INC_006B)
    R2.notify_actor_named("A", incident_id=INC_006B)
    A.acknowledge(INC_006B)
    R2.notify_actor_keeper_open(INC_006B)
    # (no A.deposit_fee — the Actor owes nothing under the requester-full default)

    # Phase 3: evidence collection — the Actor participates fully despite owing no deposit.
    R2.request_evidence("A", incident_id=INC_006B)
    A.submit_evidence(INC_006B)
    R2.request_evidence("C", incident_id=INC_006B)
    C.submit_evidence(INC_006B)
    R2.verify_claim_chain("A", incident_id=INC_006B, keeper_name="Ka")
    R2.verify_claim_chain("C", incident_id=INC_006B, keeper_name="Kc")

    # Phase 4: assessment + settlement. Only the Claimant's escrow (Kc) holds funds — the
    # full 200 — so it settles from Kc alone (push release).
    R2.query_fee_status(INC_006B)
    R2.issue_contribution_result(INC_006B)
    R2.notify_assessment_complete(INC_006B)
    Kc.release_fee(INC_006B)
    R2.send_fee_receipt(INC_006B)

    # --- assertions: requester-full default; Actor NOT_REQUIRED but participating ---
    print("\n--- Act 2 assertions ---")
    v2 = world.last("C", "CONTRIBUTION_RESULT")["assessment"]
    # Allocation never touches fault: both verified → 0.5/0.5/HIGH, exactly as in Act 1.
    assert (v2["fault"]["actor_fault"], v2["fault"]["claimant_fault"]) == (0.5, 0.5) and v2["fault"]["confidence"] == "HIGH"
    # THE point: under the requester-full default the Actor owes nothing → NOT_REQUIRED (not
    # NOT_DEPOSITED), and the Claimant is expected to fund the full amount.
    fc2 = v2["fee_compliance"]
    assert fc2["actor_fee_status"] == "NOT_REQUIRED", f"Actor owes nothing under the default, got {fc2['actor_fee_status']}"
    assert fc2["claimant_fee_status"] == "DEPOSITED", f"the requester funded the full amount, got {fc2['claimant_fee_status']}"
    assert fc2["fee_snapshot"]["claimant_expected"] == 200, f"requester expected the full amount, got {fc2['fee_snapshot']}"
    assert fc2["fee_snapshot"]["actor_expected"] == 0, f"Actor expected 0, got {fc2['fee_snapshot']}"
    # NOT_REQUIRED is about funding, not participation: the Actor was reached and acknowledged.
    assert v2["actor_participation"]["status"] == "ACKNOWLEDGED", \
        f"the Actor participated despite owing no deposit, got {v2['actor_participation']}"
    # Settlement: the full 200 came from the Claimant's Keeper alone; the Actor's Keeper
    # holds an INCIDENT_OPEN escrow shell with no funds and is never released.
    entry2 = R2._received_fees[INC_006B]
    assert entry2["keepers"].get("Kc") == 200 and "Ka" not in entry2["keepers"], f"only Kc funds the 200, got {entry2['keepers']}"
    assert sum(entry2["keepers"].values()) == 200, "the Referee receives the full 200 from the sole funder"
    assert sum(Ka._escrow[INC_006B].get("deposits", {}).values()) == 0, "the Actor's Keeper holds no funds"
    assert Kc._escrow[INC_006B]["state"] == "SETTLED", "the Claimant's escrow settles"
    # §6.24 receipt copy at the second Referee's own Keeper as well (push path this time).
    assert len(world.all_of("Kr2", "FEE_RECEIPT")) == 1, "R2 copies its receipt to Kr2"

    print("[OK] Act 2: requester-full default - Claimant funded the full 200, Actor"
          " NOT_REQUIRED (expected 0) yet ACKNOWLEDGED; fault still 0.5/0.5/HIGH;"
          " 200 settled from Kc alone; escrow SETTLED.")

if __name__ == "__main__":
    run()
