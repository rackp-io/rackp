import time

class ActionLog:
    """Sim-only timestamped action record (Unix epoch). Not part of the RACKP
    message flow; available for local logging or future diagnostic extensions."""

    def __init__(self, actor, action, detail=None):
        self.actor = actor
        self.action = action
        self.detail = detail
        self.timestamp = time.time()

    def to_dict(self):
        return {
            "actor": self.actor,
            "action": self.action,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }