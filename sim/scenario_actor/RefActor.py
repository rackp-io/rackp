# scenario_actor/RefActor.py
# A Referee that can also be named as Actor and assessed by another Referee.
# Overrides _send_action_anchor to capture anchor info for later evidence submission.
# §4.1: Referee actions are anchored to Keeper and can be reviewed by
# another Referee if the Referee itself becomes a subject of assessment.
import uuid as _uuid
from datetime import datetime, timezone
from classes.Referee import Referee
from classes.Hasher import hash_claim


class RefActor(Referee):
    def __init__(self, name, keeper_name="K"):
        super().__init__(name, keeper_name=keeper_name)
        self._last_anchor_info = None  # (payload, data_hash, claim_id, seq)

    def _send_action_anchor(self, action_type, incident_id=None, cert_id=None):
        self._anchor_seq += 1
        now      = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload  = {"action_type": action_type, "incident_id": incident_id, "seq": self._anchor_seq}
        data_hash = hash_claim(payload)
        claim_id  = str(_uuid.uuid4())
        anchor = {
            "type":            "CLAIM_ANCHOR",
            "terminal_id":     self.terminal_id,
            "claim_id":        claim_id,
            "sequence_number": self._anchor_seq,
            "timestamp":       now,
            "data_hash":       data_hash,
            "action_type":     action_type,
            "incident_id":     incident_id,
            "signature":       f"SIG_{self.terminal_id}_{self._anchor_seq}"
        }
        if self._anchor_seq == 1:
            anchor["public_key"] = f"PUBKEY_{self.terminal_id}"
        if cert_id:
            anchor["cert_id"] = cert_id
        self._last_anchor_info = (payload, data_hash, claim_id, self._anchor_seq)
        self.world.send(self.name, self._keeper_name, anchor)

    def on_message(self, msg):
        if msg["type"] == "EVIDENCE_QUERY_REQUEST":
            self._submit_as_actor(msg)
        elif msg["type"] == "CONTRIBUTION_RESULT":
            self._handle_result_as_actor(msg)
        else:
            super().on_message(msg)

    def _submit_as_actor(self, query):
        """Submit last action anchor as evidence when R is being assessed."""
        if not self._last_anchor_info:
            print(f"[{self.name}] (RefActor) no action anchor to submit")
            return
        payload, data_hash, claim_id, seq = self._last_anchor_info
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        submission = {
            "type":         "EVIDENCE_SUBMISSION",
            "incident_id":  query["incident_id"],
            "submitter_id": self.terminal_id,
            "payload": {
                "raw_data": payload,
                "metadata": {"terminal_id": self.terminal_id, "firmware_version": "sim-v1.0"}
            },
            "statement": {
                "summary":           f"{self.name} referee action '{payload['action_type']}'.",
                "raw_log_reference": claim_id
            },
            "verification_info": {
                "keeper_endpoint": f"sim://{self._keeper_name}",
                "claim_id":        claim_id,
                "sequence_number": seq,
                "stored_hash":     data_hash
            },
            "signature": f"SIG_{self.terminal_id}_{seq}",
            "timestamp": now
        }
        self.world.send(self.name, query["_sender"], submission)

    def _handle_result_as_actor(self, msg):
        v    = msg["assessment"]
        ca   = v["fault"]
        cert = v["certification"]
        print(f"[{self.name}] (as Actor) CONTRIBUTION_RESULT received:")
        print(f"[{self.name}]   {v['factual_findings']}")
        print(f"[{self.name}]   actor_fault={ca['actor_fault']}"
              f"  claimant_fault={ca['claimant_fault']}")
        print(f"[{self.name}]   cert_url={cert['cert_url']}")
