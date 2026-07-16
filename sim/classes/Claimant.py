# classes/Claimant.py
from classes.Claim import Claim
from classes.Agent import Agent
from datetime import datetime, timezone

class Claimant(Agent):
    def __init__(self, name, keeper_name="K"):
        super().__init__(name)
        self._last_claim = None
        self._last_assessment_cert_id  = None
        self._last_assessment_incident = None
        self._external_factor_claim = None
        self._keeper_name = keeper_name
        self._norm_profile_ids = []
        self._pending_queries = {}      # incident_id → EVIDENCE_QUERY_REQUEST msg

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
        with no ASSESSMENT_COMPLETE; reclaims the full deposit; schema: schemas/fee_refund_claim.json"""
        msg = {
            "type": "FEE_REFUND_CLAIM",
            "incident_id": incident_id,
            "depositor_id": self.terminal_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "signature": f"SIG_{self.terminal_id}"
        }
        self.world.send(self.name, self._keeper_name, msg)

    def withdraw_assessment(self, incident_id, actor_name, reason="", referee_name="R"):
        """RFC §6.17 — co-signed ASSESSMENT_WITHDRAWAL: the Claimant and the named Actor
        jointly withdraw the incident before assessment, sent to the Referee. The sim
        emits both placeholder signatures to model that both parties have agreed;
        schema: schemas/assessment_withdrawal.json"""
        actor_tid = self.world.agents[actor_name].terminal_id
        msg = {
            "type": "ASSESSMENT_WITHDRAWAL",
            "incident_id": incident_id,
            "actor_id": actor_tid,
            "claimant_id": self.terminal_id,
            "actor_signature": f"SIG_{actor_tid}_withdrawal",
            "claimant_signature": f"SIG_{self.terminal_id}_withdrawal",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if reason:
            msg["reason"] = reason
        self.world.send(self.name, referee_name, msg)

    def session_start(self, norm_profiles):
        """RFC §4.3, §9.3 — CLAIM_ANCHOR(SESSION_START) to declare supported Norm Profiles; schema: schemas/claim_anchor.json"""
        self._norm_profile_ids = [p["norm_profile_id"] for p in norm_profiles]
        claim = Claim(
            terminal_id=self.terminal_id,
            action="SESSION_START",
            detail={"norm_profiles": norm_profiles},
            action_type="SESSION_START",
            anchor_extra={"norm_profiles": norm_profiles}
        )
        self.world.record_claim(claim, keeper_name=self._keeper_name)

    def send_assessment_request(self, actor_name, incident_id, incident_summary="Incident reported by Claimant.", referee_name="R"):
        """RFC §5 Phase 2, §6.2 — ASSESSMENT_REQUEST to Referee; schema: schemas/assessment_request.json"""
        actor_tid = self.world.agents[actor_name].terminal_id if actor_name else None
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        msg = {
            "type": "ASSESSMENT_REQUEST",
            "incident_id": incident_id,
            "claimant_id": self.terminal_id,
            "keeper_endpoint": f"sim://{self._keeper_name}",
            "incident_summary": incident_summary,
            "incident_timestamp": now,
            "norm_profile_ids": self._norm_profile_ids or ["rackp.standard.v1"],
            "timestamp": now,
            "signature": f"SIG_{self.terminal_id}"
        }
        # actor_id is OMITTED (not null) for a Claimant-only assessment — e.g. the PoHI
        # flow (RFC §8 / assessment_request.json: "Omit for Claimant-only assessments").
        if actor_tid:
            msg["actor_id"] = actor_tid
        self.world.send(self.name, referee_name, msg)

    def act(self, action, detail=None, external_factor_claim=None):
        """RFC §4.3 — CLAIM_ANCHOR during normal operation; schema: schemas/claim_anchor.json"""
        claim = Claim(terminal_id=self.terminal_id, action=action, detail=detail)
        self.world.record_claim(claim, keeper_name=self._keeper_name)
        self._last_claim = claim  # sim simplification: holds only the latest claim; real impl maintains full log
        self._external_factor_claim = external_factor_claim

    def discover_referees(self, keeper_name="K", filters=None):
        """RFC §6.18, §6.19 — sends REFEREE_DISCOVERY_REQUEST to Keeper; schema: schemas/referee_discovery_request.json"""
        msg = {
            "type": "REFEREE_DISCOVERY_REQUEST",
            "requester_id": self.terminal_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        if filters:
            msg["filters"] = filters
        self.world.send(self.name, keeper_name, msg)

    def query_referee_stats(self, referee_name, keeper_name="K"):
        """RFC §6.20 — sends REFEREE_STATS_QUERY to Keeper; schema: schemas/referee_stats_query.json"""
        msg = {
            "type": "REFEREE_STATS_QUERY",
            "terminal_id": self.world.agents[referee_name].terminal_id,
            "requester_id": self.terminal_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        self.world.send(self.name, keeper_name, msg)

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

    def submit_evidence(self, incident_id, pohi=None):
        """RFC §5 Phase 3 — triggers EVIDENCE_SUBMISSION for a queued EVIDENCE_QUERY_REQUEST.
        For a PoHI request (RFC §8) pass `pohi` = {subject_data_hash, anchor_range, content_id};
        it rides in the submission payload (no dedicated message/schema — §8 reuses the generic flow)."""
        query = self._pending_queries.get(incident_id)
        if query:
            self._submit_evidence(query, pohi=pohi)

    def on_message(self, msg):
        """Dispatch handler for all inbound message types"""
        if msg["type"] == "EVIDENCE_QUERY_REQUEST":
            self._pending_queries[msg["incident_id"]] = msg
        elif msg["type"] == "CONTRIBUTION_RESULT":
            self._handle_result(msg)
        elif msg["type"] == "APPEAL_REJECTED":
            self._handle_appeal_rejected(msg)
        elif msg["type"] == "POH_CERTIFICATE":
            self._handle_phi_cert(msg)
        elif msg["type"] == "REFEREE_DISCOVERY_RESULT":
            self._handle_discovery_result(msg)
        elif msg["type"] == "REFEREE_STATS_RESULT":
            self._handle_referee_stats_result(msg)
        elif msg["type"] == "FEE_REFUND_RESULT":
            self._handle_fee_refund_result(msg)

    def _handle_fee_refund_result(self, msg):
        """STD-028 — receives FEE_REFUND_RESULT from the Keeper; schema: schemas/fee_refund_result.json"""
        if msg["status"] == "ACCEPTED":
            print(f"[{self.name}] FEE_REFUND_RESULT ACCEPTED: incident={msg['incident_id']}"
                  f"  refunded_amount={msg.get('refunded_amount')} {msg['currency']}")
        else:
            print(f"[{self.name}] FEE_REFUND_RESULT REJECTED: incident={msg['incident_id']}"
                  f"  reason={msg.get('rejection_reason')}")

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

    def _handle_phi_cert(self, msg):
        """RFC §8 — receives POH_CERTIFICATE from Referee; schema: schemas/poh_certificate.json"""
        p = msg["provenance"]
        print(f"[{self.name}] POH_CERTIFICATE received:")
        print(f"[{self.name}]   cert_id={msg['cert_id']}")
        print(f"[{self.name}]   human_ratio={p['human_ratio']}  ai_ratio={p['ai_ratio']}"
              f"  confidence={p['confidence_level']}")
        print(f"[{self.name}]   cert_url={msg['cert_url']}")

    def _handle_discovery_result(self, msg):
        """RFC §6.18, §6.19 — receives REFEREE_DISCOVERY_RESULT from Keeper"""
        profiles = msg.get("profiles", [])
        print(f"[{self.name}] REFEREE_DISCOVERY_RESULT: {msg['count']} referee(s) found")
        for p in profiles:
            fee = p["fee"]
            norms = ", ".join(sp["norm_profile_id"] for sp in p["conduct_norms"])
            print(f"[{self.name}]   referee_id={p['referee_id'][:8]}..."
                  f"  status={p['availability_status']}  network={p['network']}"
                  f"  fee={fee['amount']} {fee['currency']}  norms=[{norms}]")

    def _handle_referee_stats_result(self, msg):
        """RFC §6.21 — receives REFEREE_STATS_RESULT from Keeper; schema: schemas/referee_stats_result.json"""
        tid = msg["terminal_id"]
        if not msg.get("found"):
            print(f"[{self.name}] REFEREE_STATS_RESULT: no record for {tid[:8]}...")
            return
        print(f"[{self.name}] REFEREE_STATS_RESULT: referee={tid[:8]}...")
        print(f"[{self.name}]   assessment_count={msg['assessment_count']}"
              f"  appeal_rate={msg['appeal_rate']}"
              f"  anchor_continuity={msg['anchor_continuity']}")

    def _submit_evidence(self, query, pohi=None):
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
        # PoHI artifact binding (RFC §8): subject_data_hash + anchor_range travel in the
        # payload (additionalProperties), so the canonical EVIDENCE_SUBMISSION carries them
        # without a PoHI-specific message or schema.
        if pohi is not None:
            submission["payload"]["pohi"] = pohi
        self.world.send(self.name, query["_sender"], submission)
