# edge_13_referee_key_at_party_keeper.py
# G2: a party's Keeper (Ka/Kc) can verify a Referee's SIGNED payment messages
# (FEE_CLAIM, FEE_RECEIPT) only if it holds that Referee's public_key. The Referee
# anchors only to its OWN Keeper (Kr), so a party's Keeper never sees the Referee's
# seq-1 CLAIM_ANCHOR — the key arrives solely through the Referee's REFEREE_PROFILE
# (RFC-0001 §6.19, §4.4). Without it the Referee's FEE_CLAIM is undeliverable
# (UNKNOWN_TERMINAL) and it cannot be paid there.
#
# Every other paying scenario exercises the POSITIVE path implicitly: the Referee
# publishes its profile to Kc/Ka at incident open, so the key is present by payment
# time. This scenario pins the boundary directly — the negative case (no profile ->
# no verification) and the trust-on-first-use rule — which the implicit path can't show.
import uuid
from datetime import datetime, timezone
from classes.World import World
from classes.Referee import Referee
from classes.Keeper import Keeper


def run():
    world = World()
    Kr = Keeper("Kr")                    # Referee R's own Keeper
    Ka = Keeper("Ka")                    # a party's Keeper — never holds R's anchors
    R  = Referee("R",  keeper_name="Kr")
    R2 = Referee("R2", keeper_name="Kr")  # a second Referee that never publishes to Ka
    for ag in [Kr, Ka, R, R2]:
        world.register(ag)

    print("=== Scenario edge_13: Referee key at a party Keeper (G2) ===")
    INC = "000000ed-0000-4000-8000-0000000000ed"

    def fee_claim(ref):
        # A well-formed signed FEE_CLAIM (sim signatures are placeholder tokens; the
        # point here is whether the Keeper can look up a key to verify AGAINST at all).
        return {
            "type": "FEE_CLAIM", "incident_id": INC, "referee_id": ref.terminal_id,
            "cert_id": "CERT-NONE", "currency": "USD",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "signature": f"SIG_{ref.terminal_id}",
        }

    # R establishes itself at its OWN Keeper. publish_profile sends the profile AND a
    # seq-1 CLAIM_ANCHOR, so Kr registers R's key through the normal anchor channel.
    R.publish_profile(keeper_name="Kr")
    assert Kr._can_verify(R.terminal_id), "R's own Keeper registers its key from the seq-1 anchor"

    # --- (1) party Keeper holds NO key for R yet: FEE_CLAIM is undeliverable ---
    print("\n--- FEE_CLAIM to a party Keeper that holds no key for R ---")
    assert not Ka._can_verify(R.terminal_id), "Ka has never seen R's anchor or profile"
    world.send(R.name, "Ka", fee_claim(R))
    rej = world.last("R", "DELIVERY_REJECTION")
    assert rej is not None and rej["reason"] == "UNKNOWN_TERMINAL", \
        f"an unverifiable FEE_CLAIM is rejected UNKNOWN_TERMINAL, got {rej}"
    assert world.last("R", "FEE_CLAIM_RESULT") is None, \
        "no FEE_CLAIM_RESULT: the claim never reached the business logic (identity unverified)"

    # --- (2) R publishes its profile to Ka: the key arrives, verification succeeds ---
    print("\n--- R publishes its REFEREE_PROFILE to the party Keeper ---")
    R._send_profile("Ka")
    assert Ka._can_verify(R.terminal_id), "Ka registers R's key from its REFEREE_PROFILE (RFC §6.19)"
    world.send(R.name, "Ka", fee_claim(R))
    # Past the identity gate now: the claim reaches FEE_CLAIM logic and is answered with a
    # FEE_CLAIM_RESULT. It's REJECTED (CERT_NOT_FOUND — no verdict exists), but the point is
    # it was VERIFIED and processed, not that it pays out.
    fcr = world.last("R", "FEE_CLAIM_RESULT")
    assert fcr is not None, "a verifiable FEE_CLAIM reaches the business logic"
    assert fcr["status"] == "REJECTED" and fcr["rejection_reason"] == "CERT_NOT_FOUND", \
        f"verified but no verdict -> CERT_NOT_FOUND, got {fcr.get('status')}/{fcr.get('rejection_reason')}"

    # --- (3) a different Referee that never published to Ka stays unverifiable ---
    print("\n--- a second Referee that never published its profile to Ka ---")
    assert not Ka._can_verify(R2.terminal_id), "Ka never received R2's profile"
    world.send(R2.name, "Ka", fee_claim(R2))
    rej2 = world.last("R2", "DELIVERY_REJECTION")
    assert rej2 is not None and rej2["reason"] == "UNKNOWN_TERMINAL", \
        "R2, unpublished at Ka, cannot be verified either"
    assert world.last("R2", "FEE_CLAIM_RESULT") is None

    # --- trust-on-first-use: a later profile with a DIFFERENT key must not overwrite ---
    print("\n--- trust-on-first-use: a conflicting later key does not overwrite ---")
    original = Ka._pubkeys[R.terminal_id]
    tampered = R._build_profile()
    tampered["public_key"] = "PUBKEY_IMPOSTOR"
    world.send(R.name, "Ka", tampered)
    assert Ka._pubkeys[R.terminal_id] == original, \
        "first key seen for a terminal is authoritative; a later differing key is ignored"

    print("\n[OK] a party Keeper verifies a Referee's signed payment messages only after it"
          " holds the Referee's key via REFEREE_PROFILE (G2); unpublished Referees are"
          " UNKNOWN_TERMINAL; first key seen wins (TOFU).")


if __name__ == "__main__":
    run()
