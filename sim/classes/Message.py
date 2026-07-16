class Message:
    """Sim-internal message envelope used by World.send() for delivery routing.
    Not transmitted on-wire; the payload dict is the actual protocol message."""

    def __init__(self, sender, receiver, payload=None, msg_type="generic"):
        self.sender = sender
        self.receiver = receiver
        self.payload = payload
        self.msg_type = msg_type

    def __repr__(self):
        return f"Message({self.sender} -> {self.receiver}, {self.msg_type}, {self.payload})"