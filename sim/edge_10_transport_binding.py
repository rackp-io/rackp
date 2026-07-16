# edge_10_transport_binding.py
# STD-031 / TRANSPORT-BINDING.md: a receiver MUST acknowledge every accepted message
# with a signed DELIVERY_RECEIPT (proof of service) and reject invalid ones with a
# reason-coded DELIVERY_REJECTION. Redelivery of identical bytes is idempotent.
# This scenario exercises the two transport schemas that no protocol-flow scenario
# touches (delivery_receipt.json, delivery_rejection.json):
#   1. A well-formed message → DELIVERY_RECEIPT whose message_hash binds it, signed.
#   2. Identical redelivery → the same receipt, no second state change (binding §4).
#   3. A bad signature → DELIVERY_REJECTION reason=SIGNATURE_INVALID (binding §3).
#   4. A schema-invalid message → DELIVERY_REJECTION reason=SCHEMA_VIOLATION.
from classes.World import World
from classes.Claimant import Claimant
from classes.Keeper import Keeper


def run():
    world = World()
    C  = Claimant("C", keeper_name="Kc")
    Kc = Keeper("Kc")
    for agent in [C, Kc]:
        world.register(agent)

    print("=== Scenario edge_10: HTTP transport binding (STD-031) ===")
    INC = "00000031-0000-4000-8000-000000000031"

    # A well-formed protocol message (FEE_REFUND_CLAIM shape) the receiver will accept.
    good = {
        "type":         "FEE_REFUND_CLAIM",
        "incident_id":  INC,
        "depositor_id": C.terminal_id,
        "timestamp":    "2026-06-15T00:00:00Z",
        "signature":    f"SIG_{C.terminal_id}",
    }

    # (1) Accepted → signed DELIVERY_RECEIPT binding the message identity.
    print("\n--- accepted message (expect DELIVERY_RECEIPT) ---")
    receipt = Kc.acknowledge_delivery(good, "C")
    assert receipt["type"] == "DELIVERY_RECEIPT"
    assert receipt["receiver_id"] == Kc.terminal_id
    assert receipt["signature"].startswith("SIG_")
    assert len(receipt["message_hash"]) == 64

    # (2) Idempotent redelivery → the same receipt, no second state change (binding §4).
    print("\n--- identical redelivery (expect same receipt, idempotent) ---")
    receipt2 = Kc.acknowledge_delivery(good, "C")
    assert receipt2 == receipt, "redelivery must return the original receipt"
    assert len(Kc._delivery_acks) == 1, "idempotent redelivery must not create a new ack"

    # (3) Bad signature → DELIVERY_REJECTION(SIGNATURE_INVALID).
    print("\n--- tampered signature (expect DELIVERY_REJECTION SIGNATURE_INVALID) ---")
    bad_sig = dict(good, signature="0xTAMPERED")
    rej_sig = Kc.acknowledge_delivery(bad_sig, "C")
    assert rej_sig["type"] == "DELIVERY_REJECTION"
    assert rej_sig["reason"] == "SIGNATURE_INVALID"

    # (4) Schema-invalid message → DELIVERY_REJECTION(SCHEMA_VIOLATION).
    print("\n--- malformed message (expect DELIVERY_REJECTION SCHEMA_VIOLATION) ---")
    malformed = {k: v for k, v in good.items() if k != "depositor_id"}  # drop required field
    rej_schema = Kc.acknowledge_delivery(malformed, "C")
    assert rej_schema["type"] == "DELIVERY_REJECTION"
    assert rej_schema["reason"] == "SCHEMA_VIOLATION"

    print("\n[OK] signed DELIVERY_RECEIPT on accept; idempotent redelivery; reason-coded"
          " DELIVERY_REJECTION on bad signature / schema violation (STD-031).")


if __name__ == "__main__":
    run()
