# base_12_counter_assessment.py
# STD-020 end-to-end: a counter-assessment (re-assessment) as a NEW incident under a
# NEW incident_id.
#
# Round 1 — C files INC_A against A with Referee R (declared 50/50 split); both parties
# verify, the result issues, escrow releases and settles. A is dissatisfied.
#
# Round 2 — A seeks a second opinion (RFC-0001 §2.5): the SAME terminal that was the
# Actor of INC_A files as the CLAIMANT of a NEW incident INC_B with a different Referee
# R2, naming C as the Actor. Roles are per-incident; terminal identity, Keeper, and
# anchor chain are unchanged (SEQUENCE.md role-substitution table). Per STD-020 the
# initiating party bears the full deposit (R2 declares no allocation → STD-029
# requester-full default) and declares the original case via prior_incident_ids, so the
# results are linked (verified_prior_incidents → related_incident_ids).
#
# The point (issue #4): an incident_id is bound to ONE Referee for its lifetime
# (RFC-0001 §6.3, G1). A re-assessment therefore never re-opens the old incident_id —
# it is a new incident, so R2's INCIDENT_NOTICE(INCIDENT_OPEN) for INC_B is accepted by
# the same Keepers that hold the INC_A→R binding, and both bindings coexist.
# RFC-0002 §1.5 (STD-020), RFC-0001 §2.5, §6.2 (prior_incident_ids),
# §6.6 (verified_prior_incidents), §6.14 (related_incident_ids, prior_assessment_count)
from classes.topology import standard_world
from classes.Referee import Referee
from classes.Keeper import Keeper
from datetime import datetime, timezone

