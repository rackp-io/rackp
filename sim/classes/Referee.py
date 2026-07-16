# classes/Referee.py
import uuid
from classes.Agent import Agent
from classes.Hasher import hash_claim
from datetime import datetime, timezone, timedelta

class Referee(Agent):
    MINIMUM_APPEAL_ROUNDS = 3  # RFC protocol constant
    STANDARD_NORM = "rackp.standard.v1"  # §9.3 default ("Undeclared Norm")

    def __init__(self, name="R", keeper_name="K"):
        super().__init__(name)
        self._keeper_name = keeper_name
        # incident_id -> {parties: [str], results: {submitter_id: bool}, target_period: {}}
        self._incidents = {}
        # target_hash -> (incident_id, submitter_id)
        self._pending_verifications = {}
        # target_hash -> appeal_msg  (dedicated queue for appeal verification)
        self._pending_appeal_verifications = {}
        self._anchor_seq = 0
        self._assessment_count = 0
        # incident_id -> {deposited: [...], missing: [...]}
        self._fee_status = {}
        # incident_id -> {submitter_id -> int}  (R tracks appeal counts internally)
        self._appeal_counts = {}
        # incident_id -> ASSESSMENT_APPEAL msg (stored until verify_appeal_evidence() is called)
        self._pending_appeals = {}
        # incident_id -> (verified: bool, appeal_msg, reason: str)
        self._appeal_verification_results = {}
        # incident_id -> {total: float, currency: str, keepers: set}  (accumulated from FEE_RELEASE)
        self._received_fees = {}
        # Referee's declared fee profile — the single source of truth, published in
        # REFEREE_PROFILE and snapshotted into fee_compliance.fee_snapshot (STD-026/029).
        # Default allocation splits fee.amount evenly per party. cancellation_fee is
        # deducted per Keeper on a joint withdrawal (§6.17; defaults to 0).
        # Explicit 50/50 cost-sharing allocation, DECLARED here (STD-029): both parties
        # owe half. The declaration is what makes the split legitimate — with no declared
        # fee.deposit the STD-029 default makes the requesting party (the Claimant in an
        # initial assessment) bear the full amount and the counterparty NOT_REQUIRED. Sim
        # scenarios exercise this declared joint-cost split, so each party owes 100.
        self._fee_profile = {"amount": 200.0, "currency": "USD", "cancellation_fee": 0.1,
                             "deposit": {"claimant": 100.0, "actor": 100.0}}
        # STD-027: declared assessment-deadline window (hours), published in
        # REFEREE_PROFILE and carried verbatim in each INCIDENT_NOTICE(INCIDENT_OPEN).
        # The sim declares the Standard Norm default explicitly so the field is
        # exercised end-to-end (Keeper arms its STD-028 timer from the notice value).
        self._assessment_deadline_hours = 720

    def request_evidence(self, target, incident_id="00000001-0000-4000-8000-000000000001",
                      prior_incident_ids=None):
        """RFC §5 Phase 3, §6.9 — sends EVIDENCE_QUERY_REQUEST to one party; schema: schemas/evidence_query_request.json"""
        inc = self._incidents.setdefault(incident_id, {"parties": [], "results": {}})
        if prior_incident_ids:
            inc.setdefault("prior_incident_ids", []).extend(prior_incident_ids)
        target_tid = self.world.agents[target].terminal_id
        inc["parties"].append(target_tid)

        now = datetime.now(timezone.utc)
        target_period = {
            "start": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": now.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        inc["target_period"] = target_period  # used in VERIFICATION_QUERY

        query = {
            "type": "EVIDENCE_QUERY_REQUEST",
            "incident_id": incident_id,
            "requester_id": self.terminal_id,
            "target_period": target_period,
            "required_fields": ["sensor_log", "decision_logic_id"],
            "response_deadline": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_human_readable_statement": False,
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        self.world.send(self.name, target, query)

    def finalize_incident(self, incident_id="00000001-0000-4000-8000-000000000001"):
        """RFC §5 Phase 4 — orchestrates FEE_STATUS_QUERY → CONTRIBUTION_RESULT → INCIDENT_NOTICE(ASSESSMENT_COMPLETE) → FEE_RELEASE"""
        self.query_fee_status(incident_id)
        self.issue_contribution_result(incident_id)
        self.notify_assessment_complete(incident_id)
        inc = self._incidents.get(incident_id, {})
        keeper_names = set(inc.get("keeper_map", {}).values()) or {self._keeper_name}
        for kn in keeper_names:
            keeper = self.world.agents.get(kn)
            if keeper and hasattr(keeper, "release_fee"):
                keeper.release_fee(incident_id)

    def query_fee_status(self, incident_id):
        """RFC §6.5 — sends FEE_STATUS_QUERY to each party's Keeper (split-Keeper aware); schema: schemas/fee_status_query.json"""
        inc = self._incidents.get(incident_id, {})
        parties = inc.get("parties", [])
        keeper_map = inc.get("keeper_map", {})
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for terminal_id in parties:
            kn = keeper_map.get(terminal_id, self._keeper_name)
            self.world.send(self.name, kn, {
                "type": "FEE_STATUS_QUERY",
                "incident_id": incident_id,
                "referee_id": self.terminal_id,
                "terminal_id": terminal_id,
                "timestamp": now
            })

    def issue_contribution_result(self, incident_id):
        """RFC §6.14 — computes fault and issues CONTRIBUTION_RESULT; also self-anchors ASSESSMENT_ISSUED; schema: schemas/contribution_result.json"""
        self._issue_result(incident_id)

    def notify_assessment_complete(self, incident_id):
        """RFC §6.3 — sends INCIDENT_NOTICE(ASSESSMENT_COMPLETE) to all relevant Keepers; schema: schemas/incident_notice.json"""
        inc = self._incidents.get(incident_id, {})
        cert_id = inc.get("cert_id", "")
        appeal_deadline = inc.get("appeal_deadline", "")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        keeper_names = set(inc.get("keeper_map", {}).values()) or {self._keeper_name}
        for kn in keeper_names:
            self.world.send(self.name, kn, {
                "type": "INCIDENT_NOTICE",
                "incident_id": incident_id,
                "referee_id": self.terminal_id,        # G1: signed, verified against the bound Referee
                "recipient_id": self.world.agents[kn].terminal_id,
                "event_type": "ASSESSMENT_COMPLETE",
                "cert_id": cert_id,
                "additional_appeal_limit_datetime": appeal_deadline,
                "timestamp": now,
                "signature": f"SIG_{self.terminal_id}"
            })

    def _send_incident_notice_to_keepers(self, event_type, incident_id):
        """RFC §6.3 — sends INCIDENT_NOTICE with given event_type to all party Keepers (Ka/Kc); schema: schemas/incident_notice.json"""
        inc = self._incidents.get(incident_id, {})
        keeper_names = set(inc.get("keeper_map", {}).values()) or {self._keeper_name}
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for kn in keeper_names:
            self.world.send(self.name, kn, {
                "type": "INCIDENT_NOTICE",
                "incident_id": incident_id,
                "referee_id": self.terminal_id,        # G1: signed, verified against the bound Referee
                "recipient_id": self.world.agents[kn].terminal_id,
                "event_type": event_type,
                "timestamp": now,
                "signature": f"SIG_{self.terminal_id}"
            })

    def verify_claim_chain(self, target, incident_id="00000001-0000-4000-8000-000000000001",
                           keeper_name="K",
                           range_start="2000-01-01T00:00:00Z", range_end="2099-12-31T23:59:59Z"):
        """RFC §6.27 — signed ANCHOR_CHAIN_QUERY (ledger disclosure): the basis for
        evidence_sufficiency coverage/gaps (§6.14), the §9.3 Norm retrieval, and the §8
        PoHI density evaluation. The sim default window is deliberately wide (sim clocks
        all run "now"), so SESSION_START anchors surface inside the window rather than
        as the governing session_start; schema: schemas/anchor_chain_query.json"""
        target_tid = self.world.agents[target].terminal_id
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = {
            "type": "ANCHOR_CHAIN_QUERY",
            "incident_id": incident_id,
            "requester_id": self.terminal_id,
            "target_terminal_id": target_tid,
            "range": {"start": range_start, "end": range_end},
            "timestamp": now,
            "signature": f"SIG_{self.terminal_id}"
        }
        self.world.send(self.name, keeper_name, query)

    def _handle_assessment_request(self, msg):
        """RFC §6.2, §6.3 — receives ASSESSMENT_REQUEST, sends INCIDENT_NOTICE(INCIDENT_OPEN) to Claimant's Keeper; schema: schemas/assessment_request.json"""
        incident_id  = msg["incident_id"]
        claimant_id  = msg["claimant_id"]
        actor_id     = msg.get("actor_id")
        keeper_ep    = msg["keeper_endpoint"]
        keeper_name  = keeper_ep[len("sim://"):] if keeper_ep.startswith("sim://") else self._keeper_name
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"[R] ASSESSMENT_REQUEST received: incident={incident_id}  claimant={claimant_id[:8]}...")

        inc = self._incidents.setdefault(incident_id, {"parties": [], "results": {}})
        inc["claimant_id"] = claimant_id
        inc["actor_id"]    = actor_id
        # Learn the Claimant's Keeper now, so escrow settlement/notices can route even
        # before any evidence is submitted (e.g. a withdrawal before Phase 3).
        inc.setdefault("keeper_map", {})[claimant_id] = keeper_name
        norms = msg.get("norm_profile_ids", ["rackp.standard.v1"])
        inc.setdefault("declared_norms", {})[claimant_id] = norms
        inc["target_period"] = {
            "start": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": now_str
        }

        # G2: publish this Referee's profile to the Claimant's Keeper before opening
        # the incident, so Kc holds the public_key needed to verify the Referee's later
        # FEE_CLAIM/FEE_RECEIPT (RFC §6.19). In the standard flow the profile rides with
        # the first INCIDENT_NOTICE(INCIDENT_OPEN) for the incident.
        self._send_profile(keeper_name)
        # Notify Keeper that incident is open
        self.world.send(self.name, keeper_name, {
            "type": "INCIDENT_NOTICE",
            "incident_id": incident_id,
            "referee_id": self.terminal_id,            # G1: binds the incident to this Referee
            "recipient_id": self.world.agents[keeper_name].terminal_id,
            "event_type": "INCIDENT_OPEN",
            "assessment_deadline_hours": self._assessment_deadline_hours,
            "timestamp": now_str,
            "signature": f"SIG_{self.terminal_id}"
        })

    def notify_actor_keeper_open(self, incident_id):
        """RFC §4.4, §6.3 — sends INCIDENT_NOTICE(INCIDENT_OPEN) to Actor's Keeper after ACTOR_ACKNOWLEDGMENT; schema: schemas/incident_notice.json"""
        inc = self._incidents.get(incident_id, {})
        actor_keeper_ep = inc.get("actor_keeper_endpoint", "")
        if not actor_keeper_ep:
            return
        kn = actor_keeper_ep[len("sim://"):] if actor_keeper_ep.startswith("sim://") else self._keeper_name
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # G2: publish the profile to the Actor's Keeper before opening, so Ka holds the
        # public_key to verify the Referee's later FEE_CLAIM/FEE_RECEIPT (RFC §6.19).
        self._send_profile(kn)
        self.world.send(self.name, kn, {
            "type": "INCIDENT_NOTICE",
            "incident_id": incident_id,
            "referee_id": self.terminal_id,            # G1: binds the incident to this Referee
            "recipient_id": self.world.agents[kn].terminal_id,
            "event_type": "INCIDENT_OPEN",
            "assessment_deadline_hours": self._assessment_deadline_hours,
            "timestamp": now,
            "signature": f"SIG_{self.terminal_id}"
        })

    def notify_actor(self, target, incident_id):
        """RFC §6.7 — sends ACTOR_NOTIFICATION to Actor; schema: schemas/actor_notification.json"""
        inc = self._incidents.get(incident_id, {})
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.world.send(self.name, target, {
            "type": "ACTOR_NOTIFICATION",
            "incident_id": incident_id,
            "referee_id": self.terminal_id,
            "claimant_id": inc.get("claimant_id", ""),
            "incident_summary": inc.get("incident_summary", "Incident reported by Claimant."),
            "incident_timestamp": now_str,
            "response_deadline": (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "timestamp": now_str,
            "signature": f"SIG_{self.terminal_id}"
        })

    def _handle_actor_acknowledgment(self, msg):
        """RFC §6.8 — receives ACTOR_ACKNOWLEDGMENT, stores Actor's Keeper endpoint and declared norm; schema: schemas/actor_acknowledgment.json"""
        incident_id = msg["incident_id"]
        actor_id    = msg["actor_id"]
        print(f"[R] ACTOR_ACKNOWLEDGMENT received: actor={actor_id[:8]}...")
        inc = self._incidents.get(incident_id, {})
        actor_keeper_ep = msg["actor_keeper_endpoint"]
        inc["actor_keeper_endpoint"] = actor_keeper_ep
        inc["actor_acknowledged"] = True  # STD-030 actor_participation disclosure
        # Learn the Actor's Keeper now (same reason as the Claimant's, above).
        if actor_keeper_ep.startswith("sim://"):
            inc.setdefault("keeper_map", {})[actor_id] = actor_keeper_ep[len("sim://"):]
        norms = msg.get("norm_profile_ids", ["rackp.standard.v1"])
        inc.setdefault("declared_norms", {})[actor_id] = norms

    def on_message(self, msg):
        """Dispatch handler for all inbound message types"""
        if msg["type"] == "ASSESSMENT_REQUEST":
            self._handle_assessment_request(msg)
        elif msg["type"] == "ACTOR_ACKNOWLEDGMENT":
            self._handle_actor_acknowledgment(msg)
        elif msg["type"] == "EVIDENCE_SUBMISSION":
            self._handle_submission(msg)
        elif msg["type"] == "VERIFICATION_RESULT":
            self._handle_verification_result(msg)
        elif msg["type"] == "ASSESSMENT_APPEAL":
            self._handle_appeal(msg)
        elif msg["type"] == "EVIDENCE_REJECTION":
            self._handle_evidence_rejection(msg)
        elif msg["type"] == "ASSESSMENT_WITHDRAWAL":
            self._handle_withdrawal(msg)
        elif msg["type"] == "ANCHOR_CHAIN_RESULT":
            self._handle_anchor_chain_result(msg)
        elif msg["type"] == "FEE_STATUS_RESULT":
            incident_id = msg["incident_id"]
            entry = self._fee_status.setdefault(incident_id, {
                "parties": {},
                "prior_assessment_count": 0,
                "prior_verdict_refs": []
            })
            entry["parties"][msg["terminal_id"]] = msg["deposited"]
            entry["prior_assessment_count"] = msg.get("prior_assessment_count", 0)
            if msg.get("prior_verdict_refs"):
                entry["prior_verdict_refs"] = msg["prior_verdict_refs"]
        elif msg["type"] == "FEE_RELEASE":
            self._handle_fee_release(msg)
        elif msg["type"] == "FEE_CLAIM_RESULT":
            self._handle_fee_claim_result(msg)

    def _handle_submission(self, msg):
        """RFC §6.10, §6.12 — receives EVIDENCE_SUBMISSION, computes hash independently, issues VERIFICATION_QUERY; schema: schemas/evidence_submission.json, schemas/verification_query.json"""
        v = msg["verification_info"]
        submitter_id = msg["submitter_id"]
        incident_id = msg["incident_id"]
        print(f"[R] evidence received from {submitter_id}: claim={v['claim_id']}")

        ext_claim = msg.get("external_factor_claim")
        if ext_claim:
            inc = self._incidents.get(incident_id, {})
            inc.setdefault("external_claims", {})[submitter_id] = ext_claim

        # PoHI artifact binding (RFC §8) rides in the generic submission payload. Capture it
        # so issue_phi_cert() can certify this Claimant-only assessment as a POH_CERTIFICATE.
        pohi = msg["payload"].get("pohi")
        if pohi:
            self._incidents.setdefault(incident_id, {"parties": [], "results": {}})["pohi_binding"] = pohi

        # Independently compute SHA-256 from payload (RFC 8785 canonicalization)
        computed_hash = hash_claim(msg["payload"]["raw_data"])
        reported_hash = v["stored_hash"]

        # Cross-check: record discrepancy if computed hash differs from self-reported stored_hash
        if computed_hash != reported_hash:
            print(f"[R] HASH DISCREPANCY: submitter={submitter_id}"
                  f"  computed={computed_hash[:8]}...  reported={reported_hash[:8]}...")
            inc = self._incidents.setdefault(incident_id, {})
            inc.setdefault("hash_discrepancies", []).append(
                f"{submitter_id}: payload hash mismatch"
                f" (computed={computed_hash[:8]}... reported={reported_hash[:8]}...)"
            )

        # Use computed hash (not self-reported) for Keeper verification
        self._pending_verifications[computed_hash] = (incident_id, submitter_id)

        # Route to the Keeper declared by the submitter (supports split-Keeper setups)
        keeper_ep = v.get("keeper_endpoint", f"sim://{self._keeper_name}")
        keeper_name = keeper_ep[len("sim://"):] if keeper_ep.startswith("sim://") else self._keeper_name
        # Record which Keeper each party uses, for INCIDENT_NOTICE routing
        self._incidents.setdefault(incident_id, {}).setdefault(
            "keeper_map", {})[submitter_id] = keeper_name

        period = self._incidents.get(incident_id, {}).get("target_period", {})
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = {
            "type": "VERIFICATION_QUERY",
            "incident_id": incident_id,
            "requester_id": self.terminal_id,
            "target_terminal_id": submitter_id,
            "target_hashes": [computed_hash],
            "original_timestamp_range": {
                "start": period.get("start", "2026-01-01T00:00:00Z"),
                "end":   period.get("end",   "2026-12-31T23:59:59Z")
            },
            "timestamp": now
        }
        self.world.send(self.name, keeper_name, query)

    def _handle_verification_result(self, msg):
        """RFC §6.13 — receives VERIFICATION_RESULT; routes to appeal or standard evidence flow; schema: schemas/verification_result.json"""
        result_entry = msg["results"][0]
        target_hash = result_entry["target_hash"]
        incident_id = msg["incident_id"]
        verified = result_entry["matched"]
        matched_record = result_entry["matched_record"]
        matched_claim_id = matched_record["claim_id"] if matched_record else None
        reason = "" if verified else "NOT_FOUND"

        # check if this is a verification result for an appeal
        if target_hash in self._pending_appeal_verifications:
            appeal_msg = self._pending_appeal_verifications.pop(target_hash)
            incident_id_a = appeal_msg["incident_id"]
            status = "VERIFIED" if verified else "NOT_FOUND"
            print(f"[R] appeal verification: {status}")
            self._appeal_verification_results[incident_id_a] = (verified, appeal_msg, reason or "NOT_FOUND")
            return

        # standard evidence verification result
        entry = self._pending_verifications.pop(target_hash, None)
        submitter_id = entry[1] if entry else "unknown"

        status = "VERIFIED" if verified else "FAILED"
        print(f"[R] verification: {submitter_id}  {status}  matched={matched_claim_id}"
              + (f"  reason={reason}" if reason else ""))

        inc = self._incidents.get(incident_id)
        if inc:
            inc["results"][submitter_id] = verified

    def _handle_evidence_rejection(self, msg):
        """RFC §6.11 — receives EVIDENCE_REJECTION, anchors EVIDENCE_REJECTED, marks party as non-participating; schema: schemas/evidence_rejection.json"""
        incident_id  = msg["incident_id"]
        submitter_id = msg["submitter_id"]
        reason       = msg.get("reason", "")
        print(f"[R] EVIDENCE_REJECTION: {submitter_id[:8]}...  incident={incident_id}"
              + (f"  reason={reason}" if reason else ""))
        inc = self._incidents.setdefault(incident_id, {"parties": [], "results": {}})
        inc["results"][submitter_id] = False
        self._send_action_anchor("EVIDENCE_REJECTED", incident_id)

    def _handle_appeal(self, msg):
        """RFC §6.16 — receives ASSESSMENT_APPEAL, anchors APPEAL_RECEIVED, stores for verify_appeal_evidence(); schema: schemas/assessment_appeal.json"""
        incident_id  = msg["incident_id"]
        submitter_id = msg["submitter_id"]
        counts = self._appeal_counts.setdefault(incident_id, {})
        counts[submitter_id] = counts.get(submitter_id, 0) + 1
        appeal_count = counts[submitter_id]
        print(f"\n[R] ASSESSMENT_APPEAL received from {submitter_id}"
              f"  incident={incident_id}  count={appeal_count}")
        self._send_action_anchor("APPEAL_RECEIVED", incident_id)
        self._send_incident_notice_to_keepers("APPEAL_RECEIVED", incident_id)
        self._pending_appeals[incident_id] = msg

    def verify_appeal_evidence(self, incident_id):
        """RFC §6.16 — sends VERIFICATION_QUERY for pending appeal's additional evidence; result stored in _appeal_verification_results for accept_appeal() or reject_pending_appeal(); schema: schemas/verification_query.json"""
        appeal_msg = self._pending_appeals.get(incident_id)
        if not appeal_msg:
            print(f"[R] no pending appeal for incident={incident_id}")
            return
        submitter_id = appeal_msg["submitter_id"]
        additional_evidence = appeal_msg.get("additional_evidence")
        if not additional_evidence:
            print(f"[R] appeal: no additional evidence provided")
            self._appeal_verification_results[incident_id] = (False, appeal_msg, "no evidence provided")
            return
        v_info = additional_evidence["verification_info"]
        self._pending_appeal_verifications[v_info["stored_hash"]] = appeal_msg
        period = self._incidents.get(incident_id, {}).get("target_period", {})
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = {
            "type": "VERIFICATION_QUERY",
            "incident_id": incident_id,
            "requester_id": self.terminal_id,
            "target_terminal_id": submitter_id,
            "target_hashes": [v_info["stored_hash"]],
            "original_timestamp_range": {
                "start": period.get("start", "2026-01-01T00:00:00Z"),
                "end":   period.get("end",   "2026-12-31T23:59:59Z")
            },
            "timestamp": now
        }
        # Route to the appealing party's OWN Keeper (where its anchors live), derived
        # from the appeal evidence's keeper_endpoint — not the Referee's own Keeper.
        keeper_ep = v_info.get("keeper_endpoint", "")
        keeper_name = (keeper_ep[len("sim://"):] if keeper_ep.startswith("sim://")
                       else self._incidents.get(incident_id, {})
                                .get("keeper_map", {}).get(submitter_id, self._keeper_name))
        self.world.send(self.name, keeper_name, query)
        # _handle_verification_result stores result in _appeal_verification_results

    def accept_appeal(self, incident_id):
        """RFC §6.16 — updates appellant's evidence result to verified, anchors APPEAL_ACCEPTED; call issue_contribution_result() and notify_assessment_complete() next; schema: schemas/claim_anchor.json"""
        result = self._appeal_verification_results.get(incident_id)
        if not result:
            print(f"[R] no verification result for incident={incident_id}")
            return
        verified, appeal_msg, _ = result
        if not verified:
            print(f"[R] cannot accept: appeal evidence not verified")
            return
        submitter_id = appeal_msg["submitter_id"]
        inc = self._incidents.get(incident_id, {})
        print(f"\n[R] === APPEAL ACCEPTED: {incident_id} ===")
        print(f"[R]   {submitter_id[:8]}... additional evidence verified -> updating result")
        inc["results"][submitter_id] = True
        self._send_action_anchor("APPEAL_ACCEPTED", incident_id)
        self._send_incident_notice_to_keepers("APPEAL_ACCEPTED", incident_id)

    def reject_pending_appeal(self, incident_id):
        """RFC §6.16 — notifies all parties their appeal was rejected (the direct party message is sim convenience, no dedicated schema), self-anchors action_type=APPEAL_REJECTED and notifies Keepers event_type=APPEAL_REJECTED; schemas: schemas/claim_anchor.json, schemas/incident_notice.json"""
        appeal_msg = self._pending_appeals.get(incident_id)
        if not appeal_msg:
            print(f"[R] no pending appeal for incident={incident_id}")
            return
        result = self._appeal_verification_results.get(incident_id)
        reason = result[2] if result else "evidence not verified"
        submitter_id = appeal_msg["submitter_id"]
        inc = self._incidents.get(incident_id, {})

        rejection = {
            "type": "APPEAL_REJECTED",
            "incident_id": incident_id,
            "submitter_id": submitter_id,
            "reason": reason
        }

        appeal_count = self._appeal_counts.get(incident_id, {}).get(submitter_id, 1)
        rounds_remaining = max(0, self.MINIMUM_APPEAL_ROUNDS - appeal_count)

        print(f"\n[R] === APPEAL REJECTED: {incident_id} ===")
        print(f"[R]   reason: {reason}")
        if rounds_remaining > 0:
            print(f"[R]   {rounds_remaining} appeal round(s) still available under MINIMUM_APPEAL_ROUNDS.")
        else:
            print(f"[R]   initial assessment stands.")

        parties = list(dict.fromkeys(inc.get("parties", [])))
        for party_tid in parties:
            self.world.send(self.name, self.world.route_by_tid(party_tid), rejection)
        self._send_action_anchor("APPEAL_REJECTED", incident_id)
        self._send_incident_notice_to_keepers("APPEAL_REJECTED", incident_id)

    def _issue_result(self, incident_id):
        """RFC §6.14, §7 — core fault computation (Verification Outcome Table + STD-010) and CONTRIBUTION_RESULT issuance; schema: schemas/contribution_result.json"""
        inc = self._incidents.get(incident_id)
        if not inc:
            print(f"[R] no incident found: {incident_id}")
            return

        # deduplicate preserving order (appeal round may re-add a party)
        parties = list(dict.fromkeys(inc["parties"]))
        results = inc["results"]

        # parties[0] = actor (respondent), parties[1] = claimant (filing party)
        actor_id    = parties[0] if len(parties) > 0 else None
        claimant_id = parties[1] if len(parties) > 1 else None

        # A party that was queried but submitted nothing FAILS verification: §7
        # treats "not submitted" as FAILED, symmetrically for Actor and Claimant
        # ("strategic unreachability unrewarded in both directions"). The previous
        # default of True for the Claimant wrongly credited a silent filing party. A
        # single-requester flow has no claimant_id and is handled via no_actor below,
        # so it retains the prior default.
        actor_verified    = results.get(actor_id, False)
        claimant_verified = results.get(claimant_id, False) if claimant_id is not None else True

        # RFC Section 7 — minimum reference logic (Verification Outcome Table)
        # Implementations MAY extend provided norms_used describes any deviation.
        if actor_verified and claimant_verified:
            actor_fault, claimant_fault = 0.5, 0.5
            confidence = "HIGH"
        elif not actor_verified and claimant_verified:
            actor_fault, claimant_fault = 0.8, 0.2
            confidence = "MEDIUM"
        elif actor_verified and not claimant_verified:
            actor_fault, claimant_fault = 0.2, 0.8
            confidence = "MEDIUM"
        else:
            actor_fault, claimant_fault = 0.5, 0.5
            confidence = "LOW"

        # external_factor: only claims from verified parties are accepted
        external_factor = 0.0
        if actor_verified and claimant_verified:
            external_claims = inc.get("external_claims", {})
            valid_claim_count = sum(
                1 for pid in [actor_id, claimant_id]
                if pid and external_claims.get(pid, {}).get("claimed") is True
            )
            if valid_claim_count == 1:
                external_factor = 0.4
                confidence = "MEDIUM"
            elif valid_claim_count == 2:
                external_factor = 0.8
            actor_fault    = round(actor_fault    * (1.0 - external_factor), 10)
            claimant_fault = round(claimant_fault * (1.0 - external_factor), 10)

        # STD-010 / STD-026: fee compliance is DISCLOSED ONLY. Non-payment MUST NOT
        # be factored into the fault values and MUST NOT be listed in
        # technical_violation — the fault values measure deviation from the declared
        # Norms in the incident itself, never participation funding. The deposit
        # status is recorded as-is in assessment.fee_compliance so downstream
        # consumers can weigh it in their own context (RFC-0001 §7, RFC-0002 §1.6).
        fee_status = self._fee_status.get(incident_id, {})
        fee_parties = fee_status.get("parties", {})
        no_actor = claimant_id is None  # single-requester assessment (parties[0] only)
        fee_compliance = self._build_fee_compliance(
            actor_id, claimant_id, fee_parties, no_actor)
        # STD-030: actor participation is likewise DISCLOSED ONLY.
        actor_participation = self._build_actor_participation(inc, no_actor)

        evidence_sufficiency = self._evaluate_evidence_sufficiency(
            incident_id, actor_id, claimant_id)

        # technical_violation holds genuine integrity/norm violations only (e.g. hash
        # discrepancies) — never fee non-payment, which is disclosed via fee_compliance.
        technical_violation = list(inc.get("hash_discrepancies", []))

        # Detect norm jurisdiction mismatch (§9.3)
        norm_mismatch = None
        declared_norms = inc.get("declared_norms", {})
        if actor_id and claimant_id and len(declared_norms) >= 2:
            actor_norms    = set(declared_norms.get(actor_id, []))
            claimant_norms = set(declared_norms.get(claimant_id, []))
            if actor_norms and claimant_norms and actor_norms.isdisjoint(claimant_norms):
                norm_mismatch = (
                    f"Actor declared {sorted(actor_norms)}, Claimant declared {sorted(claimant_norms)}. "
                    f"No common Norm - discrepancy recorded per RFC-0001 S9.5. "
                    f"Referee assessed using norms_used as listed; parties should verify "
                    f"that the declared Norms share a common jurisdiction."
                )

        # norms_used (§9.3, §9.5): the Norm Profile(s) actually used as the
        # basis of assessment — each party's Norm as declared at session start and read
        # back from its anchor chain. A party that declared none falls back to the
        # Standard Norm (§9.3 "Undeclared Norm"). This MUST reflect the declared Norms,
        # never a fixed constant, so a jurisdiction mismatch surfaces the real profiles.
        norms_used = set()
        for pid in (actor_id, claimant_id):
            if not pid:
                continue
            pn = declared_norms.get(pid)
            norms_used.update(pn if pn else [self.STANDARD_NORM])
        norms_used = sorted(norms_used) if norms_used else [self.STANDARD_NORM]

        self._assessment_count += 1
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        # A monotonic suffix keeps the cert_id unique even when two verdicts for the
        # same incident are issued within the same wall-clock second (e.g. an appeal
        # revision in a fast run); ID uniqueness must not depend on timing granularity.
        cert_id = f"CERT-{incident_id}-{now.strftime('%Y%m%d%H%M%S')}-{self._assessment_count:04d}"
        inc["cert_id"] = cert_id
        appeal_deadline = (now + timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%SZ")
        inc["appeal_deadline"] = appeal_deadline

        result = {
            "type": "CONTRIBUTION_RESULT",
            "network": "TESTNET",
            "incident_id": incident_id,
            "referee_id": self.terminal_id,
            "referee_reputation_snapshot": {
                "total_assessments": self._assessment_count,
                "snapshot_timestamp": now_str
            },
            "assessment": {
                "factual_findings": self._summarize_findings(results),
                "fault": {
                    "actor_fault": actor_fault,
                    "claimant_fault": claimant_fault,
                    "external_factor": external_factor,
                    "confidence": confidence
                },
                "technical_violation": technical_violation,
                "evidence_sufficiency": evidence_sufficiency,
                "fee_compliance": fee_compliance,
                "actor_participation": actor_participation,
                "provenance_score": {
                    "actor_provenance":    {"human_ratio": 0.2, "ai_ratio": 0.8},
                    "claimant_provenance": {"human_ratio": 0.1, "ai_ratio": 0.9},
                    "confidence_level": confidence
                },
                "norms_used": norms_used,
                **({"norm_jurisdiction_mismatch": norm_mismatch} if norm_mismatch else {}),
                "detailed_report": {
                    "report_url":  f"https://rackp.example/reports/{incident_id}",
                    "report_hash": "a" * 64
                },
                "certification": {
                    "cert_id":    cert_id,
                    "issue_date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "cert_url":   f"https://rackp.example/verify/{cert_id}",
                    "proof_hash": "b" * 64
                }
            },
            "evidence_provenance": ", ".join(
                f"{k}={'VERIFIED' if v else 'FAILED'}" for k, v in results.items()
            ),
            "additional_appeal_limit_datetime": appeal_deadline,
            "prior_assessment_count": fee_status.get("prior_assessment_count", 0),
            "prior_verdict_refs": fee_status.get("prior_verdict_refs", []) or [],
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        prior_count = result["prior_assessment_count"]
        prior_inc_ids = inc.get("prior_incident_ids", [])
        print(f"\n[R] === CONTRIBUTION_RESULT: {incident_id} ===")
        if prior_inc_ids:
            print(f"[R]   prior_incident_ids: {prior_inc_ids}")
        if prior_count > 0:
            print(f"[R]   RE-ASSESSMENT (STD-020): prior_count={prior_count}"
                  f"  refs={result['prior_verdict_refs']}")
        print(f"[R]   findings : {result['assessment']['factual_findings']}")
        print(f"[R]   actor_fault={actor_fault}  claimant_fault={claimant_fault}"
              f"  external_factor={external_factor}  confidence={confidence}")
        print(f"[R]   assessment_status={evidence_sufficiency['assessment_status']}"
              f"  actor_coverage={evidence_sufficiency['actor_coverage']}"
              f"  claimant_coverage={evidence_sufficiency['claimant_coverage']}")
        if evidence_sufficiency["gaps"]:
            for g in evidence_sufficiency["gaps"]:
                print(f"[R]   gap: {g['party_id']} - {g['description']}")
        if norm_mismatch:
            print(f"[R]   NORM_MISMATCH: {norm_mismatch}")
        print(f"[R]   cert_id  : {cert_id}")
        print(f"[R]   cert_url : {result['assessment']['certification']['cert_url']}")
        print(f"[R]   report   : {result['assessment']['detailed_report']['report_url']}")
        print(f"[R]   appeal_deadline: {result['additional_appeal_limit_datetime']}")
        print(f"[R]   referee_snapshot: total_assessments={self._assessment_count}"
              f"  snapshot_timestamp={result['referee_reputation_snapshot']['snapshot_timestamp']}")

        for party_tid in parties:
            self.world.send(self.name, self.world.route_by_tid(party_tid), result)
        self._send_action_anchor("ASSESSMENT_ISSUED", incident_id, cert_id=cert_id)

    def _summarize_findings(self, results):
        """Utility — builds factual_findings string from verification results for CONTRIBUTION_RESULT.
        Fee compliance is never mentioned here: it is disclosed only via fee_compliance (STD-010)."""
        verified = [k for k, v in results.items() if v]
        failed   = [k for k, v in results.items() if not v]
        parts = []
        if verified:
            parts.append(f"{', '.join(verified)}: evidence verified")
        if failed:
            parts.append(f"{', '.join(failed)}: evidence tampered or not submitted")
        return ". ".join(parts) + "."

    def _build_fee_compliance(self, actor_id, claimant_id, fee_parties, no_actor):
        """STD-026 — per-party deposit status plus a fee_snapshot of the Referee's
        pricing at issuance, populated from FEE_STATUS_RESULT. Disclosure only:
        these values never influence the fault computation."""
        total    = self._fee_profile["amount"]
        currency = self._fee_profile["currency"]
        allocation = self._fee_profile.get("deposit")
        # STD-029: a sole requester owes the full amount. Otherwise a DECLARED fee.deposit
        # allocation governs each role's expected share; with NO declared allocation the
        # requester (Claimant) bears the full amount and the counterparty is NOT_REQUIRED.
        if no_actor:
            claimant_expected, actor_expected = total, 0.0
        elif allocation:
            claimant_expected = allocation.get("claimant", 0.0)
            actor_expected    = allocation.get("actor", 0.0)
        else:
            claimant_expected, actor_expected = total, 0.0

        def label(party_id, expected):
            # A role with no expected share owes nothing (STD-029 → NOT_REQUIRED); else its
            # FEE_STATUS_RESULT bool gives DEPOSITED/NOT_DEPOSITED, absence ⇒ Keeper unreachable.
            if expected == 0:
                return "NOT_REQUIRED"
            if party_id not in fee_parties:
                return "UNKNOWN"
            return "DEPOSITED" if fee_parties[party_id] else "NOT_DEPOSITED"

        return {
            "actor_fee_status": "NOT_REQUIRED" if no_actor else label(actor_id, actor_expected),
            "claimant_fee_status": label(claimant_id, claimant_expected),
            "fee_snapshot": {
                "total_amount": total,
                "claimant_expected": claimant_expected,
                "actor_expected": actor_expected,
                "currency": currency,
            },
        }

    def _build_actor_participation(self, inc, no_actor):
        """STD-030 — whether and how the Actor was reached at issuance time.
        Disclosure only: never influences the fault computation. For any reached/
        attempted status the schema requires a notification_record (if/then)."""
        if no_actor:
            return {"status": "NOT_APPLICABLE"}
        acknowledged = bool(inc.get("actor_acknowledged"))
        return {
            "status": "ACKNOWLEDGED" if acknowledged else "NOTIFIED_NO_RESPONSE",
            "notification_record": {
                # The Actor's identity always originates from the Claimant's
                # ASSESSMENT_REQUEST in this sim, never a Norm registry.
                "endpoint_source": "CLAIMANT_PROVIDED",
                "delivery_confirmed": acknowledged,
                "attempt_count": 1,
            },
        }

    def issue_phi_cert(self, incident_id):
        """RFC §8 — issues a POH_CERTIFICATE for a Claimant-only (no-Actor) assessment whose
        EVIDENCE_SUBMISSION carried a PoHI artifact binding. The canonical §8 flow reuses the
        generic messages (ASSESSMENT_REQUEST without actor_id → EVIDENCE_QUERY_REQUEST →
        EVIDENCE_SUBMISSION → POH_CERTIFICATE); there is NO PoHI-specific message. Call after
        verify_claim_chain() has surfaced the Claimant's anchor chain.
        schema: schemas/poh_certificate.json"""
        inc = self._incidents.get(incident_id)
        if not inc:
            print(f"[{self.name}] issue_phi_cert: no incident {incident_id}")
            return
        claimant_tid = inc.get("claimant_id")
        binding      = inc.get("pohi_binding")
        if not claimant_tid or not binding:
            print(f"[{self.name}] issue_phi_cert: no PoHI binding/claimant for {incident_id}")
            return
        count       = inc.get("anchor_coverage", {}).get(claimant_tid, {}).get("count", 0)
        keeper_name = inc.get("keeper_map", {}).get(claimant_tid, self._keeper_name)
        self._finalize_phi_cert(incident_id, claimant_tid, keeper_name, count, binding)

    def _finalize_phi_cert(self, incident_id, claimant_tid, keeper_name, count, binding):
        """RFC §8 — computes the provenance ratio from anchor density (the Claimant's chain
        surfaced by ANCHOR_CHAIN_QUERY) and issues a POH_CERTIFICATE bound to the artifact's
        subject_data_hash; schema: schemas/poh_certificate.json"""
        human_ratio = min(1.0, round(count / 5.0, 2)) if count > 0 else 0.0
        ai_ratio    = round(1.0 - human_ratio, 2)
        confidence  = "HIGH" if count >= 5 else ("MEDIUM" if count >= 2 else "LOW")

        now_str       = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cert_id       = str(uuid.uuid4())
        claimant_name = self.world.route_by_tid(claimant_tid)
        anchor_range  = binding.get("anchor_range", {})

        cert = {
            "type":               "POH_CERTIFICATE",
            "cert_id":            cert_id,
            "issue_date":         now_str,
            "referee_id":         self.terminal_id,
            "subject_terminal_id": claimant_tid,
            "anchor_range":       {"start": anchor_range.get("start", now_str),
                                   "end":   anchor_range.get("end",   now_str)},
            "provenance": {
                "human_ratio":     human_ratio,
                "ai_ratio":        ai_ratio,
                "confidence_level": confidence
            },
            "keeper": {
                "keeper_id":       self.world.agents[keeper_name].terminal_id,
                "keeper_endpoint": f"sim://{keeper_name}"
            },
            "subject_data_hash": binding["subject_data_hash"],
            "cert_url":   f"https://rackp.example/phi/{cert_id}",
            "proof_hash": "e" * 64,
            "signature":  f"SIG_{self.terminal_id}_phi_{cert_id[:8]}"
        }

        print(f"\n[{self.name}] === POH_CERTIFICATE issued ===")
        print(f"[{self.name}]   cert_id:      {cert_id}")
        print(f"[{self.name}]   subject:      {claimant_tid[:8]}...")
        print(f"[{self.name}]   anchor_count: {count}"
              f"  human_ratio: {human_ratio}  confidence: {confidence}")
        print(f"[{self.name}]   cert_url:     {cert['cert_url']}")

        # Self-anchor cert issuance with action_type POH_CERT_ISSUED to the Referee's own
        # Keeper — the PoHI analogue of the ASSESSMENT_ISSUED anchor (RFC §8.4). It feeds
        # poh_cert_count and the per-artifact license reconciliation (RFC-0002 §1.3), and is
        # counted SEPARATELY from assessment_count: a PoHI cert is not an incident assessment,
        # so it must not pollute the appeal_rate / named_as_actor_rate denominators. Escrow
        # settlement is still driven by INCIDENT_NOTICE(ASSESSMENT_COMPLETE) below, not here.
        self._send_action_anchor("POH_CERT_ISSUED", incident_id=incident_id, cert_id=cert_id)
        self.world.send(self.name, claimant_name, cert)

        # Register cert_id so the Claimant's Keeper can validate a later FEE_CLAIM (pull path).
        inc = self._incidents.setdefault(incident_id, {})
        inc["cert_id"] = cert_id
        inc.setdefault("keeper_map", {})[claimant_tid] = keeper_name
        self.world.send(self.name, keeper_name, {
            "type":         "INCIDENT_NOTICE",
            "incident_id":  incident_id,
            "referee_id":   self.terminal_id,          # G1: signed, verified against the bound Referee
            "recipient_id": self.world.agents[keeper_name].terminal_id,
            "event_type":   "ASSESSMENT_COMPLETE",
            "cert_id":      cert_id,
            "additional_appeal_limit_datetime": now_str,
            "timestamp":    now_str,
            "signature":    f"SIG_{self.terminal_id}"
        })

    def notify_actor_named(self, actor_name, incident_id):
        """RFC §4.1, §6.7 — anchors NAMED_AS_ACTOR to own Keeper; named_actor_id (sim-only) routes stats update to the correct terminal; schema: schemas/claim_anchor.json"""
        actor_tid = self.world.agents[actor_name].terminal_id
        self._anchor_seq += 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload   = {"action_type": "NAMED_AS_ACTOR", "incident_id": incident_id,
                     "seq": self._anchor_seq}
        data_hash = hash_claim(payload)
        anchor = {
            "type":            "CLAIM_ANCHOR",
            "terminal_id":     self.terminal_id,
            "claim_id":        str(uuid.uuid4()),
            "sequence_number": self._anchor_seq,
            "timestamp":       now,
            "data_hash":       data_hash,
            "action_type":     "NAMED_AS_ACTOR",
            "incident_id":     incident_id,
            "signature":       f"SIG_{self.terminal_id}_{self._anchor_seq}",
            "named_actor_id":  actor_tid
        }
        if self._anchor_seq == 1:
            anchor["public_key"] = f"PUBKEY_{self.terminal_id}"
        self.world.send(self.name, self._keeper_name, anchor)

    def _build_profile(self):
        """Builds this Referee's REFEREE_PROFILE. public_key matches the key the
        Referee registers via its seq-1 CLAIM_ANCHOR (G2): a party's Keeper never
        sees that anchor, so the profile is its only channel to the key needed to
        verify FEE_CLAIM/FEE_RECEIPT (RFC §6.19, §4.4)."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "type": "REFEREE_PROFILE",
            "network": "TESTNET",
            "referee_id": self.terminal_id,
            "public_key": f"PUBKEY_{self.terminal_id}",
            "endpoint": f"sim://{self.name}",
            "keeper_endpoint": f"sim://{self._keeper_name}",
            "conduct_norms": [
                {
                    "jurisdiction_code": "GLOBAL",
                    "domain": "general",
                    "norm_profile_id": "rackp.standard.v1"
                }
            ],
            "availability_status": "AVAILABLE",
            "fee": {
                "model": "FIXED",
                "amount": self._fee_profile["amount"],
                "currency": self._fee_profile["currency"],
                "cancellation_fee": self._fee_profile.get("cancellation_fee", 0),
                # Publish the declared allocation so the 50/50 split is opt-in on record,
                # not an undeclared deviation from the STD-029 requester-pays-full default.
                **({"deposit": self._fee_profile["deposit"]} if self._fee_profile.get("deposit") else {})
            },
            "assessment_deadline_hours": self._assessment_deadline_hours,
            "profile_timestamp": now
        }

    def _send_profile(self, keeper_name):
        """RFC §6.19 — sends REFEREE_PROFILE to a Keeper (message only, no SESSION_START
        anchor). A party's Keeper registers this Referee's public_key from it (G2), the
        only channel by which Kc/Ka obtain the key to verify FEE_CLAIM/FEE_RECEIPT."""
        print(f"[{self.name}] publishing REFEREE_PROFILE -> {keeper_name}")
        self.world.send(self.name, keeper_name, self._build_profile())

    def publish_profile(self, keeper_name="K"):
        """RFC §6.19 — publishes REFEREE_PROFILE to the Referee's own Keeper for discovery
        and declares its Norms via a SESSION_START anchor (the profile is the Referee's
        norm declaration, equivalent to SESSION_START); schema: schemas/referee_profile.json"""
        profile = self._build_profile()
        self._send_profile(keeper_name)
        norm_profiles = [
            {"norm_profile_id": cn["norm_profile_id"], "norm_fetch_url": f"https://rackp.example/norms/{cn['norm_profile_id']}"}
            for cn in profile["conduct_norms"]
        ]
        self._send_action_anchor("SESSION_START", norm_profiles=norm_profiles)

    def _handle_fee_release(self, msg):
        """RFC §6.15 — receives FEE_RELEASE from Keeper; records per-Keeper released amount for send_fee_receipt(); schema: schemas/fee_release.json"""
        incident_id     = msg["incident_id"]
        released_amount = msg["released_amount"]
        currency        = msg["currency"]
        print(f"[{self.name}] FEE_RELEASE received:"
              f"  incident={incident_id}"
              f"  released_amount={released_amount} {currency}")
        entry = self._received_fees.setdefault(incident_id, {
            "currency": currency, "keepers": {}, "triggered_by": "FEE_RELEASE"
        })
        entry["keepers"][msg["_sender"]] = released_amount

    def claim_fee(self, incident_id):
        """RFC §6.22 — sends FEE_CLAIM to Keeper(s) as pull-based alternative to waiting for FEE_RELEASE; schema: schemas/fee_claim.json"""
        from datetime import datetime, timezone
        inc          = self._incidents.get(incident_id, {})
        cert_id      = inc.get("cert_id", "")
        keeper_names = set(inc.get("keeper_map", {}).values()) or {self._keeper_name}
        now          = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._send_action_anchor(incident_id=incident_id)
        for kn in keeper_names:
            self.world.send(self.name, kn, {
                "type":        "FEE_CLAIM",
                "incident_id": incident_id,
                "referee_id":  self.terminal_id,
                "cert_id":     cert_id,
                "currency":    "USD",
                "timestamp":   now,
                "signature":   f"SIG_{self.terminal_id}_claim_{incident_id[:8]}"
            })

    def _handle_fee_claim_result(self, msg):
        """RFC §6.23 — receives FEE_CLAIM_RESULT; on ACCEPTED stores in _received_fees for send_fee_receipt(); schema: schemas/fee_claim_result.json"""
        incident_id = msg["incident_id"]
        status      = msg["status"]
        if status == "ACCEPTED":
            released_amount = msg["released_amount"]
            currency        = msg["currency"]
            print(f"[{self.name}] FEE_CLAIM_RESULT ACCEPTED:"
                  f"  incident={incident_id}  amount={released_amount} {currency}")
            entry = self._received_fees.setdefault(incident_id, {
                "currency": currency, "keepers": {}, "triggered_by": "FEE_CLAIM_RESULT"
            })
            entry["keepers"][msg["_sender"]] = released_amount
        else:
            reason = msg.get("rejection_reason", "")
            print(f"[{self.name}] FEE_CLAIM_RESULT REJECTED:"
                  f"  incident={incident_id}  reason={reason}")

    def send_fee_receipt(self, incident_id):
        """RFC §6.24 — sends FEE_RECEIPT to each releasing Keeper for the amount that Keeper released; schema: schemas/fee_receipt.json"""
        from datetime import datetime, timezone
        entry = self._received_fees.get(incident_id)
        if not entry:
            print(f"[{self.name}] send_fee_receipt: no FEE_RELEASE received for incident={incident_id}")
            return
        inc     = self._incidents.get(incident_id, {})
        cert_id = inc.get("cert_id", "")
        now     = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._send_action_anchor(incident_id=incident_id)
        for keeper_name, amount in entry["keepers"].items():
            receipt = {
                "type":            "FEE_RECEIPT",
                "incident_id":     incident_id,
                "referee_id":      self.terminal_id,
                "cert_id":         cert_id,
                "received_amount": amount,
                "currency":        entry["currency"],
                "triggered_by":    entry.get("triggered_by", "FEE_RELEASE"),
                "timestamp":       now,
                "signature":       f"SIG_{self.terminal_id}_receipt_{incident_id[:8]}"
            }
            self.world.send(self.name, keeper_name, receipt)
        # §6.24: reputation is queried at the Referee's own Keeper (§6.20), so a copy of
        # the receipt goes there too — the copy is what closes the unreceived_count
        # obligation opened by the ASSESSMENT_ISSUED / POH_CERT_ISSUED anchor (§6.21).
        # Skipped when the own Keeper already received the receipt as a releasing Keeper.
        if self._keeper_name not in entry["keepers"]:
            copy = {
                "type":            "FEE_RECEIPT",
                "incident_id":     incident_id,
                "referee_id":      self.terminal_id,
                "cert_id":         cert_id,
                "received_amount": sum(entry["keepers"].values()),
                "currency":        entry["currency"],
                "triggered_by":    entry.get("triggered_by", "FEE_RELEASE"),
                "timestamp":       now,
                "signature":       f"SIG_{self.terminal_id}_receipt_{incident_id[:8]}"
            }
            self.world.send(self.name, self._keeper_name, copy)

    def _send_action_anchor(self, action_type=None, incident_id=None, cert_id=None, norm_profiles=None):
        """RFC §4.1, §6.1 — sends typed CLAIM_ANCHOR to own Keeper for self-anchoring of all protocol actions; schema: schemas/claim_anchor.json"""
        self._anchor_seq += 1
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = {"action_type": action_type, "incident_id": incident_id, "seq": self._anchor_seq}
        data_hash = hash_claim(payload)
        claim_id = str(uuid.uuid4())
        anchor = {
            "type": "CLAIM_ANCHOR",
            "terminal_id": self.terminal_id,
            "claim_id": claim_id,
            "sequence_number": self._anchor_seq,
            "timestamp": now,
            "data_hash": data_hash,
            "signature": f"SIG_{self.terminal_id}_{self._anchor_seq}"
        }
        if action_type:
            anchor["action_type"] = action_type
        if incident_id:
            anchor["incident_id"] = incident_id
        if self._anchor_seq == 1:
            anchor["public_key"] = f"PUBKEY_{self.terminal_id}"
        if cert_id:
            anchor["cert_id"] = cert_id
        if norm_profiles:
            anchor["norm_profiles"] = norm_profiles
        self.world.send(self.name, self._keeper_name, anchor)

    def _handle_withdrawal(self, msg):
        """RFC §6.17 — receives ASSESSMENT_WITHDRAWAL, verifies both signatures, self-anchors WITHDRAWAL_ISSUED, sends INCIDENT_NOTICE(ASSESSMENT_WITHDRAWN); schema: schemas/assessment_withdrawal.json"""
        incident_id  = msg["incident_id"]
        actor_id     = msg["actor_id"]
        claimant_id  = msg["claimant_id"]

        inc = self._incidents.get(incident_id)
        if not inc:
            print(f"[R] withdrawal rejected: incident not found: {incident_id}")
            return

        # In the simulation, signatures are dummy strings — treated as always valid.
        # A production implementation MUST verify both Ed25519 signatures here.
        actor_sig    = msg.get("actor_signature", "")
        claimant_sig = msg.get("claimant_signature", "")
        if not actor_sig or not claimant_sig:
            print(f"[R] withdrawal rejected: both signatures required  incident={incident_id}")
            return

        # Mark the incident as withdrawn so no result can be issued.
        inc["withdrawn"] = True

        reason = msg.get("reason", "")
        print(f"\n[R] === ASSESSMENT_WITHDRAWAL accepted: {incident_id} ===")
        if reason:
            print(f"[R]   reason: {reason}")
        print(f"[R]   actor={actor_id}  claimant={claimant_id}")
        print(f"[R]   MUST NOT issue CONTRIBUTION_RESULT. Notifying Keeper.")

        # Self-anchor withdrawal to own Keeper (§4.1)
        self._send_action_anchor("WITHDRAWAL_ISSUED", incident_id)

        # Send INCIDENT_NOTICE(ASSESSMENT_WITHDRAWN) to each party's Keeper that holds
        # escrow (Ka, Kc), learned from the filing handshake (§4.4, §6.17).
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        keeper_names = set(inc.get("keeper_map", {}).values()) or {self._keeper_name}
        for keeper_name in keeper_names:
            notice = {
                "type": "INCIDENT_NOTICE",
                "incident_id": incident_id,
                "referee_id": self.terminal_id,        # G1: signed, verified against the bound Referee
                "recipient_id": self.world.agents[keeper_name].terminal_id,
                "event_type": "ASSESSMENT_WITHDRAWN",
                # The Keeper deducts the Referee's declared cancellation fee (RFC §6.17);
                # carried here so a party Keeper need not hold the Referee's profile.
                "cancellation_fee": self._fee_profile.get("cancellation_fee", 0),
                "timestamp": now,
                "signature": f"SIG_{self.terminal_id}"
            }
            self.world.send(self.name, keeper_name, notice)

    def _handle_anchor_chain_result(self, msg):
        """RFC §6.28 — consumes ANCHOR_CHAIN_RESULT for evidence sufficiency (RFC §6.14) and
        POH_CERTIFICATE (RFC §8). Within-window completeness is verified locally from
        sequence contiguity; the governing session_start (§9.3) is self-authenticating
        (party-signed) and read alongside any in-window SESSION_START anchors."""
        terminal_id = msg["target_terminal_id"]
        incident_id = msg["incident_id"]
        count = msg["count"]
        anchors = msg["anchors"]

        sorted_anchors = sorted(anchors, key=lambda a: a["sequence_number"])
        has_gap = any(
            sorted_anchors[i]["sequence_number"] != sorted_anchors[i - 1]["sequence_number"] + 1
            for i in range(1, len(sorted_anchors))
        ) if len(sorted_anchors) > 1 else False

        inc = self._incidents.setdefault(incident_id, {})
        inc.setdefault("anchor_coverage", {})[terminal_id] = {
            "count": count,
            "has_gap": has_gap
        }

        # Norm retrieval (§9.3): the governing SESSION_START rides the result; in-window
        # SESSION_STARTs (the sim's wide-window norm) appear in anchors. Read both.
        declared = list(anchors)
        if msg.get("session_start"):
            declared.append(msg["session_start"])
        for anchor in declared:
            if anchor.get("action_type") == "SESSION_START":
                profiles = anchor.get("norm_profiles", [])
                if profiles:
                    ids = [p["norm_profile_id"] for p in profiles]
                    inc.setdefault("declared_norms", {})[terminal_id] = ids

        if count == 0:
            print(f"[R] anchor chain: {terminal_id}  no anchors found")
        else:
            print(f"[R] anchor chain: {terminal_id}  {count} anchor(s) on record"
                  f"  gap={has_gap}")
            for a in anchors:
                print(f"       {a['claim_id']}  hash={a['data_hash'][:8]}..."
                      f"  seq={a['sequence_number']}")

    def _evaluate_evidence_sufficiency(self, incident_id, actor_id, claimant_id):
        """RFC §6.14 — evaluates evidence_sufficiency (assessment_status, coverage level, gaps) from anchor coverage data"""
        coverage_data = self._incidents.get(incident_id, {}).get("anchor_coverage", {})
        gaps = []

        def coverage_level(party_id):
            if party_id not in coverage_data:
                return "UNKNOWN"
            data = coverage_data[party_id]
            if data["count"] == 0:
                return "NONE"
            if data["has_gap"]:
                gaps.append({"party_id": party_id,
                             "description": "sequence gap detected in anchor chain"})
                return "LOW"
            if data["count"] >= 5:
                return "HIGH"
            if data["count"] >= 2:
                return "MEDIUM"
            return "LOW"

        actor_cov    = coverage_level(actor_id)
        claimant_cov = coverage_level(claimant_id)

        is_provisional = any(c in ("NONE", "LOW", "UNKNOWN")
                             for c in [actor_cov, claimant_cov])
        return {
            "assessment_status":     "PROVISIONAL" if is_provisional else "DEFINITIVE",
            "actor_coverage":     actor_cov,
            "claimant_coverage":  claimant_cov,
            "gaps":               gaps
        }
