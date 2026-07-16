# classes/Claim.py
from datetime import datetime, timezone

class Claim:
    """RFC §6.1 — in-memory representation of one anchored action.
    World assigns seq/hash/claim_id before the claim is sent to Keeper.
    Serialized to a CLAIM_ANCHOR message via to_anchor_msg(); schema: schemas/claim_anchor.json.
    """

    def __init__(self, terminal_id, action, detail=None, timestamp=None,
                 action_type=None, anchor_extra=None):
        self.terminal_id = terminal_id
        self.action = action
        self.detail = detail or {}
        self.seq = None        # assigned by World
        self.prev_hash = None  # assigned by World
        self.hash = None       # assigned by World
        self.claim_id = None   # assigned by World
        self.timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.action_type = action_type    # optional: e.g. "SESSION_START"
        self.anchor_extra = anchor_extra or {}  # extra fields included in to_anchor_msg()

    def raw_data(self):
        """Raw data payload for evidence submission."""
        return {"action": self.action, "detail": self.detail}

    def to_dict(self):
        """Dict for hash computation, including chain structure."""
        return {
            "terminal_id": self.terminal_id,
            "action": self.action,
            "detail": self.detail,
            "seq": self.seq,
            "prev_hash": self.prev_hash,
        }

    def to_anchor_msg(self):
        """Returns a CLAIM_ANCHOR schema-compliant message."""
        msg = {
            "type": "CLAIM_ANCHOR",
            "terminal_id": self.terminal_id,
            "claim_id": self.claim_id,
            "sequence_number": self.seq,
            "timestamp": self.timestamp,
            "data_hash": self.hash,
            "signature": f"SIG_{self.terminal_id}_{self.seq}"
        }
        if self.seq == 1:
            msg["public_key"] = f"PUBKEY_{self.terminal_id}"
        if self.action_type:
            msg["action_type"] = self.action_type
        msg.update(self.anchor_extra)
        return msg
