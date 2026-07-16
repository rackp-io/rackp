# classes/Actor.py
from classes.Claim import Claim
from classes.Agent import Agent
from datetime import datetime, timezone

class Actor(Agent):
    def __init__(self, name, keeper_name="K"):
        super().__init__(name)
        self._last_claim = None
        self._last_assessment_cert_id  = None
        self._last_assessment_incident = None
        self._external_factor_claim = None
        self._keeper_name = keeper_name
        self._norm_profile_ids = []
        self._pending_queries = {}        # incident_id → EVIDENCE_QUERY_REQUEST msg
        self._pending_notifications = {}  # incident_id → ACTOR_NOTIFICATION msg

    def session_start(self, norm_profiles):
        """RFC §4.2, §9.3 — CLAIM_ANCHOR(SESSION_START) to declare supported Norm Profiles; schema: schemas/claim_anchor.json"""
        self._norm_profile_ids = [p["norm_profile_id"] for p in norm_profiles]
        claim = Claim(
            terminal_id=self.terminal_id,
            action="SESSION_START",
            detail={"norm_profiles": norm_profiles},
            action_type="SESSION_START",
            anchor_extra={"norm_profiles": norm_profiles}
        )
        self.world.record_claim(claim, keeper_name=self._keeper_name)

    def deposit_fee(self, incident_id, amount, currency="USD"):
        """RFC §5 Phase 2, §6.4 — FEE_DEPOSIT to Keeper; signed per STD-033 so the Keeper
        can verify depositor_id before crediting escrow; schema: schemas/fee_deposit.json"""
        msg = {
            "type": "FEE_DEPOSIT",
            "incident_id": incident_id,
            "depositor_id": self.terminal_id,
            "amount": amount,
            "currency": currency,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "signature": f"SIG_{self.terminal_id}"
        }
        self.world.send(self.name, self._keeper_name, msg)

    def claim_refund(self, incident_id):
        """STD-028 — FEE_REFUND_CLAIM to the Keeper after the assessment deadline elapses
        with no ASSESSMENT_COMPLETE; reclaims the full deposit. The right belongs to any
        depositing party, so the Actor reclaims its own deposit independently of the
        Claimant; schema: schemas/fee_refund_claim.json"""
        msg = {
            "type": "FEE_REFUND_CLAIM",
            "incident_id": incident_id,
            "depositor_id": self.terminal_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "signature": f"SIG_{self.terminal_id}"
        }
        self.world.send(self.name, self._keeper_name, msg)

    def act(self, action, detail=None, timestamp=None, external_factor_claim=None):
        """RFC §4.2 — CLAIM_ANCHOR during normal operation; schema: schemas/claim_anchor.json"""
        claim = Claim(terminal_id=self.terminal_id, action=action, detail=detail, timestamp=timestamp)
        self.world.record_claim(claim, keeper_name=self._keeper_name)
        self._last_claim = claim  # sim simplification: holds only the latest claim; real impl maintains full log
        self._external_factor_claim = external_factor_claim

    def reject_evidence(self, incident_id, reason=""):
        """RFC §6.11 — sends EVIDENCE_REJECTION to Referee in lieu of EVIDENCE_SUBMISSION; schema: schemas/evidence_rejection.json"""
        query = self._pending_queries.get(incident_id)
        if not query:
            return
        msg = {
            "type": "EVIDENCE_REJECTION",
            "incident_id": incident_id,
            "submitter_id": self.terminal_id,
            "signature": f"SIG_{self.terminal_id}_REJECT",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        if reason:
            msg["reason"] = reason
        self.world.send(self.name, query["_sender"], msg)

    def submit_evidence(self, incident_id):
        """RFC §5 Phase 3 — triggers EVIDENCE_SUBMISSION for a queued EVIDENCE_QUERY_REQUEST"""
        query = self._pending_queries.get(incident_id)
        if query:
            self._submit_evidence(query)

    def acknowledge(self, incident_id):
        """RFC §6.8 — sends ACTOR_ACKNOWLEDGMENT for a queued ACTOR_NOTIFICATION; schema: schemas/actor_acknowledgment.json"""
        query = self._pending_notifications.get(incident_id)
        if query:
            self._handle_actor_notification(query)

    def on_message(self, msg):
        """Dispatch handler for all inbound message types"""
        if msg["type"] == "ACTOR_NOTIFICATION":
            self._pending_notifications[msg["incident_id"]] = msg
        elif msg["type"] == "EVIDENCE_QUERY_REQUEST":
            self._pending_queries[msg["incident_id"]] = msg
        elif msg["type"] == "CONTRIBUTION_RESULT":
            self._handle_result(msg)
        elif msg["type"] == "APPEAL_REJECTED":
            self._handle_appeal_rejected(msg)

    def _handle_actor_notification(self, msg):
        """RFC §6.7, §6.8 — receives ACTOR_NOTIFICATION, replies with ACTOR_ACKNOWLEDGMENT; schema: schemas/actor_notification.json, schemas/actor_acknowledgment.json"""
        incident_id = msg["incident_id"]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"[{self.name}] ACTOR_NOTIFICATION received: incident={incident_id}")
        ack = {
            "type": "ACTOR_ACKNOWLEDGMENT",
            "incident_id": incident_id,
            "actor_id": self.terminal_id,
            "actor_keeper_endpoint": f"sim://{self._keeper_name}",
            "timestamp": now,
            "signature": f"SIG_{self.terminal_id}"
        }
        if self._norm_profile_ids:
            ack["norm_profile_ids"] = self._norm_profile_ids
        self.world.send(self.name, msg["_sender"], ack)

    def _handle_result(self, msg):
        """RFC §6.14 — receives CONTRIBUTION_RESULT; schema: schemas/contribution_result.json"""
        v    = msg["assessment"]
        ca   = v["fault"]
        cert = v["certification"]
        self._last_assessment_cert_id  = cert["cert_id"]
        self._last_assessment_incident = msg["incident_id"]
        print(f"[{self.name}] CONTRIBUTION_RESULT received:")
        print(f"[{self.name}]   {v['factual_findings']}")
        print(f"[{self.name}]   actor_fault={ca['actor_fault']}"
              f"  claimant_fault={ca['claimant_fault']}")
        print(f"[{self.name}]   cert_url={cert['cert_url']}")

    def _handle_appeal_rejected(self, msg):
        """RFC §6.16 — receives APPEAL_REJECTED from Referee"""
        print(f"[{self.name}] APPEAL_REJECTED: {msg['incident_id']}"
              f"  reason={msg['reason']}")

    def _submit_evidence(self, query):
        """RFC §6.10 — builds and sends EVIDENCE_SUBMISSION; schema: schemas/evidence_submission.json"""
        if not self._last_claim:
            return
        c = self._last_claim
        submission = {
            "type": "EVIDENCE_SUBMISSION",
            "incident_id": query["incident_id"],
            "submitter_id": self.terminal_id,
            "payload": {
                "raw_data": c.to_dict(),
                "metadata": {
                    "terminal_id": self.terminal_id,
                    "firmware_version": "sim-v1.0"
                }
            },
            "statement": {
                "summary": f"{self.name} performed action '{c.action}'.",
                "raw_log_reference": c.claim_id
            },
            "verification_info": {
                "keeper_endpoint": f"sim://{self._keeper_name}",
                "claim_id": c.claim_id,
                "sequence_number": c.seq,
                "stored_hash": c.hash
            },
            "signature": f"SIG_{self.terminal_id}_{c.seq}",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        if self._external_factor_claim is not None:
            submission["external_factor_claim"] = self._external_factor_claim
        self.world.send(self.name, query["_sender"], submission)
