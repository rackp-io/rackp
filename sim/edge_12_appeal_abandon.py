# edge_12_appeal_abandon.py
# STD-028 (appeal branch): the Referee ACCEPTS an appeal, then vanishes without issuing
# the revised assessment. Accepting the appeal re-arms the assessment-deadline timer
# (Keeper APPEAL_ACCEPTED handler), so the now-undelivered revised assessment is again
# under a deadline. When it elapses, BOTH depositing parties reclaim their full deposits
# from their own Keepers and each escrow transitions to EXPIRED.
#
# This is the appeal-side counterpart to edge_08. edge_08 covers the timer on the INITIAL
# assessment (the Referee never issues anything). Here the Referee DID deliver an initial
# verdict and accepted an appeal against it — re-opening the obligation — then abandoned
# it. The crossing exercised is "APPEAL_ACCEPTED re-arms the timer -> EXPIRED via refund",
# the fund-protection backstop against a Referee that agrees to revise and then disappears.
#
# Structurally this is base_02 (appeal success) up to accept_appeal(); base_02 then issues
# the revised CONTRIBUTION_RESULT (deadline -> None, escrow eventually SETTLED). Here we
# stop at accept_appeal() and let the re-armed deadline elapse instead.
#   1. APPEAL_ACCEPTED re-arms the deadline (Kc/Ka escrow deadline is not None again).
#   2. Before the deadline elapses, FEE_REFUND_CLAIM is rejected DEADLINE_NOT_ELAPSED,
#      and the result still carries deadline_expires_at -> proves the timer was re-armed
#      (had the initial ASSESSMENT_COMPLETE's deadline=None still stood, the field would
#      be absent and a refund would never become claimable).
#   3. After expiry, each depositor's FEE_REFUND_CLAIM is ACCEPTED for the full amount and
#      its escrow -> EXPIRED. Split-Keeper: Kc refunds C, Ka refunds A, independently.
#   4. No double refund -> ALREADY_REFUNDED.
#   5. A late FEE_CLAIM by the (returning) Referee confers no payment right -> ESCROW_EXPIRED.
#   6. No revised verdict ever reached the parties: only the initial CONTRIBUTION_RESULT exists.
# RFC-0002 §1.6 (Guaranteed: EXPIRED transition); RFC-0001 §6.16 (appeal), §6.3 (timer reset);
# norms STD-028.
from classes.topology import standard_world
from scenario_actor.AppealActor import AppealActor


