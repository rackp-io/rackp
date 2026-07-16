import uuid

class Agent:
    def __init__(self, name):
        self.name = name
        self.terminal_id = str(uuid.uuid4())
        self.world = None

    def on_message(self, message):
        pass

    def receive(self, message):
        """Validate incoming message against schema, then dispatch to on_message."""
        from classes.World import _validate
        _validate(message)
        self.on_message(message)
