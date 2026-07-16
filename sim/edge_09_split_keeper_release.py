# edge_09_split_keeper_release.py
# STD-029: in a split-Keeper topology each Keeper releases ONLY the balance it holds,
# the amounts released across Keepers sum to the total deposited, and the Referee is
# never paid more than that total. The Claimant deposits 100 to Kc and the Actor
# deposits 100 to Ka (total escrow = 200 = the Referee's declared fee.amount). After
# assessment, Kc and Ka each release 100; the sum the Referee receives is exactly 200.
# Over-release is then shown to be impossible: a duplicate release is a no-op and a
# late FEE_CLAIM is rejected ALREADY_RELEASED, so the Referee's total never exceeds 200.
# RFC-0002 §1.6 (Guaranteed: sum released ≤ total deposited, no double payment); STD-029.
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

    print("=== Scenario edge_09: split-Keeper release accounting (STD-029) ===")
    INC = "00000029-0000-4000-8000-000000000029"

    R.publish_profile(keeper_name="Kr")

    # Phase 1: both parties declare and anchor to their own Keepers.
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    # Phase 2: split deposits — Claimant 100 → Kc, Actor 100 → Ka (total = fee.amount = 200).
    C.deposit_fee(INC, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC)
    R.notify_actor("A", incident_id=INC)
    R.notify_actor_named("A", incident_id=INC)
    A.acknowledge(INC)
    R.notify_actor_keeper_open(INC)
    A.deposit_fee(INC, amount=100, currency="USD")

    # Phase 3: evidence (also teaches the Referee each party's Keeper via keeper_map).
    R.request_evidence("A", incident_id=INC)
    A.submit_evidence(INC)
    R.request_evidence("C", incident_id=INC)
    C.submit_evidence(INC)

    # Phase 4: assessment + per-Keeper release.
    R.query_fee_status(INC)
    R.issue_contribution_result(INC)
    R.notify_assessment_complete(INC)
    print("\n--- per-Keeper release (each releases only the balance it holds) ---")
    Kc.release_fee(INC)
    Ka.release_fee(INC)

    # Over-release attempts: a duplicate release is a no-op; a late FEE_CLAIM is denied.
    print("\n--- over-release attempts (expect no-op / ALREADY_RELEASED) ---")
    Kc.release_fee(INC)          # already RELEASED → no second FEE_RELEASE
    R.claim_fee(INC)             # both Keepers already released → ALREADY_RELEASED

    R.send_fee_receipt(INC)

    # STD-029 invariants.
    deposited_total = sum(Kc._escrow[INC]["deposits"].values()) + sum(Ka._escrow[INC]["deposits"].values())
    per_keeper = R._received_fees[INC]["keepers"]
    received_total = sum(per_keeper.values())
    print(f"\n  deposited_total = {deposited_total} USD across {{Kc, Ka}}")
    print(f"  released_total  = {received_total} USD  per-Keeper={ {k: per_keeper[k] for k in per_keeper} }")
    assert sum(Kc._escrow[INC]["deposits"].values()) == 100 and sum(Ka._escrow[INC]["deposits"].values()) == 100, \
        "each Keeper holds only its own party's deposit"
    assert received_total == deposited_total == 200, \
        f"released sum ({received_total}) must equal total deposited ({deposited_total})"
    assert received_total <= deposited_total, "the Referee must never be paid more than the total deposited"
    # The over-release attempts were denied over the wire: the late FEE_CLAIM is rejected
    # ALREADY_RELEASED for every Keeper it reached, so the Referee's total cannot grow past 200.
    claim_results = world.all_of("R", "FEE_CLAIM_RESULT")
    assert claim_results and all(
        cr["status"] == "REJECTED" and cr["rejection_reason"] == "ALREADY_RELEASED"
        for cr in claim_results), f"a late FEE_CLAIM must be ALREADY_RELEASED, got {claim_results}"
    # FEE_RECEIPT was sent to both releasing Keepers → each advances RELEASED → SETTLED.
    assert Kc._escrow[INC]["state"] == "SETTLED" and Ka._escrow[INC]["state"] == "SETTLED", \
        f"got {Kc._escrow[INC]['state']}/{Ka._escrow[INC]['state']}"
    print("\n[OK] each Keeper released only its held balance; released sum == total"
          " deposited (200); over-release impossible (STD-029).")


if __name__ == "__main__":
    run()
