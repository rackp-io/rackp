# base_08_withdrawal.py
# Both Actor and Claimant jointly withdraw before any assessment is issued.
# Expected: Referee accepts the withdrawal, MUST NOT issue a CONTRIBUTION_RESULT, and
#           each Keeper settles its escrow with the cancellation_fee only (no FEE_RELEASE).
# §6.17 (ASSESSMENT_WITHDRAWAL, cancellation-fee escrow settlement)
from classes.topology import standard_world

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world()

    print("=== Scenario 08: ASSESSMENT_WITHDRAWAL (mutual agreement) ===")
    INC_008 = "00000008-0000-4000-8000-000000000008"

    # Phase 1: Norm declaration + evidence anchoring
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("negotiate", {"offer_id": "OFF-001", "value": 500})
    C.act("negotiate", {"offer_id": "OFF-001", "value": 500})

    # Phase 2: filing + escrow. The handshake teaches the Referee each party's Keeper
    # (Kc from ASSESSMENT_REQUEST, Ka from ACTOR_ACKNOWLEDGMENT) so the later withdrawal
    # settlement can route to both, even though no evidence is ever submitted.
    print("\n--- filing + fee deposit ---")
    C.deposit_fee(INC_008, 100, "USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_008)
    R.notify_actor("A", incident_id=INC_008)
    R.notify_actor_named("A", incident_id=INC_008)
    A.acknowledge(INC_008)
    R.notify_actor_keeper_open(INC_008)
    A.deposit_fee(INC_008, 100, "USD")

    # Pre-assessment settlement: the parties reach an out-of-band agreement and submit a
    # co-signed ASSESSMENT_WITHDRAWAL. finalize_incident is never called.
    print("\n--- parties agree to withdraw ---")
    C.withdraw_assessment(INC_008, actor_name="A",
                          reason="Parties reached out-of-band settlement before assessment.")

    # --- assertions: withdrawal accepted, no verdict, cancellation-fee-only settlement ---
    print("\n--- assertions ---")
    # The Referee MUST NOT issue a CONTRIBUTION_RESULT to either party (RFC §6.17).
    assert world.last("C", "CONTRIBUTION_RESULT") is None, "no verdict may be issued on withdrawal"
    assert world.last("A", "CONTRIBUTION_RESULT") is None, "no verdict may be issued on withdrawal"
    # Each party's escrow settled as WITHDRAWN, with the cancellation fee only and the
    # remainder returned — and crucially NOT via a FEE_RELEASE (that path is for verdicts).
    for K in (Kc, Ka):
        e = K._escrow[INC_008]
        assert e["state"] == "WITHDRAWN", f"{K.name} escrow must be WITHDRAWN, got {e['state']}"
        assert e["cancellation_fee"] == 0.1, f"only the cancellation fee is taken, got {e['cancellation_fee']}"
        assert e["remainder"] == 99.9, f"the remainder returns to the depositor, got {e['remainder']}"
    assert world.last("R", "FEE_RELEASE") is None, "a withdrawal must not trigger FEE_RELEASE"

    print("[OK] withdrawal accepted; no CONTRIBUTION_RESULT; both escrows WITHDRAWN with"
          " cancellation_fee=0.1 only (remainder 99.9 returned); no FEE_RELEASE.")

if __name__ == "__main__":
    run()