def run():
    world, R, A, C, Kr, Kc, Ka = standard_world(AppealActor)

    print("=== Scenario edge_12: Referee abandons after accepting an appeal (STD-028) ===")
    INC = "00000012-0000-4000-8000-000000000012"

    # Phase 1: Norm declaration + evidence anchoring (identical to base_02).
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: filing + both parties deposit (each to its own Keeper).
    C.deposit_fee(INC, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC)
    R.notify_actor("A", incident_id=INC)
    R.notify_actor_named("A", incident_id=INC)
    A.acknowledge(INC)
    R.notify_actor_keeper_open(INC)
    A.deposit_fee(INC, amount=100, currency="USD")

    # Phase 3: evidence (A submits falsified evidence as in base_02 -> FAILED).
    R.request_evidence("A", incident_id=INC)
    A.submit_evidence(INC)
    R.request_evidence("C", incident_id=INC)
    C.submit_evidence(INC)
    R.verify_claim_chain("A", incident_id=INC, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC, keeper_name="Kc")

    # Phase 4: initial assessment (actor FAILED, claimant VERIFIED -> 0.8/0.2). This delivers
    # a verdict, so ASSESSMENT_COMPLETE stops the deadline timer on both Keepers (deadline=None).
    print("\n--- initial assessment (delivered) ---")
    R.query_fee_status(INC)
    R.issue_contribution_result(INC)
    R.notify_assessment_complete(INC)

    # Appeal: A appeals with genuine evidence; the Referee verifies and ACCEPTS it. Accepting
    # re-opens the obligation to deliver a revised verdict, so the timer is re-armed.
    print("\n--- appeal accepted (re-arms the assessment-deadline timer) ---")
    A.file_appeal(use_real_evidence=True)          # A -> R: ASSESSMENT_APPEAL; R anchors APPEAL_RECEIVED (pending)
    R.request_evidence("C", incident_id=INC)       # appeal round, mirrors base_02
    C.submit_evidence(INC)
    R.verify_appeal_evidence(INC)                  # A's genuine evidence -> VERIFIED
    R.accept_appeal(INC)                           # R anchors APPEAL_ACCEPTED -> Kc/Ka re-arm deadline

    # --- The Referee now VANISHES: no issue_contribution_result(), no notify_assessment_complete().
    # The revised verdict is never delivered. ---

    # Invariant: APPEAL_ACCEPTED re-armed the timer on both Keepers (deadline back to non-None),
    # and neither escrow has been released. Without the re-arm the deadline would still be the
    # None left by the initial ASSESSMENT_COMPLETE and the deposits would be unrecoverable.
    assert Kc._escrow[INC]["deadline"] is not None, "APPEAL_ACCEPTED must re-arm Kc's deadline"
    assert Ka._escrow[INC]["deadline"] is not None, "APPEAL_ACCEPTED must re-arm Ka's deadline"
    assert Kc._escrow[INC]["state"] == "ESCROWED" and not Kc._escrow[INC]["released"]
    assert Ka._escrow[INC]["state"] == "ESCROWED" and not Ka._escrow[INC]["released"]

    # (1) Before the deadline elapses: a refund MUST be rejected, but the rejection carries
    # deadline_expires_at -> over-the-wire proof the timer is armed (re-armed by APPEAL_ACCEPTED).
    print("\n--- refund attempt before the re-armed deadline (expect DEADLINE_NOT_ELAPSED) ---")
    C.claim_refund(INC)
    A.claim_refund(INC)

    # Time passes with no revised assessment -> the re-armed deadline elapses on both Keepers.
    print("\n--- re-armed assessment deadline elapses ---")
    Kc.expire_assessment_timer(INC)
    Ka.expire_assessment_timer(INC)

    # (2) After expiry: each depositor reclaims its full deposit; each escrow -> EXPIRED.
    print("\n--- refund after deadline (expect ACCEPTED, 100 each, escrow EXPIRED) ---")
    C.claim_refund(INC)
    A.claim_refund(INC)

    # (3) No double refund (C tries again).
    print("\n--- second refund claim by C (expect ALREADY_REFUNDED) ---")
    C.claim_refund(INC)

    # (4) The Referee returns and tries to collect against the EXPIRED escrows -> no right.
    print("\n--- late FEE_CLAIM by the returning Referee (expect ESCROW_EXPIRED on both) ---")
    R.claim_fee(INC)

    # --- assertions: the appeal-abandon refund path, checked OVER THE WIRE. ---
    print("\n--- assertions: appeal abandoned after acceptance -> deposits recovered ---")

    # Claimant: pre-deadline REJECTED (with deadline_expires_at), post-deadline ACCEPTED 100,
    # then ALREADY_REFUNDED.
    c_refunds = world.all_of("C", "FEE_REFUND_RESULT")
    assert len(c_refunds) == 3, f"C made three refund attempts -> three results, got {len(c_refunds)}"
    assert c_refunds[0]["status"] == "REJECTED" and c_refunds[0]["rejection_reason"] == "DEADLINE_NOT_ELAPSED", \
        f"C pre-deadline refund must be DEADLINE_NOT_ELAPSED, got {c_refunds[0]}"
    assert "deadline_expires_at" in c_refunds[0], \
        "the pre-deadline rejection must carry deadline_expires_at -> proves APPEAL_ACCEPTED re-armed the timer"
    assert c_refunds[1]["status"] == "ACCEPTED" and c_refunds[1]["refunded_amount"] == 100, \
        f"C post-deadline refund must ACCEPT the full 100, got {c_refunds[1]}"
    assert c_refunds[2]["status"] == "REJECTED" and c_refunds[2]["rejection_reason"] == "ALREADY_REFUNDED", \
        f"C's second refund must be ALREADY_REFUNDED, got {c_refunds[2]}"

    # Actor: the appellant whose revision was abandoned reclaims its own deposit from Ka,
    # independently of the Claimant (split-Keeper). pre-deadline REJECTED, then ACCEPTED 100.
    a_refunds = world.all_of("A", "FEE_REFUND_RESULT")
    assert len(a_refunds) == 2, f"A made two refund attempts -> two results, got {len(a_refunds)}"
    assert a_refunds[0]["status"] == "REJECTED" and a_refunds[0]["rejection_reason"] == "DEADLINE_NOT_ELAPSED", \
        f"A pre-deadline refund must be DEADLINE_NOT_ELAPSED, got {a_refunds[0]}"
    assert "deadline_expires_at" in a_refunds[0], \
        "A's pre-deadline rejection must also carry deadline_expires_at (timer re-armed on Ka)"
    assert a_refunds[1]["status"] == "ACCEPTED" and a_refunds[1]["refunded_amount"] == 100, \
        f"A post-deadline refund must ACCEPT the full 100, got {a_refunds[1]}"

    # (5) Both late FEE_CLAIM results (one per Keeper) deny payment: the escrows are EXPIRED.
    claim_results = world.all_of("R", "FEE_CLAIM_RESULT")
    assert len(claim_results) == 2, f"claim_fee fans out to Kc and Ka -> two results, got {len(claim_results)}"
    assert all(cr["status"] == "REJECTED" and cr["rejection_reason"] == "ESCROW_EXPIRED" for cr in claim_results), \
        f"a late FEE_CLAIM on EXPIRED escrows must be ESCROW_EXPIRED on both, got {claim_results}"

    # (6) The Referee abandoned the revision: the appeal was accepted but no revised verdict
    # ever reached the parties. Only the single initial CONTRIBUTION_RESULT exists (contrast
    # base_02, which mints a second, revised verdict).
    c_verdicts = world.all_of("C", "CONTRIBUTION_RESULT")
    assert len(c_verdicts) == 1, \
        f"an abandoned appeal mints no revised verdict; only the initial exists, got {len(c_verdicts)}"

    # Invariants: both escrows EXPIRED, each depositor fully refunded, neither ever released.
    ec, ea = Kc._escrow[INC], Ka._escrow[INC]
    assert ec["state"] == "EXPIRED" and ea["state"] == "EXPIRED", \
        f"both escrows must be EXPIRED, got Kc={ec['state']} Ka={ea['state']}"
    assert ec["refunded"][C.terminal_id] == 100 and ea["refunded"][A.terminal_id] == 100, \
        "each depositor's full deposit must be refunded"
    assert not ec["released"] and not ea["released"], "an EXPIRED escrow must never have been released"

    print("\n[OK] APPEAL_ACCEPTED re-armed the deadline; the Referee abandoned the revision;"
          " both parties reclaimed their full 100 USD from their own Keepers (escrow EXPIRED);"
          " no double refund; late FEE_CLAIM denied (ESCROW_EXPIRED); no revised verdict minted.")


if __name__ == "__main__":
    run()
