# scenario_actor/AppealActor.py
from scenario_actor.LiarActor import LiarActor
from datetime import datetime, timezone

class AppealActor(LiarActor):
    """
    Actor that submits falsified evidence on the initial assessment (resulting in FAILED),
    then files an appeal.
    - use_real_evidence=True  : appeal with genuine evidence → accepted, assessment revised
    - use_real_evidence=False : appeal with non-existent evidence → rejected
    """

    def file_appeal(self, use_real_evidence=True):
        if not self._last_assessment_cert_id:
            print(f"[{self.name}] no assessment to appeal")
            return

        incident_id = self._last_assessment_incident
        c = self._last_claim

        if use_real_evidence:
            evidence_hash = c.hash   # genuine hash stored in Keeper
            label = "real"
        else:
            evidence_hash = "f" * 64  # fake hash not present in Keeper
            label = "fake"

        print(f"[{self.name}] filing appeal ({label} evidence)"
              f"  target_assessment={self._last_assessment_cert_id}")

        appeal = {
            "type": "ASSESSMENT_APPEAL",
            "incident_id": incident_id,
            "submitter_id": self.terminal_id,
            "target_assessment_id": self._last_assessment_cert_id,
            "appeal_grounds": {
                "category": "FACTUAL_ERROR",
                "description": (
                    "Initial submission contained an error. "
                    "Providing correct evidence anchor."
                )
            },
            "additional_evidence": {
                "payload": {"raw_data": c.raw_data()},
                "verification_info": {
                    "claim_id":       c.claim_id,
                    "stored_hash":    evidence_hash,
                    "keeper_endpoint": f"sim://{self._keeper_name}"
                }
            },
            "signature": f"SIG_{self.name}_APPEAL",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        self.world.send(self.name, "R", appeal)

    def file_appeal_disputing_split(self):
        """Re-appeal that DISPUTES the fault allocation but attaches NO new evidence —
        the genuine record was already submitted and assessed. This models the honest-
        but-futile re-litigation pattern (an Actor that does not lie, yet keeps pressing
        for a better split with nothing new). With no additional_evidence to verify, the
        Referee finds nothing new and rejects it, so the standing verdict is unmoved.
        Contrast file_appeal(), which attaches an evidence anchor for the Referee to
        verify and can therefore actually move the verdict."""
        if not self._last_assessment_cert_id:
            print(f"[{self.name}] no assessment to appeal")
            return
        print(f"[{self.name}] filing re-appeal disputing the split (no new evidence)"
              f"  target_assessment={self._last_assessment_cert_id}")
        appeal = {
            "type": "ASSESSMENT_APPEAL",
            "incident_id": self._last_assessment_incident,
            "submitter_id": self.terminal_id,
            "target_assessment_id": self._last_assessment_cert_id,
            "appeal_grounds": {
                "category": "LOGIC_ERROR",
                "description": (
                    "Disputes the fault allocation. No new evidence is provided beyond "
                    "what was already submitted and assessed."
                )
            },
            # No additional_evidence: nothing new for the Referee to verify.
            "signature": f"SIG_{self.name}_APPEAL",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        self.world.send(self.name, "R", appeal)
