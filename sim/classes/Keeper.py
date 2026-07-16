# classes/Keeper.py
from datetime import datetime, timezone, timedelta
from classes.Agent import Agent
from classes.Hasher import hash_claim

class Keeper(Agent):
    # STD-027 Standard Norm default assessment-deadline window (hours), applied when
    # INCIDENT_NOTICE(INCIDENT_OPEN) carries no assessment_deadline_hours. The Referee's
    # declared value from the notice takes precedence (stored per escrow entry). The sim
    # exposes expire_assessment_timer() to elapse the window without waiting.
    DEFAULT_ASSESSMENT_DEADLINE_HOURS = 720

    def __init__(self, name="K"):
        super().__init__(name)
        self.anchors = {}  # claim_id -> CLAIM_ANCHOR dict
        self._j_stats = {}  # terminal_id -> stats dict
        # incident_id -> {deposits: {id: amount}, currency, released: bool,
        #   state: ESCROWED|RELEASED|SETTLED|WITHDRAWN|EXPIRED (STD-028 lifecycle),
        #   deadline: datetime|None (STD-028 assessment-deadline timer),
        #   refunded: {depositor_id: amount}, reassessment_initiator: str|None}
        self._escrow = {}
        self._prior_verdicts = {}  # incident_id -> [cert_id, ...]
        self._profiles = {}  # referee_id -> REFEREE_PROFILE dict
        self._pubkeys = {}  # terminal_id -> public_key (TOFU; from seq-1 CLAIM_ANCHOR or REFEREE_PROFILE, G2)
        self._incident_referee = {}  # incident_id -> referee_id bound by the first accepted INCIDENT_NOTICE (G1)
        self._appeal_pending = {}  # incident_id -> bool
        self._delivery_acks = {}  # message_hash -> DELIVERY_RECEIPT|DELIVERY_REJECTION (STD-031 idempotency)

    def on_message(self, msg):
        """Dispatch handler for all inbound message types"""
        if msg["type"] == "CLAIM_ANCHOR":
            self._store_anchor(msg)
        elif msg["type"] == "VERIFICATION_QUERY":
            self._handle_verification(msg)
        elif msg["type"] == "ANCHOR_CHAIN_QUERY":
            self._handle_anchor_chain_query(msg)
        elif msg["type"] == "REFEREE_STATS_QUERY":
            self._handle_referee_stats_query(msg)
        elif msg["type"] == "FEE_DEPOSIT":
            self._handle_fee_deposit(msg)
        elif msg["type"] == "FEE_STATUS_QUERY":
            self._handle_fee_status_query(msg)
        elif msg["type"] == "INCIDENT_NOTICE":
            self._handle_incident_notice(msg)
        elif msg["type"] == "REFEREE_PROFILE":
            self._store_profile(msg)
        elif msg["type"] == "REFEREE_DISCOVERY_REQUEST":
            self._handle_discovery_request(msg)
        elif msg["type"] == "FEE_RECEIPT":
            self._handle_fee_receipt(msg)
        elif msg["type"] == "FEE_CLAIM":
            self._handle_fee_claim(msg)
        elif msg["type"] == "FEE_REFUND_CLAIM":
            self._handle_fee_refund_claim(msg)

    def _register_key(self, terminal_id, public_key):
        """G2/RFC §4.4 — trust-on-first-use key registration. The first key seen for a
        terminal is authoritative; a later differing key (anchor or profile) is ignored."""
        if public_key and terminal_id not in self._pubkeys:
            self._pubkeys[terminal_id] = public_key

    def _can_verify(self, terminal_id):
        """G2 — whether this Keeper holds a public_key for terminal_id and can therefore
        verify its signed messages. In a split-Keeper topology a party's Keeper obtains a
        Referee's key from its REFEREE_PROFILE (RFC §6.19); absent it, signed messages
        from that Referee are undeliverable (UNKNOWN_TERMINAL)."""
        return terminal_id in self._pubkeys

    def _reject_unverifiable(self, msg, reason="UNKNOWN_TERMINAL"):
        """G2/G1 — reject a signed message as undeliverable, mirroring TRANSPORT-BINDING §3.
        UNKNOWN_TERMINAL: the sender's public_key is not held (the Referee must first publish
        its REFEREE_PROFILE here, RFC-0001 §6.19). PROTOCOL_REJECTED: the notice's referee_id
        does not match the Referee this incident is bound to (G1)."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rej = {
            "type": "DELIVERY_REJECTION",
            "reason": reason,
            "received_at": now,
            "receiver_id": self.terminal_id,
        }
        print(f"[{self.name}] DELIVERY_REJECTION: {reason}"
              f"  ({msg['type']} from {msg.get('referee_id', '?')[:8]}...)")
        self.world.send(self.name, msg["_sender"], rej)

    def _store_anchor(self, msg):
        """RFC §4.4, §6.1 — stores CLAIM_ANCHOR; triggers j_stats update and escrow events on typed anchors; schema: schemas/claim_anchor.json"""
        self.anchors[msg["claim_id"]] = msg
        # RFC §4.4: register the terminal's key from its first anchor (public_key present
        # at sequence_number == 1). The primary key-registration channel (G2).
        self._register_key(msg["terminal_id"], msg.get("public_key"))
        print(f"[{self.name}] anchor stored: {msg['terminal_id'][:8]}... SEQ{msg['sequence_number']:04d}  hash={msg['data_hash'][:8]}...")
        if msg.get("action_type"):
            self._update_j_stats(msg)
            if msg["action_type"] == "ASSESSMENT_ISSUED" and msg.get("incident_id"):
                incident_id = msg["incident_id"]
                cert_id = msg.get("cert_id")
                if cert_id:
                    self._prior_verdicts.setdefault(incident_id, []).append(cert_id)
                # Escrow release is triggered by INCIDENT_NOTICE(ASSESSMENT_COMPLETE), not here.
                # This CLAIM_ANCHOR is the Referee's self-anchor to its own Keeper only.

    def _handle_fee_deposit(self, msg):
        """RFC §6.4 — receives FEE_DEPOSIT, records into escrow; schema: schemas/fee_deposit.json.
        STD-033: verified against depositor_id's registered public key before crediting
        escrow — without this, any sender could forge another party's deposit record."""
        depositor_id = msg["depositor_id"]
        if not self._can_verify(depositor_id):
            self._reject_unverifiable(msg)
            return
        incident_id  = msg["incident_id"]
        amount       = msg["amount"]
        currency     = msg.get("currency", "USD")
        prior = self._prior_verdicts.get(incident_id, [])
        is_reassessment = len(prior) > 0
        if incident_id not in self._escrow:
            self._escrow[incident_id] = {
                "deposits": {},
                "currency": currency,
                "released": False,
                "state": "ESCROWED",
                "deadline": None,
                "refunded": {},
                "reassessment_initiator": depositor_id if is_reassessment else None
            }
        elif not self._escrow[incident_id]["deposits"]:
            # Entry pre-created by INCIDENT_NOTICE (INCIDENT_OPEN or a prior round's
            # ASSESSMENT_COMPLETE) with no deposits yet: this is the round's first
            # deposit, so it fixes the escrow currency and — after a prior verdict —
            # identifies the re-assessment initiating party (STD-020).
            self._escrow[incident_id]["currency"] = currency
            if is_reassessment and self._escrow[incident_id].get("reassessment_initiator") is None:
                self._escrow[incident_id]["reassessment_initiator"] = depositor_id
        self._escrow[incident_id]["deposits"][depositor_id] = amount
        # STD-028: the assessment-deadline timer starts at the later of FEE_DEPOSIT
        # and INCIDENT_NOTICE(INCIDENT_OPEN). Refreshing on each event yields "later of".
        self._start_assessment_timer(self._escrow[incident_id])
        if is_reassessment:
            initiator = self._escrow[incident_id]["reassessment_initiator"]
            print(f"[{self.name}] escrow deposit (RE-ASSESSMENT STD-020): {depositor_id}"
                  f"  incident={incident_id}  amount={amount} {currency}")
            if depositor_id == initiator:
                print(f"[{self.name}]   STD-020: {depositor_id} is the initiating party"
                      f" - full cost applies, transfer to opposing party PROHIBITED")
        else:
            print(f"[{self.name}] escrow deposit: {depositor_id}  incident={incident_id}"
                  f"  amount={amount} {currency}")

    def release_fee(self, incident_id):
        """RFC §6.15 — explicit FEE_RELEASE trigger called after INCIDENT_NOTICE(ASSESSMENT_COMPLETE); schema: schemas/fee_release.json"""
        entry = self._escrow.get(incident_id)
        if not entry:
            print(f"[{self.name}] release_fee: no escrow entry for incident={incident_id}")
            return
        referee_tid = entry.get("_referee_tid")
        if not referee_tid:
            print(f"[{self.name}] release_fee: no referee recorded for incident={incident_id}")
            return
        self._release_escrow(incident_id, referee_tid)

    def _settle_withdrawal_escrow(self, incident_id, referee_tid, cancellation_fee=0):
        """RFC §6.17 — triggered by INCIDENT_NOTICE(ASSESSMENT_WITHDRAWN); deducts the
        Referee's declared cancellation_fee (carried in the notice; defaults to 0 per
        REFEREE_PROFILE) and returns the remainder to depositors; no FEE_RELEASE issued"""
        entry = self._escrow.get(incident_id)
        if not entry or entry["released"]:
            return
        total            = sum(entry["deposits"].values())
        currency         = entry["currency"]
        fee_paid         = min(cancellation_fee, total)
        remainder        = round(total - fee_paid, 2)
        entry["released"] = True
        entry["state"] = "WITHDRAWN"
        entry["cancellation_fee"] = fee_paid   # ledger record of the settlement
        entry["remainder"] = remainder
        print(f"[{self.name}] withdrawal escrow settlement: incident={incident_id}")
        print(f"[{self.name}]   cancellation_fee={fee_paid} {currency} -> {referee_tid[:8]}...")
        print(f"[{self.name}]   remainder={remainder} {currency} -> depositing parties")

    def _release_escrow(self, incident_id, referee_id):
        """RFC §6.15 — sends FEE_RELEASE to Referee after appeal window closes; schema: schemas/fee_release.json"""
        from datetime import datetime, timezone
        entry = self._escrow.get(incident_id)
        if not entry or entry["released"]:
            return
        # STD-028: an EXPIRED escrow has already been refunded — never release it.
        if entry.get("state") == "EXPIRED":
            print(f"[{self.name}] release_fee blocked: escrow EXPIRED  incident={incident_id}")
            return
        total    = sum(entry["deposits"].values())
        currency = entry["currency"]
        entry["released"] = True
        entry["state"] = "RELEASED"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[{self.name}] escrow release: incident={incident_id}  total={total} {currency}")
        print(f"[{self.name}]   -> {referee_id}: {total} {currency}")
        release_msg = {
            "type": "FEE_RELEASE",
            "incident_id": incident_id,
            "referee_id": referee_id,
            "released_amount": total,
            "currency": currency,
            "timestamp": now
        }
        self.world.send(self.name, self.world.route_by_tid(referee_id), release_msg)

    def _update_j_stats(self, msg):
        """RFC §4.4 — maintains per-Referee action stats from CLAIM_ANCHOR action_type field"""
        tid = msg["terminal_id"]
        if tid not in self._j_stats:
            self._j_stats[tid] = {
                "assessment_count": 0,
                "poh_cert_count": 0,
                "appeal_count": 0,
                "appeal_accepted_count": 0,
                "appeal_rejected_count": 0,
                "appealed_assessment_ids": set(),
                "named_as_actor_count": 0,
                "active_since": msg["timestamp"],
                "last_active": msg["timestamp"]
            }
        s = self._j_stats[tid]
        s["last_active"] = msg["timestamp"]
        action_type = msg["action_type"]
        incident_id = msg.get("incident_id")
        # unreceived_count (§6.21/§6.24) applies to FIXED-model incidents only. The fee
        # model comes from the Referee's REFEREE_PROFILE stored at this (its own) Keeper;
        # an unpublished profile is counted conservatively (unknown is not exempt).
        fee_model = self._profiles.get(tid, {}).get("fee", {}).get("model")
        owes_receipt = fee_model != "FREE"
        if action_type == "ASSESSMENT_ISSUED":
            s["assessment_count"] += 1
            if owes_receipt:
                s["unreceived_count"] = s.get("unreceived_count", 0) + 1
        elif action_type == "POH_CERT_ISSUED":
            # PoHI analogue of ASSESSMENT_ISSUED, counted SEPARATELY so PoHI volume never
            # enters the incident-assessment reputation denominators (RFC §6.21, §8.4). Like
            # a FIXED-model assessment it owes a FEE_RECEIPT, so it shares the
            # unreceived_count obligation (closed by the Referee's FEE_RECEIPT copy, §6.24).
            s["poh_cert_count"] = s.get("poh_cert_count", 0) + 1
            if owes_receipt:
                s["unreceived_count"] = s.get("unreceived_count", 0) + 1
        elif action_type == "APPEAL_RECEIVED":
            s["appeal_count"] += 1
            if incident_id:
                s["appealed_assessment_ids"].add(incident_id)
        elif action_type == "APPEAL_ACCEPTED":
            s["appeal_accepted_count"] += 1
        elif action_type == "APPEAL_REJECTED":
            s["appeal_rejected_count"] += 1
        elif action_type == "NAMED_AS_ACTOR":
            # named_actor_id (sim-only field) identifies the terminal that was named.
            # Falls back to the sender if absent.
            named_id = msg.get("named_actor_id", tid)
            named_s = self._j_stats.setdefault(named_id, {
                "assessment_count": 0, "poh_cert_count": 0, "appeal_count": 0,
                "appeal_accepted_count": 0, "appeal_rejected_count": 0,
                "appealed_assessment_ids": set(), "named_as_actor_count": 0,
                "active_since": msg["timestamp"], "last_active": msg["timestamp"]
            })
            named_s["named_as_actor_count"] += 1
        elif action_type == "WITHDRAWAL_ISSUED":
            s.setdefault("withdrawal_count", 0)
            s["withdrawal_count"] += 1

    def _handle_referee_stats_query(self, msg):
        """RFC §4.4 — responds to REFEREE_STATS_QUERY with assessment/appeal track record; schema: schemas/referee_stats_query.json, schemas/referee_stats_result.json"""
        from datetime import datetime, timezone
        terminal_id = msg["terminal_id"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        s = self._j_stats.get(terminal_id)
        if not s:
            result = {
                "type": "REFEREE_STATS_RESULT",
                "terminal_id": terminal_id,
                "found": False,
                "timestamp": now
            }
        else:
            assessment_count          = s["assessment_count"]
            appeal_count           = s["appeal_count"]
            appealed_assessment_count = len(s["appealed_assessment_ids"])
            named_as_actor_count   = s["named_as_actor_count"]
            appeal_rate            = round(appeal_count / assessment_count, 3) if assessment_count > 0 else 0.0
            appealed_assessment_rate  = round(appealed_assessment_count / assessment_count, 3) if assessment_count > 0 else 0.0
            named_as_actor_rate    = round(named_as_actor_count / assessment_count, 3) if assessment_count > 0 else 0.0
            j_anchors = sorted(
                [a for a in self.anchors.values() if a["terminal_id"] == terminal_id],
                key=lambda a: a["sequence_number"]
            )
            continuous = all(
                j_anchors[i]["sequence_number"] == j_anchors[i-1]["sequence_number"] + 1
                for i in range(1, len(j_anchors))
            ) if len(j_anchors) > 1 else True
            result = {
                "type": "REFEREE_STATS_RESULT",
                "terminal_id": terminal_id,
                "found": True,
                "assessment_count": assessment_count,
                "poh_cert_count": s.get("poh_cert_count", 0),
                "appeal_count": appeal_count,
                "appeal_rate": appeal_rate,
                "appealed_assessment_count": appealed_assessment_count,
                "appealed_assessment_rate": appealed_assessment_rate,
                "appeal_accepted_count": s["appeal_accepted_count"],
                "appeal_rejected_count": s["appeal_rejected_count"],
                "named_as_actor_count": named_as_actor_count,
                "named_as_actor_rate": named_as_actor_rate,
                "anchor_continuity": continuous,
                "active_since": s["active_since"],
                "last_active":  s["last_active"],
                "unreceived_count": s.get("unreceived_count", 0),
                "timestamp": now
            }
        if s:
            print(f"[{self.name}] referee stats: {terminal_id}")
            print(f"[{self.name}]   assessment_count={result['assessment_count']}"
                  f"  appealed_assessment_rate={result['appealed_assessment_rate']}"
                  f"  named_as_actor_rate={result['named_as_actor_rate']}")
            print(f"[{self.name}]   appeal_count={result['appeal_count']}"
                  f"  appeal_rate={result['appeal_rate']}")
            print(f"[{self.name}]   appeal_accepted={result['appeal_accepted_count']}"
                  f"  appeal_rejected={result['appeal_rejected_count']}")
            print(f"[{self.name}]   anchor_continuity={result['anchor_continuity']}"
                  f"  active_since={result['active_since']}")
        else:
            print(f"[{self.name}] referee stats: {terminal_id}  not found")
        self.world.send(self.name, msg["_sender"], result)

    def _handle_fee_status_query(self, msg):
        """RFC §6.5, §6.6 — responds to FEE_STATUS_QUERY with deposit confirmation and prior verdict refs; schema: schemas/fee_status_query.json, schemas/fee_status_result.json"""
        from datetime import datetime, timezone
        incident_id = msg["incident_id"]
        terminal_id = msg["terminal_id"]
        entry       = self._escrow.get(incident_id, {})
        deposits    = entry.get("deposits", {})
        deposited   = terminal_id in deposits
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prior = self._prior_verdicts.get(incident_id, [])
        result = {
            "type": "FEE_STATUS_RESULT",
            "incident_id": incident_id,
            "terminal_id": terminal_id,
            "deposited": deposited,
            "timestamp": now,
            "prior_assessment_count": len(prior),
        }
        if prior:
            result["prior_verdict_refs"] = list(prior)
        print(f"[{self.name}] fee status: {terminal_id[:8]}...  incident={incident_id}"
              f"  deposited={deposited}  prior_count={len(prior)}")
        self.world.send(self.name, msg["_sender"], result)

    def _handle_fee_receipt(self, msg):
        """RFC §6.24 — receives FEE_RECEIPT from Referee; marks escrow SETTLED; decrements unreceived_count once per incident; schema: schemas/fee_receipt.json"""
        # G2: FEE_RECEIPT is signed; a Keeper that holds no key for this Referee cannot
        # verify it (UNKNOWN_TERMINAL). The Referee's own Keeper has the key from the
        # seq-1 anchor; a party's Keeper has it from the REFEREE_PROFILE published at
        # incident open (RFC §6.19).
        if not self._can_verify(msg["referee_id"]):
            self._reject_unverifiable(msg)
            return
        # G1: same authorization boundary as FEE_CLAIM. A bound escrow lives at a party
        # Keeper; the own-Keeper copy lands where no notice bound a Referee (bound is None),
        # so it passes.
        bound = self._incident_referee.get(msg["incident_id"])
        if bound and bound != msg["referee_id"]:
            self._reject_unverifiable(msg, reason="PROTOCOL_REJECTED")
            return
        incident_id     = msg["incident_id"]
        referee_id      = msg["referee_id"]
        received_amount = msg["received_amount"]
        currency        = msg["currency"]
        entry = self._escrow.get(incident_id)
        if entry:
            entry["settled"] = True
            entry["state"] = "SETTLED"
        # Decrement once per incident (guards against duplicate receipts in split-Keeper setups)
        s = self._j_stats.get(referee_id)
        if s:
            receipt_incidents = s.setdefault("receipt_incidents", set())
            if incident_id not in receipt_incidents:
                receipt_incidents.add(incident_id)
                s["unreceived_count"] = max(0, s.get("unreceived_count", 0) - 1)
        print(f"[{self.name}] FEE_RECEIPT: incident={incident_id}"
              f"  referee={referee_id[:8]}...  amount={received_amount} {currency}"
              f"  -> escrow SETTLED")

    def _handle_fee_claim(self, msg):
        """RFC §6.22 — receives FEE_CLAIM from Referee; validates and responds with FEE_CLAIM_RESULT; schema: schemas/fee_claim.json, schemas/fee_claim_result.json"""
        from datetime import datetime, timezone
        # G2: FEE_CLAIM is signed; without the Referee's key this Keeper cannot verify it
        # and the claim is undeliverable (UNKNOWN_TERMINAL), not a FEE_CLAIM_RESULT
        # rejection. A party's Keeper holds the key from the REFEREE_PROFILE published at
        # incident open (RFC §6.19); absent it, the Referee cannot be paid here.
        if not self._can_verify(msg["referee_id"]):
            self._reject_unverifiable(msg)
            return
        # G1: identity is not authorization. Only the Referee this incident is bound to
        # (by the first INCIDENT_NOTICE) may claim its escrow — otherwise a different
        # registered terminal (even a party that knows the cert_id) could release or block
        # it. A claim only reaches ACCEPTED after ASSESSMENT_COMPLETE, which binds, so a
        # legitimate claim always matches.
        bound = self._incident_referee.get(msg["incident_id"])
        if bound and bound != msg["referee_id"]:
            self._reject_unverifiable(msg, reason="PROTOCOL_REJECTED")
            return
        incident_id = msg["incident_id"]
        referee_id  = msg["referee_id"]
        cert_id     = msg["cert_id"]
        currency    = msg["currency"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = self._escrow.get(incident_id)

        def reject(reason):
            result = {
                "type":             "FEE_CLAIM_RESULT",
                "incident_id":      incident_id,
                "referee_id":       referee_id,
                "cert_id":          cert_id,
                "status":           "REJECTED",
                "currency":         currency,
                "rejection_reason": reason,
                "timestamp":        now
            }
            print(f"[{self.name}] FEE_CLAIM rejected: {reason}  incident={incident_id}")
            self.world.send(self.name, msg["_sender"], result)

        # STD-028: a FEE_CLAIM after the escrow has EXPIRED confers no payment right.
        if entry and entry.get("state") == "EXPIRED":
            reject("ESCROW_EXPIRED")
            return
        if entry and entry.get("released"):
            reject("ALREADY_RELEASED")
            return
        if cert_id not in self._prior_verdicts.get(incident_id, []):
            reject("CERT_NOT_FOUND")
            return
        if self._appeal_pending.get(incident_id):
            reject("APPEAL_PENDING")
            return

        total    = sum(entry["deposits"].values()) if entry else 0
        currency = entry["currency"] if entry else currency
        if entry:
            entry["released"] = True
            entry["state"] = "RELEASED"
        print(f"[{self.name}] FEE_CLAIM accepted: incident={incident_id}  amount={total} {currency}")
        self.world.send(self.name, msg["_sender"], {
            "type":            "FEE_CLAIM_RESULT",
            "incident_id":     incident_id,
            "referee_id":      referee_id,
            "cert_id":         cert_id,
            "status":          "ACCEPTED",
            "released_amount": total,
            "currency":        currency,
            "timestamp":       now
        })

    def _start_assessment_timer(self, entry):
        """STD-028 — (re)arm the assessment-deadline timer to now + window. Called on
        FEE_DEPOSIT and INCIDENT_OPEN; the later call wins, giving 'later of the two'.
        The window is the Referee-declared assessment_deadline_hours carried in
        INCIDENT_OPEN (STD-027), falling back to the Standard Norm default of 720h.
        Never re-arms a terminal escrow (released/refunded)."""
        if entry.get("state") in ("RELEASED", "SETTLED", "WITHDRAWN", "EXPIRED"):
            return
        hours = entry.get("deadline_hours", self.DEFAULT_ASSESSMENT_DEADLINE_HOURS)
        entry["deadline"] = datetime.now(timezone.utc) + timedelta(hours=hours)

    def expire_assessment_timer(self, incident_id):
        """Sim helper — backdate the deadline to simulate elapsed time without waiting.
        Production Keepers compare wall-clock against the stored deadline instead."""
        entry = self._escrow.get(incident_id)
        if entry and entry.get("deadline") is not None:
            entry["deadline"] = datetime.now(timezone.utc) - timedelta(seconds=1)
            print(f"[{self.name}] assessment-deadline timer elapsed (sim): incident={incident_id}")

    def _handle_fee_refund_claim(self, msg):
        """STD-028 — receives FEE_REFUND_CLAIM from a depositing party. After the
        assessment deadline elapses with no ASSESSMENT_COMPLETE, returns the full
        deposited amount (no cancellation fee) and transitions the escrow to EXPIRED;
        schema: schemas/fee_refund_claim.json, schemas/fee_refund_result.json"""
        incident_id  = msg["incident_id"]
        depositor_id = msg["depositor_id"]
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = self._escrow.get(incident_id)

        def respond(status, reason=None, amount=None):
            result = {
                "type":        "FEE_REFUND_RESULT",
                "incident_id": incident_id,
                "depositor_id": depositor_id,
                "status":      status,
                "currency":    entry["currency"] if entry else msg.get("currency", "USD"),
                "timestamp":   now_str,
            }
            if reason:
                result["rejection_reason"] = reason
            if amount is not None:
                result["refunded_amount"] = amount
            if entry and entry.get("deadline") is not None:
                result["deadline_expires_at"] = entry["deadline"].strftime("%Y-%m-%dT%H:%M:%SZ")
            tag = reason if status == "REJECTED" else f"{amount} {result['currency']}"
            print(f"[{self.name}] FEE_REFUND_CLAIM {status}: {tag}  incident={incident_id}")
            self.world.send(self.name, msg["_sender"], result)

        if not entry or depositor_id not in entry.get("deposits", {}):
            respond("REJECTED", "DEPOSIT_NOT_FOUND")
            return
        if entry.get("state") in ("RELEASED", "SETTLED"):
            respond("REJECTED", "ALREADY_RELEASED")
            return
        if entry.get("state") == "WITHDRAWN":
            # fee_refund_result.json: funds returned via withdrawal settlement
            # are ALREADY_REFUNDED (ASSESSMENT_COMPLETED is the release-flow case).
            respond("REJECTED", "ALREADY_REFUNDED")
            return
        if depositor_id in entry.get("refunded", {}):
            respond("REJECTED", "ALREADY_REFUNDED")
            return
        # STD-028: the Keeper MUST NOT refund before the deadline has elapsed.
        deadline = entry.get("deadline")
        if deadline is None or now < deadline:
            respond("REJECTED", "DEADLINE_NOT_ELAPSED")
            return

        amount = entry["deposits"][depositor_id]
        entry["refunded"][depositor_id] = amount   # ledger record; full amount, no fee
        entry["state"] = "EXPIRED"
        respond("ACCEPTED", amount=amount)

    def acknowledge_delivery(self, message, sender_name):
        """STD-031 / TRANSPORT-BINDING.md §2-4 — the receiver's delivery acknowledgment.
        Returns (and sends back to the sender) a signed DELIVERY_RECEIPT for an accepted
        message, or a reason-coded DELIVERY_REJECTION for one that fails validation.
        Idempotent on message_hash: redelivery of identical bytes re-returns the original
        acknowledgment with no second state change (binding §4).
        schema: schemas/delivery_receipt.json, schemas/delivery_rejection.json"""
        clean = {k: v for k, v in message.items() if k != "_sender"}
        mh = hash_claim(clean)  # SHA-256 over the canonical message (binding §2)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Binding §4: identical redelivery returns the original acknowledgment, no-op.
        if mh in self._delivery_acks:
            ack = self._delivery_acks[mh]
            print(f"[{self.name}] redelivery (idempotent): re-returning original {ack['type']}")
            self.world.send(self.name, sender_name, ack)
            return ack

        def reject(reason, detail=None):
            rej = {
                "type":        "DELIVERY_REJECTION",
                "reason":      reason,
                "received_at": now,
                "receiver_id": self.terminal_id,
            }
            if detail:
                rej["detail"] = detail
            self._delivery_acks[mh] = rej
            print(f"[{self.name}] DELIVERY_REJECTION: {reason}  ({message.get('type')})")
            self.world.send(self.name, sender_name, rej)
            return rej

        # Binding §3: malformed/invalid messages get a reason-coded rejection.
        if not clean.get("type"):
            return reject("MALFORMED", "no type field")
        # Schema validation is a soft gate (mirrors World._validate): if jsonschema is
        # unavailable we skip it rather than mislabel the absent dependency as a
        # SCHEMA_VIOLATION. Resolver construction stays outside the validation try so a
        # resolver/programming error propagates instead of masquerading as a schema fault;
        # only an actual ValidationError yields the SCHEMA_VIOLATION rejection.
        try:
            import jsonschema
        except ImportError:
            jsonschema = None
        from classes.World import _load_schema
        schema = _load_schema(clean["type"])
        if jsonschema is not None and schema is not None:
            from classes.World import _build_store
            resolver = jsonschema.RefResolver(base_uri=schema.get("$id", ""),
                                              referrer=schema, store=_build_store())
            try:
                jsonschema.validate(instance=clean, schema=schema, resolver=resolver)
            except jsonschema.ValidationError as e:
                return reject("SCHEMA_VIOLATION", e.message)
        # Sim signature convention is the placeholder token "SIG_<...>"; a missing or
        # malformed token stands in for a failed Ed25519 verification (binding §3).
        sig = clean.get("signature")
        if sig is not None and not str(sig).startswith("SIG_"):
            return reject("SIGNATURE_INVALID")

        receipt = {
            "type":         "DELIVERY_RECEIPT",
            "received_at":  now,
            "message_hash": mh,
            "receiver_id":  self.terminal_id,
            "signature":    f"SIG_{self.terminal_id}",  # receipts are signed (binding §2)
        }
        self._delivery_acks[mh] = receipt
        print(f"[{self.name}] DELIVERY_RECEIPT: {message.get('type')}  hash={mh[:8]}...")
        self.world.send(self.name, sender_name, receipt)
        return receipt

    def _handle_incident_notice(self, msg):
        """RFC §6.3, §4.4 — processes INCIDENT_NOTICE events to manage escrow lifecycle; schema: schemas/incident_notice.json"""
        incident_id = msg["incident_id"]
        event_type  = msg["event_type"]
        referee_id  = msg["referee_id"]
        # G1: authenticate before acting. The notice drives escrow transitions (release,
        # appeal hold, withdrawal settlement), so an unverifiable or wrong-Referee notice
        # must not touch the escrow. (1) the sender's key must be registered here — a party
        # Keeper gets it from the Referee's REFEREE_PROFILE published at incident open (G2);
        # (2) the incident is bound to the referee_id of the first accepted notice, and a
        # later notice from a different Referee is rejected.
        if not self._can_verify(referee_id):
            self._reject_unverifiable(msg)
            return
        bound = self._incident_referee.get(incident_id)
        if bound is None:
            self._incident_referee[incident_id] = referee_id
        elif bound != referee_id:
            self._reject_unverifiable(msg, reason="PROTOCOL_REJECTED")
            return
        print(f"[{self.name}] INCIDENT_NOTICE: event={event_type}  incident={incident_id}")
        if event_type == "INCIDENT_OPEN":
            # STD-027/028: record the Referee-declared deadline window and start (or
            # refresh to the later of) the assessment-deadline timer. The entry is
            # created if this notice precedes FEE_DEPOSIT so the declared window is
            # not lost; a deadline on an empty escrow is harmless because
            # FEE_REFUND_CLAIM requires a deposit.
            entry = self._escrow.setdefault(incident_id, {
                "deposits": {}, "currency": "USD", "released": False,
                "state": "ESCROWED", "deadline": None, "refunded": {},
                "reassessment_initiator": None
            })
            if "assessment_deadline_hours" in msg:
                entry["deadline_hours"] = msg["assessment_deadline_hours"]
            self._start_assessment_timer(entry)
        elif event_type == "ASSESSMENT_COMPLETE":
            # Store cert_id so Ka/Kc can validate FEE_CLAIM in split-Keeper scenarios.
            cert_id = msg.get("cert_id")
            if cert_id:
                self._prior_verdicts.setdefault(incident_id, []).append(cert_id)
            # Store Referee reference for explicit release_fee() call.
            referee_name = msg["_sender"]
            referee_agent = self.world.agents.get(referee_name)
            if referee_agent:
                entry = self._escrow.setdefault(incident_id, {
                    "deposits": {}, "currency": "USD", "released": False,
                    "state": "ESCROWED", "deadline": None, "refunded": {},
                    "reassessment_initiator": None
                })
                entry["_referee_tid"] = referee_agent.terminal_id
                # STD-028: ASSESSMENT_COMPLETE stops the timer (assessment finished in time).
                entry["deadline"] = None
        elif event_type == "APPEAL_RECEIVED":
            # RFC §6.3 — suspend FEE_RELEASE timer
            self._appeal_pending[incident_id] = True
        elif event_type == "APPEAL_ACCEPTED":
            # RFC §6.3 / STD-028 — reset timer; await new ASSESSMENT_COMPLETE
            self._appeal_pending[incident_id] = False
            entry = self._escrow.get(incident_id)
            if entry:
                self._start_assessment_timer(entry)
        elif event_type == "APPEAL_REJECTED":
            # RFC §6.3 — resume FEE_RELEASE timer
            self._appeal_pending[incident_id] = False
        elif event_type == "ASSESSMENT_WITHDRAWN":
            # RFC §6.17 — INCIDENT_NOTICE(ASSESSMENT_WITHDRAWN) is the settlement trigger.
            # The cancellation fee is the Referee's declared fee, carried in the notice.
            referee_agent = self.world.agents.get(msg["_sender"])
            if referee_agent:
                self._settle_withdrawal_escrow(incident_id, referee_agent.terminal_id,
                                               msg.get("cancellation_fee", 0))

    def _handle_anchor_chain_query(self, msg):
        """RFC §6.27, §6.28 — ledger disclosure: the target terminal's stored anchors within
        the requested window plus the governing SESSION_START (latest at or before
        range.start, returned verbatim even from outside the window). Signed query,
        authorized only for the Referee bound to the incident (G1 binding) or the target
        terminal itself (self-query) — anchor metadata reveals activity patterns and is
        not public the way Referee stats are.
        schema: schemas/anchor_chain_query.json, schemas/anchor_chain_result.json"""
        requester = msg["requester_id"]
        target    = msg["target_terminal_id"]
        if not self._can_verify(requester):
            self._reject_unverifiable(msg)
            return
        if requester != target and self._incident_referee.get(msg["incident_id"]) != requester:
            self._reject_unverifiable(msg, reason="PROTOCOL_REJECTED")
            return

        rng = msg["range"]
        # Sim timestamps share one strftime format, so string comparison is safe here.
        strip = lambda a: {k: v for k, v in a.items() if k != "_sender"}
        mine = sorted((a for a in self.anchors.values() if a["terminal_id"] == target),
                      key=lambda a: a["sequence_number"])
        in_window = [strip(a) for a in mine
                     if rng["start"] <= a["timestamp"] <= rng["end"]]
        session_start = None
        for a in mine:  # ascending sequence — the last qualifying declaration governs
            if a.get("action_type") == "SESSION_START" and a["timestamp"] <= rng["start"]:
                session_start = strip(a)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = {
            "type": "ANCHOR_CHAIN_RESULT",
            "incident_id": msg["incident_id"],
            "target_terminal_id": target,
            "count": len(in_window),
            "truncated": False,      # the sim applies no size cap
            "anchors": in_window,
            "session_start": session_start,
            "timestamp": now
        }
        print(f"[{self.name}] anchor chain query: {target}  -> {len(in_window)} record(s) in window")
        self.world.send(self.name, msg["_sender"], result)

    def _handle_verification(self, msg):
        """RFC §6.12, §6.13 — responds to VERIFICATION_QUERY by matching stored anchor hashes; schema: schemas/verification_query.json, schemas/verification_result.json"""
        ts_range = msg.get("original_timestamp_range", {})
        target_tid = msg.get("target_terminal_id")
        results = []

        for target_hash in msg["target_hashes"]:
            # Scope the match to the target terminal: a hash anchored by a DIFFERENT
            # terminal must not verify as this party's evidence (prevents a party from
            # claiming another terminal's anchored work — only observable on a Keeper
            # that holds more than one terminal's anchors).
            matched = next(
                (a for a in self.anchors.values()
                 if a["data_hash"] == target_hash
                 and (target_tid is None or a["terminal_id"] == target_tid)),
                None
            )

            if matched is None:
                is_matched, matched_record, reason = False, None, "NOT_FOUND"
            elif ts_range and not (ts_range["start"] <= matched["timestamp"] <= ts_range["end"]):
                is_matched, matched_record, reason = False, None, "TIMESTAMP_OUT_OF_RANGE"
            else:
                is_matched = True
                matched_record = {
                    "claim_id":    matched["claim_id"],
                    "terminal_id": matched["terminal_id"],
                    "timestamp":   matched["timestamp"],
                    "data_hash":   matched["data_hash"],
                    "public_key":  matched.get("public_key")
                }
                reason = "OK"

            print(f"[{self.name}] verification: hash={target_hash[:8]}...  -> {reason}")
            results.append({
                "target_hash":    target_hash,
                "matched":        is_matched,
                "matched_record": matched_record
            })

        result = {
            "type":        "VERIFICATION_RESULT",
            "incident_id": msg["incident_id"],
            "results":     results
        }
        self.world.send(self.name, msg["_sender"], result)

    def _store_profile(self, msg):
        """RFC §6.19 — stores REFEREE_PROFILE received from Referee; schema: schemas/referee_profile.json"""
        referee_id = msg["referee_id"]
        self._profiles[referee_id] = msg
        # G2/RFC §4.4: register the Referee's key from its profile. In a split-Keeper
        # topology this is the only channel by which a party's Keeper (Kc/Ka) obtains the
        # key to verify the Referee's FEE_CLAIM/FEE_RECEIPT (TOFU; won't overwrite an
        # anchor-registered key at the Referee's own Keeper).
        self._register_key(referee_id, msg.get("public_key"))
        print(f"[{self.name}] REFEREE_PROFILE stored: referee={referee_id[:8]}..."
              f"  status={msg['availability_status']}  network={msg['network']}  key registered")

    def _handle_discovery_request(self, msg):
        """RFC §6.18 — responds to REFEREE_DISCOVERY_REQUEST with matching profiles; schema: schemas/referee_discovery_request.json, schemas/referee_discovery_result.json"""
        from datetime import datetime, timezone
        filters = msg.get("filters", {})
        limit   = msg.get("limit", 10)
        now     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        matched = []
        for profile in self._profiles.values():
            if self._profile_matches(profile, filters):
                matched.append(profile)
                if len(matched) >= limit:
                    break
        result = {
            "type":     "REFEREE_DISCOVERY_RESULT",
            "profiles": matched,
            "count":    len(matched),
            "timestamp": now
        }
        print(f"[{self.name}] REFEREE_DISCOVERY_REQUEST: {len(matched)} referee(s) matched"
              f"  filters={list(filters.keys()) if filters else 'none'}")
        self.world.send(self.name, msg["_sender"], result)

    def _profile_matches(self, profile, filters):
        """Utility — checks if a stored REFEREE_PROFILE satisfies the filter dict from REFEREE_DISCOVERY_REQUEST"""
        if not filters:
            return True
        if "availability_status" in filters and profile["availability_status"] != filters["availability_status"]:
            return False
        if "network" in filters and profile["network"] != filters["network"]:
            return False
        if "fee_model" in filters and profile["fee"]["model"] != filters["fee_model"]:
            return False
        if "referee_id" in filters and profile["referee_id"] != filters["referee_id"]:
            return False
        if "jurisdiction_code" in filters:
            jc = filters["jurisdiction_code"]
            if not any(sp["jurisdiction_code"] == jc for sp in profile["conduct_norms"]):
                return False
        if "domain" in filters:
            d = filters["domain"]
            if not any(sp["domain"] == d for sp in profile["conduct_norms"]):
                return False
        if "max_fee" in filters:
            max_fee      = filters["max_fee"]
            fee_currency = filters.get("fee_currency")
            if profile["fee"]["model"] != "FREE":
                if fee_currency and profile["fee"]["currency"] != fee_currency:
                    return False
                if profile["fee"]["amount"] > max_fee:
                    return False
        if "min_assessments" in filters:
            stats = self._j_stats.get(profile["referee_id"], {})
            if stats.get("assessment_count", 0) < filters["min_assessments"]:
                return False
        return True