def run():
    world, R, A, C, Kr, Kc, Ka = standard_world()

    # Second Referee with its own Keeper. R2 declares NO fee.deposit allocation, so the
    # STD-029 default applies: the requesting party bears the full fee.amount and the
    # counterparty is NOT_REQUIRED — for a re-assessment this is exactly the STD-020
    # rule (the initiating party pays all; no share shifts to the opposing party).
    R2 = Referee("R2", keeper_name="Kr2")
    R2._fee_profile = {"amount": 200.0, "currency": "USD", "cancellation_fee": 0.1}
    Kr2 = Keeper("Kr2")
    world.register(R2)
    world.register(Kr2)
    R2.publish_profile(keeper_name="Kr2")

    print("=== Scenario 12: counter-assessment as a new incident (STD-020) ===")
    INC_A = "0000012a-0000-4000-8000-00000000012a"   # round 1: C vs A, Referee R
    INC_B = "0000012b-0000-4000-8000-00000000012b"   # round 2: A vs C, Referee R2 (new id)

    # ---------------- Round 1: standard assessment (C files against A with R) ----------------
    print("\n--- Round 1: INC_A - C files against A with R ---")
    A.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/rackp-standard-v1.json"}])
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/rackp-standard-v1.json"}])
    A.act("move", {"x": 1, "y": 2})
    C.act("move", {"x": 1, "y": 2})

    C.deposit_fee(INC_A, amount=100, currency="USD")     # R declares 50/50 → each owes 100
    C.send_assessment_request(actor_name="A", incident_id=INC_A)
    R.notify_actor("A", incident_id=INC_A)
    R.notify_actor_named("A", incident_id=INC_A)
    A.acknowledge(INC_A)
    R.notify_actor_keeper_open(INC_A)
    A.deposit_fee(INC_A, amount=100, currency="USD")

    R.request_evidence("A", incident_id=INC_A)
    A.submit_evidence(INC_A)
    R.request_evidence("C", incident_id=INC_A)
    C.submit_evidence(INC_A)
    R.verify_claim_chain("A", incident_id=INC_A, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_A, keeper_name="Kc")

    R.query_fee_status(INC_A)
    R.issue_contribution_result(INC_A)
    R.notify_assessment_complete(INC_A)
    Kc.release_fee(INC_A)
    Ka.release_fee(INC_A)
    R.send_fee_receipt(INC_A)

    round1 = world.last("A", "CONTRIBUTION_RESULT")
    assert round1 is not None and round1["incident_id"] == INC_A and round1["referee_id"] == R.terminal_id
    cert_a = round1["assessment"]["certification"]["cert_id"]

    # ---------------- Round 2: A's counter-assessment as a NEW incident with R2 ----------------
    print("\n--- Round 2: INC_B - A files as Claimant against C with R2 (new incident_id) ---")
    # Fresh actions to anchor the material each side will submit in INC_B.
    A.act("file_counter_claim", {"disputes": INC_A, "grounds": "norm_misapplication"})
    C.act("original_position", {"stands_by": INC_A})

    # STD-020: the initiating party bears the FULL deposit, at its own Keeper (Ka).
    A.deposit_fee(INC_B, amount=200, currency="USD")

    # The Actor terminal files as the Claimant of the new incident. The sim's Actor
    # class has no filing helper, so the ASSESSMENT_REQUEST is sent explicitly —
    # deliberately, to keep on record that this is the SAME terminal (same terminal_id,
    # same Keeper Ka, same anchor chain) occupying a different per-incident role.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    world.send("A", "R2", {
        "type":                  "ASSESSMENT_REQUEST",
        "incident_id":           INC_B,
        "claimant_id":           A.terminal_id,        # A is the Claimant of INC_B
        "actor_id":              C.terminal_id,        # C is the Actor of INC_B
        "actor_keeper_endpoint": "sim://Kc",
        "keeper_endpoint":       "sim://Ka",           # the filing party's own Keeper
        "incident_summary":      "Counter-assessment: disputes the INC_A result.",
        "incident_timestamp":    now,
        "prior_incident_ids":    [INC_A],              # STD-020 linkage (SHOULD)
        "norm_profile_ids":      ["rackp.standard.v1"],
        "timestamp":             now,
        "signature":             f"SIG_{A.terminal_id}"
    })
    R2.notify_actor("C", incident_id=INC_B)
    R2.notify_actor_named("C", incident_id=INC_B)
    # C (a Claimant-class terminal) has no acknowledge helper; the acknowledgment is
    # sent explicitly for the same reason as the request above — same terminal, new role.
    world.send("C", "R2", {
        "type":                  "ACTOR_ACKNOWLEDGMENT",
        "incident_id":           INC_B,
        "actor_id":              C.terminal_id,
        "actor_keeper_endpoint": "sim://Kc",
        "norm_profile_ids":      ["rackp.standard.v1"],
        "timestamp":             now,
        "signature":             f"SIG_{C.terminal_id}"
    })
    R2.notify_actor_keeper_open(INC_B)
    # (no C.deposit_fee — the counterparty of a re-assessment owes nothing, STD-020)

    # Sim convention: the first request_evidence target is the Actor (parties[0]),
    # the second the Claimant — in INC_B that means C first, then A (roles swapped).
    R2.request_evidence("C", incident_id=INC_B)
    C.submit_evidence(INC_B)
    R2.request_evidence("A", incident_id=INC_B)
    A.submit_evidence(INC_B)
    R2.verify_claim_chain("A", incident_id=INC_B, keeper_name="Ka")
    R2.verify_claim_chain("C", incident_id=INC_B, keeper_name="Kc")

    R2.query_fee_status(INC_B)
    R2.issue_contribution_result(INC_B)
    R2.notify_assessment_complete(INC_B)
    Ka.release_fee(INC_B)
    R2.send_fee_receipt(INC_B)

    # ---------------- assertions ----------------
    print("\n--- assertions ---")

    # 1) G1 binding coexistence (issue #4): each incident_id is bound to exactly one
    #    Referee for its lifetime, and a re-assessment never re-opens the old id — so
    #    the SAME Keepers hold both bindings side by side, and every R2 message for
    #    INC_B was accepted (no DELIVERY_REJECTION) despite the INC_A→R binding.
    assert Ka._incident_referee[INC_A] == R.terminal_id, "INC_A stays bound to R at Ka"
    assert Ka._incident_referee[INC_B] == R2.terminal_id, "INC_B binds to R2 at Ka"
    assert Kc._incident_referee[INC_A] == R.terminal_id, "INC_A stays bound to R at Kc"
    assert Kc._incident_referee[INC_B] == R2.terminal_id, "INC_B binds to R2 at Kc"
    rejections = world.all_of("R2", "DELIVERY_REJECTION")
    assert not rejections, f"no R2 message may be rejected under the new-incident form, got {rejections}"

    # 2) The counter-result is a normal FIRST assessment of a NEW incident: its
    #    prior_assessment_count is 0 (same-id priors are appeal rounds only, §6.14),
    #    while the STD-020 linkage to INC_A travels as related_incident_ids.
    round2 = world.last("A", "CONTRIBUTION_RESULT")
    assert round2["incident_id"] == INC_B and round2["referee_id"] == R2.terminal_id
    assert round2["prior_assessment_count"] == 0, \
        f"a re-assessment is a NEW incident, not a same-id continuation, got {round2['prior_assessment_count']}"
    assert round2.get("related_incident_ids") == [INC_A], \
        f"the declared prior incident must be disclosed, got {round2.get('related_incident_ids')}"
    # The linkage was VERIFIED by the party Keepers, which hold INC_A's completion
    # notice: verified_prior_incidents carries INC_A with its cert_id (§6.6).
    vpi = R2._fee_status[INC_B]["verified_prior_incidents"]
    assert vpi and vpi[0]["incident_id"] == INC_A and vpi[0]["verified"] is True
    assert vpi[0]["cert_id"] == cert_a, f"linkage resolves to INC_A's cert, got {vpi[0]}"

    # 3) Role swap without identity change: the same terminals appear in swapped
    #    per-incident roles, and BOTH results now sit side by side at the same party —
    #    RFC-0001 §2.5: humans weigh the independently produced results; divergence is
    #    information, not error.
    results_at_A = world.all_of("A", "CONTRIBUTION_RESULT")
    assert {r["incident_id"] for r in results_at_A} == {INC_A, INC_B}, \
        "A holds both the original and the counter result"
    assert round1["referee_id"] != round2["referee_id"], "independently produced by different Referees"

    # 4) STD-020 economics: the initiating party (A) funded the full 200 at its own
    #    Keeper; the counterparty (C) owes nothing → NOT_REQUIRED, not NOT_DEPOSITED.
    fc = round2["assessment"]["fee_compliance"]
    assert fc["claimant_fee_status"] == "DEPOSITED", f"the initiator (Claimant of INC_B) funded, got {fc}"
    assert fc["actor_fee_status"] == "NOT_REQUIRED", f"the counterparty owes nothing (STD-020), got {fc}"
    assert fc["fee_snapshot"]["claimant_expected"] == 200 and fc["fee_snapshot"]["actor_expected"] == 0
    entry2 = R2._received_fees[INC_B]
    assert entry2["keepers"].get("Ka") == 200 and "Kc" not in entry2["keepers"], \
        f"the full 200 comes from the initiator's Keeper alone, got {entry2['keepers']}"

    # 5) Escrow independence: INC_A's settled escrow is untouched by round 2, and
    #    INC_B settles as its own record — no cross-incident interference (contrast the
    #    pre-fix same-id form, where the round-2 deposit entered the already-released
    #    INC_A escrow with no release or refund path).
    assert Ka._escrow[INC_A]["state"] == "SETTLED" and Ka._escrow[INC_B]["state"] == "SETTLED"
    assert Ka._escrow[INC_A]["deposits"] == {A.terminal_id: 100}
    assert Ka._escrow[INC_B]["deposits"] == {A.terminal_id: 200}
    assert sum(Kc._escrow[INC_B].get("deposits", {}).values()) == 0, "the counterparty's Keeper holds no INC_B funds"

    print("[OK] counter-assessment ran end-to-end as a NEW incident: bindings for INC_A(R)"
          " and INC_B(R2) coexist at Ka/Kc with no rejection; prior_assessment_count=0 with"
          " related_incident_ids=[INC_A] verified via the Keepers; the initiator funded 200"
          " alone (counterparty NOT_REQUIRED); both escrows settled independently.")

if __name__ == "__main__":
    run()
