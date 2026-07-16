# scenario_actor/SelectiveClaimant.py
from classes.Claimant import Claimant

class SelectiveClaimant(Claimant):
    """
    Claimant that files an assessment and pays its fee like any honest party, but
    then refuses to submit its own evidence (ignores EVIDENCE_QUERY_REQUEST),
    hoping to withhold an unfavorable record. Its anchors still exist in its Keeper
    and remain visible to the Referee via ANCHOR_CHAIN_QUERY — so selective
    disclosure does not actually hide them.
    """

    def on_message(self, msg):
        if msg["type"] == "EVIDENCE_QUERY_REQUEST":
            print(f"[{self.name}] (selective) ignoring EVIDENCE_QUERY_REQUEST"
                  f" for incident={msg['incident_id']}")
            return  # withhold: never queue the query, so submit_evidence() is a no-op
        super().on_message(msg)
