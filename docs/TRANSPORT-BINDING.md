# RACKP HTTP Transport Binding

**Status: Baseline — referenced from [RFC-0001 Section 6](RFC-0001.md#6-message-schemas) (Message Delivery).** Alternative transports MAY be used where all involved endpoints agree, provided a verifiable delivery acknowledgment is preserved in the transport's form (STD-031).

This document defines the baseline HTTP binding for RACKP protocol messages: how
a message defined in [RFC-0001 Section 6](RFC-0001.md#6-message-schemas) is
carried over HTTP, what constitutes the acceptance response that RFC-0001 treats
as delivery confirmation, and the retry and idempotency conventions senders and
receivers can rely on.

The protocol itself is transport-agnostic. This binding exists so that two
independent implementations interoperate without bilateral agreement; parties
MAY use an alternative transport where every involved endpoint agrees. Message
semantics — who sends what to whom, and when — remain defined solely by
RFC-0001/RFC-0002. This document adds no message types beyond the delivery
receipt and no protocol behavior.

---

## 1. General Conventions

- **Endpoint = one URL.** Every receiver (a Referee's `endpoint`, a Keeper's
  `keeper_endpoint` / `actor_keeper_endpoint`) is a single opaque URL, exactly as
  carried in protocol fields. This binding defines no path structure beneath it.
- **All messages are `POST {endpoint}`.** The request body is exactly one
  protocol message (a JSON object with a `type` field). Receivers dispatch on
  `type`. `GET {endpoint}` SHOULD return the receiver's public profile where one
  exists (`REFEREE_PROFILE` for a Referee) and otherwise MUST return a
  capability summary carrying at minimum `receiver_id` and `public_key`
  (STD-034) — the same Ed25519 key that verifies the receiver's
  `DELIVERY_RECEIPT` signature (Section 2). A Keeper has no profile message of
  its own, so this is its only publication channel for that key; without it, a
  receipt's signature is unverifiable by any party that hasn't obtained the
  key out of band.
- **TLS is REQUIRED** (`https` URLs). Plain `http` MAY be accepted only on
  TESTNET.
- **`Content-Type: application/json; charset=utf-8`**, request and response.
  Bodies MUST NOT carry a UTF-8 BOM (RFC 8259).
- Receivers SHOULD validate inbound messages against the published JSON Schemas
  and SHOULD enforce request size limits (see RFC-0002 Section 3, Unconstrained
  payload input).

## 2. Acceptance Response (Delivery Receipt)

RFC-0001 Section 6 (Message Delivery) makes the receiver's acceptance response
the protocol's delivery confirmation, and STD-022 starts the Actor's response
deadline from it. The acceptance response therefore has evidentiary value and is
given a defined shape.

On acceptance, the receiver MUST respond `200 OK` with:

```json
{
  "type": "DELIVERY_RECEIPT",
  "received_at": "2026-06-12T04:05:06Z",
  "message_hash": "<SHA-256 hex of the JCS canonicalization of the received message>",
  "receiver_id": "<terminal_id of the receiver>",
  "signature": "<Ed25519 over the canonical body excluding signature, Base64url>"
}
```

- `received_at` is the receiver's clock and is authoritative for every deadline
  that RFC-0001 counts from delivery acceptance (STD-022). Senders MUST NOT
  substitute their own clock.
- `message_hash` binds the receipt to one specific message, making the receipt
  usable as the delivery-attempt evidence that STD-030 requires the Referee to
  record: a signed receipt proves *what* was accepted and *when*, by *whom*.
- `signature` is REQUIRED. The receipt is the protocol's proof of service:
  without a signature, "the receiver accepted at `received_at`" is
  indistinguishable from the sender's own assertion, and the evidentiary chain
  built on delivery confirmation (STD-022, STD-030) collapses back to
  self-report. The cost is deliberately accepted: every receiver already
  implements Ed25519 verification, and an operator trusted with escrow custody
  can manage one signing key. A verifier obtains the receiver's public key
  from its published profile (`REFEREE_PROFILE`) or, for a Keeper, from
  `GET {endpoint}` (Section 1, STD-034); failure to independently verify a
  receipt's signature does not undo the delivery it confirms — it only means
  that particular receipt cannot later serve as self-standing evidence.

A receipt is an acknowledgment of receipt and custody — not of agreement,
validity of the message's claims, or any protocol outcome. Where a protocol
outcome exists, it is expressed by the embedded `response` message defined
below, never by the receipt itself.

**Query messages: embedded response.** Some messages are requests for which
RFC-0001 defines an immediate response message (`VERIFICATION_QUERY` →
`VERIFICATION_RESULT`, `ANCHOR_CHAIN_QUERY` → `ANCHOR_CHAIN_RESULT`,
`REFEREE_STATS_QUERY` → `REFEREE_STATS_RESULT`,
`FEE_STATUS_QUERY` → `FEE_STATUS_RESULT`, `REFEREE_DISCOVERY_REQUEST` →
`REFEREE_DISCOVERY_RESULT`, `FEE_CLAIM` → `FEE_CLAIM_RESULT`,
`FEE_REFUND_CLAIM` → `FEE_REFUND_RESULT`). Under this binding, the receiver
MUST carry that response message in the receipt's `response` field:

```json
{
  "type": "DELIVERY_RECEIPT",
  "received_at": "2026-06-12T04:05:06Z",
  "message_hash": "<SHA-256 hex of the JCS canonicalization of the received message>",
  "receiver_id": "<terminal_id of the receiver>",
  "response": { "type": "VERIFICATION_RESULT", "...": "..." },
  "signature": "<Ed25519 over the canonical body excluding signature, Base64url>"
}
```

- The embedded message is exactly the response message RFC-0001 defines; its
  semantics are unchanged by being carried in the receipt.
- `signature` covers the canonical receipt body including `response`. The
  embedded response thereby carries the receipt's evidentiary weight without
  a signature field of its own — response-message schemas define none; this
  binding supplies the proof instead.
- Synchronous embedding is required because Actor and Claimant terminals
  expose no protocol endpoints (RFC-0001 Section 6, Message Delivery): for a
  party-initiated request such as `FEE_REFUND_CLAIM`, a deferred response has
  no route back to the requester. A receiver that cannot produce the response
  synchronously MUST NOT return a bare receipt for these messages — it fails
  the request with `5xx` (not delivered) and the sender retries.
- A `DELIVERY_REJECTION` (Section 3) refuses custody of the request itself
  and carries no `response`. A protocol-level negative answer — e.g.
  `FEE_CLAIM_RESULT` with `status: "REJECTED"` — is a successful delivery
  with an embedded response, not a transport rejection.

The obligation to acknowledge accepted messages is itself a conduct norm
(STD-031), assessable like any other; this document defines its HTTP form.

## 3. Rejection and Errors

| HTTP status | Meaning | Body |
|---|---|---|
| `400` | Body is not valid JSON, or fails schema validation | `DELIVERY_REJECTION` |
| `401` | Signature verification failed, or unknown `terminal_id` | `DELIVERY_REJECTION` |
| `409` | Protocol-state conflict (e.g., non-monotonic `sequence_number`) | `DELIVERY_REJECTION` |
| `422` | Well-formed but rejected by protocol rules (e.g., unknown `incident_id`) | `DELIVERY_REJECTION` |
| `5xx` / timeout | **Not delivered.** No confirmation exists; the sender retries. | — |

```json
{
  "type": "DELIVERY_REJECTION",
  "reason": "SIGNATURE_INVALID",
  "detail": "optional human-readable explanation",
  "received_at": "2026-06-12T04:05:06Z"
}
```

`reason` values: `MALFORMED`, `SCHEMA_VIOLATION`, `SIGNATURE_INVALID`,
`UNKNOWN_TERMINAL`, `SEQUENCE_CONFLICT`, `PROTOCOL_REJECTED`, `TOO_LARGE`.
A 4xx rejection is a definitive answer, not a delivery failure: senders MUST NOT
blindly retry an identical message after one (a corrected message is a new
message).

## 4. Retry and Idempotency

- On timeout or `5xx`, the sender SHOULD retry **the identical message bytes**
  (same `signature`) with exponential backoff. Baseline: first retry after
  1 minute, factor 2, capped at 1 hour between attempts, continuing at least
  until the protocol deadline relevant to the message has passed (e.g., the
  retry obligation of STD-022 for `ACTOR_NOTIFICATION`).
- Receivers MUST treat redelivery of an identical message — same
  `message_hash` — as idempotent: re-respond with the original acknowledgment
  — the receipt, including any embedded `response`, as originally issued
  rather than recomputed, or the rejection — and apply no state change twice.
  Escrow operations, anchor appends, and timer transitions MUST NOT
  double-apply.
- Each attempt, its endpoint, time, and outcome belong in the sender's
  delivery-attempt record where RFC-0001 requires one (STD-030).

## 5. Out of Scope

- **Mailbox access by a party to its own Keeper** (poll or push, and its
  authentication): a commercial/implementation matter per RFC-0001 Section 6.
  This binding covers only delivery *into* the mailbox — a party-addressed
  message POSTed to the party's Keeper endpoint, confirmed by the Keeper's
  receipt.
- Endpoint discovery and registries (RFC-0001 Section 6.18; RFC-0002 Section 3).
- Settlement rails and any movement of funds (RFC-0002 Section 1.6).

## 6. Conformance

An HTTP implementation is conformant with this binding if it (a) accepts
protocol messages by POST at its published endpoint, (b) returns
`DELIVERY_RECEIPT` / `DELIVERY_REJECTION` as defined, and (c) honors the
idempotency rule. The machine-readable definitions are
[`schemas/delivery_receipt.json`](../schemas/delivery_receipt.json) and
[`schemas/delivery_rejection.json`](../schemas/delivery_rejection.json); the
receipt obligation itself is normative via STD-031.
