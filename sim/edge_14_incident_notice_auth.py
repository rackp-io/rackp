# edge_14_incident_notice_auth.py
# G1: INCIDENT_NOTICE drives escrow transitions (release, appeal hold, and
# withdrawal settlement), so it is signed and the Keeper authenticates it before
# acting. A Keeper endpoint is public, so without this any party could POST a
# forged notice — e.g. ASSESSMENT_WITHDRAWN, which skims a cancellation fee and
# force-returns the remainder, cancelling a live assessment. This scenario pins:
#   1. a notice from a Referee whose key the Keeper does NOT hold -> UNKNOWN_TERMINAL;
#   2. the incident binds to the referee_id of the first accepted notice;
#   3. a forged ASSESSMENT_WITHDRAWN from a DIFFERENT Referee (even one whose key IS
#      registered) -> PROTOCOL_REJECTED, and the escrow is untouched;
#   4. the legitimate Referee's ASSESSMENT_WITHDRAWN settles normally.
import uuid
from datetime import datetime, timezone
from classes.World import World
from classes.Referee import Referee
from classes.Keeper import Keeper


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run():
    world = World()
    Ka  = Keeper("Ka")                    # a party's Keeper, holding the Actor's deposit
    R   = Referee("R",   keeper_name="Kr")  # the legitimate Referee for the incident
    Evil = Referee("Evil", keeper_name="KEvil")  # another Referee, unrelated to this incident
    for ag in [Ka, R, Evil]:
        world.register(ag)

    print("=== Scenario edge_14: INCIDENT_NOTICE authentication + binding (G1) ===")
    INC = "000000ee-0000-4000-8000-0000000000ee"
    ACTOR = str(uuid.uuid4())

    def notice(ref, event, **extra):
        n = {
            "type": "INCIDENT_NOTICE", "incident_id": INC, "referee_id": ref.terminal_id,
            "recipient_id": Ka.terminal_id, "event_type": event,
            "timestamp": now(), "signature": f"SIG_{ref.terminal_id}",
        }
        n.update(extra)
        return n

    # The Actor has deposited into Ka's escrow (so a forged withdrawal would have
    # something to skim). This scenario is about INCIDENT_NOTICE auth, not Actor
    # onboarding, so register the Actor's key directly rather than anchoring first
    # (STD-033: FEE_DEPOSIT is signed and Ka verifies depositor_id before crediting).
    Ka._register_key(ACTOR, "PUBKEY_ACTOR")
    world.send(ACTOR, "Ka", {
        "type": "FEE_DEPOSIT", "incident_id": INC, "depositor_id": ACTOR,
        "amount": 100, "currency": "USD", "timestamp": now(),
        "signature": f"SIG_{ACTOR}",
    })
    assert sum(Ka._escrow[INC]["deposits"].values()) == 100

    # --- (1) a notice from a Referee whose key Ka does not hold is undeliverable ---
    print("\n--- INCIDENT_OPEN from a Referee Ka holds no key for ---")
    assert not Ka._can_verify(R.terminal_id), "Ka has not yet received R's profile"
    world.send(R.name, "Ka", notice(R, "INCIDENT_OPEN", assessment_deadline_hours=720))
    rej = world.last("R", "DELIVERY_REJECTION")
    assert rej is not None and rej["reason"] == "UNKNOWN_TERMINAL", \
        f"unverifiable notice -> UNKNOWN_TERMINAL, got {rej}"
    assert INC not in Ka._incident_referee, "an unverified notice must not bind the incident"

    # --- (2) R publishes its profile, then a signed INCIDENT_OPEN binds the incident ---
    print("\n--- R publishes its profile, then opens the incident ---")
    R._send_profile("Ka")                 # G2 channel: Ka now holds R's key
    world.send(R.name, "Ka", notice(R, "INCIDENT_OPEN", assessment_deadline_hours=720))
    assert Ka._incident_referee.get(INC) == R.terminal_id, "the incident binds to R (first accepted notice)"
    assert Ka._escrow[INC]["state"] == "ESCROWED"

    # --- (3) a forged ASSESSMENT_WITHDRAWN from a DIFFERENT Referee is rejected ---
    print("\n--- forged ASSESSMENT_WITHDRAWN from another Referee ---")
    # Even give Evil a registered key (it published a profile somewhere): authentication
    # alone isn't enough — the notice must come from the Referee the incident is bound to.
    Evil._send_profile("Ka")
    assert Ka._can_verify(Evil.terminal_id), "Evil's key is registered, yet it is not this incident's Referee"
    world.send(Evil.name, "Ka", notice(Evil, "ASSESSMENT_WITHDRAWN", cancellation_fee=0.1))
    rej2 = world.last("Evil", "DELIVERY_REJECTION")
    assert rej2 is not None and rej2["reason"] == "PROTOCOL_REJECTED", \
        f"a notice from the wrong Referee -> PROTOCOL_REJECTED, got {rej2}"
    assert Ka._escrow[INC]["state"] == "ESCROWED", "the forged withdrawal did NOT touch the escrow"
    assert sum(Ka._escrow[INC]["deposits"].values()) == 100, "the deposit is intact"

    # --- (3b) the same binding gates FEE_CLAIM: Evil (registered) cannot claim R's escrow ---
    print("\n--- FEE_CLAIM from the wrong Referee ---")
    world.send(Evil.name, "Ka", {
        "type": "FEE_CLAIM", "incident_id": INC, "referee_id": Evil.terminal_id,
        "cert_id": "CERT-NONE", "currency": "USD", "timestamp": now(),
        "signature": f"SIG_{Evil.terminal_id}",
    })
    rej3 = world.last("Evil", "DELIVERY_REJECTION")
    assert rej3 is not None and rej3["reason"] == "PROTOCOL_REJECTED", \
        "a FEE_CLAIM from a registered-but-wrong Referee is PROTOCOL_REJECTED (identity != authorization)"
    assert world.last("Evil", "FEE_CLAIM_RESULT") is None, "the wrong Referee never reaches FEE_CLAIM logic"
    assert Ka._escrow[INC]["state"] == "ESCROWED", "the escrow is not released by the wrong Referee"

    # --- (4) the legitimate Referee's withdrawal settles normally ---
    print("\n--- the bound Referee's ASSESSMENT_WITHDRAWN settles ---")
    world.send(R.name, "Ka", notice(R, "ASSESSMENT_WITHDRAWN", cancellation_fee=0.1))
    entry = Ka._escrow[INC]
    assert entry["state"] == "WITHDRAWN", f"the bound Referee's withdrawal settles, got {entry['state']}"
    assert entry["cancellation_fee"] == 0.1, "the declared cancellation fee is settled once"

    print("\n[OK] INCIDENT_NOTICE and FEE_CLAIM are authenticated and incident-bound: an"
          " unregistered sender is UNKNOWN_TERMINAL, a wrong-Referee message is"
          " PROTOCOL_REJECTED and cannot move the escrow, and only the bound Referee drives"
          " the lifecycle (G1).")


if __name__ == "__main__":
    run()
