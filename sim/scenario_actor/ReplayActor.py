# scenario_actor/ReplayActor.py
from classes.Actor import Actor

class ReplayActor(Actor):
    """
    Actor that conceals its actual incident action by REPLAYING an older, genuinely
    anchored action as its evidence.

    The replayed anchor is real — it exists in the Keeper with a valid hash, so it is
    NOT a forgery (that is the LiarActor's trick). Its only flaw is its timestamp: it
    falls outside the incident's evidence window. The submission is therefore built in
    exactly the honest form (Claim.to_dict() + the stored hash); the sole difference
    from an honest submission is WHICH claim is sent. Keeper verification finds the hash
    but rejects it as TIMESTAMP_OUT_OF_RANGE rather than crediting the stale record.
    """

    def __init__(self, name, keeper_name="K"):
        super().__init__(name, keeper_name=keeper_name)
        self._replay_claim = None

    def remember_as_old(self):
        """Mark the latest anchored action as the stale anchor to replay later."""
        self._replay_claim = self._last_claim

    def _submit_evidence(self, query):
        """Replay the remembered OLD anchor in place of the real incident action.
        Delegates to the honest submission builder with _last_claim temporarily swapped,
        so the replayed evidence is byte-for-byte honest in form — only the (stale)
        anchor differs, which is precisely what the Keeper's window check rejects."""
        if not self._replay_claim:
            return
        real_claim, self._last_claim = self._last_claim, self._replay_claim
        try:
            print(f"[{self.name}] (replay) submitting stale anchor {self._replay_claim.claim_id}"
                  f"  ts={self._replay_claim.timestamp}  (outside the incident window)")
            super()._submit_evidence(query)
        finally:
            self._last_claim = real_claim
