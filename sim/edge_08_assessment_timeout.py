# edge_08_assessment_timeout.py
# STD-028: assessment-deadline timeout → FEE_REFUND_CLAIM → full refund → escrow EXPIRED.
# The Claimant deposits and opens the incident, but the Referee never issues an
# ASSESSMENT_COMPLETE. Once the deadline elapses the Claimant reclaims its full
# deposit (no cancellation fee) and the escrow transitions to EXPIRED. The norm's
# guarantees are exercised end to end:
#   1. The Keeper MUST NOT refund before the deadline elapses → DEADLINE_NOT_ELAPSED.
#   2. After expiry, FEE_REFUND_CLAIM is ACCEPTED for the full amount, escrow → EXPIRED.
#   3. No double refund → a second claim is rejected ALREADY_REFUNDED.
#   4. A late FEE_CLAIM after EXPIRED confers no payment right → ESCROW_EXPIRED.
# RFC-0002 §1.6 (Guaranteed: EXPIRED transition, no double refund); norms STD-028.
from classes.World import World
from classes.Actor import Actor
from classes.Claimant import Claimant
from classes.Referee import Referee
from classes.Keeper import Keeper


def run():
    world = World()
    R  = Referee("R",  keeper_name="Kr")
    A  = Actor("A",    keeper_name="Ka")
    C  = Claimant("C", keeper_name="Kc")
    Kr = Keeper("Kr")
    Kc = Keeper("Kc")
    Ka = Keeper("Ka")
    for agent in [R, A, C, Kr, Kc, Ka]:
        world.register(agent)

    print("=== Scenario edge_08: assessment-deadline timeout refund (STD-028) ===")
    INC = "00000028-0000-4000-8000-000000000028"

    R.publish_profile(keeper_name="Kr")

    # Phase 1-2: Claimant declares, anchors, deposits, and opens the incident.
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.act("move", {"x": 1, "y": 2})
    C.deposit_fee(INC, amount=100, currency="USD")          # → Kc escrow, timer armed
    C.send_assessment_request(actor_name="A", incident_id=INC)  # → INCIDENT_OPEN to Kc

    # Phase 3: Claimant submits evidence (lets the Referee learn Kc for any later FEE_CLAIM).
    R.request_evidence("C", incident_id=INC)
    C.submit_evidence(INC)

    # --- The Referee stalls: no CONTRIBUTION_RESULT, no ASSESSMENT_COMPLETE. ---

    # (1) Before the deadline: a refund claim MUST be rejected.
    print("\n--- refund attempt before deadline (expect DEADLINE_NOT_ELAPSED) ---")
    C.claim_refund(INC)

    # Time passes with no assessment completion → the deadline elapses.
    print("\n--- assessment deadline elapses ---")
    Kc.expire_assessment_timer(INC)

    # (2) After expiry: full refund, escrow → EXPIRED.
    print("\n--- refund claim after deadline (expect ACCEPTED, 100 USD, escrow EXPIRED) ---")
    C.claim_refund(INC)

    # (3) No double refund.
    print("\n--- second refund claim (expect ALREADY_REFUNDED) ---")
    C.claim_refund(INC)

    # (4) A late FEE_CLAIM against the EXPIRED escrow confers no payment right.
    print("\n--- late FEE_CLAIM after EXPIRED (expect ESCROW_EXPIRED) ---")
    R.claim_fee(INC)

    # --- result-message assertions: the four guarantees checked OVER THE WIRE, not just
    # via the final escrow state. FEE_REFUND_RESULT is returned to the Claimant for each
    # claim_refund; FEE_CLAIM_RESULT to the Referee for the late claim_fee. ---
    refunds = world.all_of("C", "FEE_REFUND_RESULT")
    assert len(refunds) == 3, f"three refund attempts -> three results, got {len(refunds)}"
    # (1) before the deadline: the Keeper MUST NOT refund.
    assert refunds[0]["status"] == "REJECTED" and refunds[0]["rejection_reason"] == "DEADLINE_NOT_ELAPSED", \
        f"pre-deadline refund must be DEADLINE_NOT_ELAPSED, got {refunds[0]}"
    # (2) after expiry: the full deposit is refunded, with no cancellation fee.
    assert refunds[1]["status"] == "ACCEPTED" and refunds[1]["refunded_amount"] == 100, \
        f"post-deadline refund must ACCEPT the full 100, got {refunds[1]}"
    # (3) no double refund.
    assert refunds[2]["status"] == "REJECTED" and refunds[2]["rejection_reason"] == "ALREADY_REFUNDED", \
        f"second refund must be ALREADY_REFUNDED, got {refunds[2]}"
    # (4) a late FEE_CLAIM against the EXPIRED escrow confers no payment right.
    claim_res = world.last("R", "FEE_CLAIM_RESULT")
    assert claim_res is not None and claim_res["status"] == "REJECTED" \
        and claim_res["rejection_reason"] == "ESCROW_EXPIRED", \
        f"late FEE_CLAIM on an EXPIRED escrow must be ESCROW_EXPIRED, got {claim_res}"

    # Invariants check (in-process, not over the wire).
    entry = Kc._escrow[INC]
    assert entry["state"] == "EXPIRED", f"escrow must be EXPIRED, got {entry['state']}"
    assert entry["refunded"][C.terminal_id] == 100, "full deposit must be refunded"
    assert not entry["released"], "an EXPIRED escrow must never have been released"
    print("\n[OK] escrow EXPIRED; full 100 USD refunded with no cancellation fee;"
          " no double refund; late FEE_CLAIM denied (STD-028).")


if __name__ == "__main__":
    run()
