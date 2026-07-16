# scenario_actor/LiarActor.py
from classes.Actor import Actor
from classes.Hasher import hash_claim
from datetime import datetime, timezone

class LiarActor(Actor):
    """
    Actor that submits a falsified hash as evidence.
    Verification against the correct hash stored in the Keeper results in FAILED.
    """

    def _submit_evidence(self, query):
        if not self._last_claim:
            return
        c = self._last_claim

        # generate hash from falsified data (different from actual action)
        falsified_data = {
            "terminal_id": self.terminal_id,
            "action": c.action,
            "detail": {},       # actual detail concealed
            "seq": c.seq,
            "prev_hash": c.prev_hash,
        }
        fake_hash = hash_claim(falsified_data)

        submission = {
            "type": "EVIDENCE_SUBMISSION",
            "incident_id": query["incident_id"],
            "submitter_id": self.terminal_id,
            "payload": {
                "raw_data": falsified_data,  # actual detail concealed — Referee will detect hash mismatch
                "metadata": {
                    "terminal_id": self.terminal_id,
                    "firmware_version": "sim-v1.0"
                }
            },
            "statement": {
                "summary": f"{self.name} performed action '{c.action}' (falsified).",
                "raw_log_reference": c.claim_id
            },
            "verification_info": {
                "keeper_endpoint": f"sim://{self._keeper_name}",
                "claim_id": c.claim_id,
                "sequence_number": c.seq,
                "stored_hash": fake_hash   # falsified hash
            },
            "signature": f"SIG_{self.terminal_id}_{c.seq}",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        print(f"[{self.name}] (liar) submitting falsified hash: {fake_hash[:8]}..."
              f"  (real: {c.hash[:8]}...)")
        self.world.send(self.name, query["_sender"], submission)
