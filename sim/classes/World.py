# classes/World.py
import json
import os
import uuid
from classes.Hasher import hash_claim

_SCHEMA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'schemas')
)
_schema_cache: dict = {}

def _load_schema(type_name: str):
    path = os.path.join(_SCHEMA_DIR, type_name.lower() + '.json')
    if not os.path.exists(path):
        return None
    if path not in _schema_cache:
        with open(path, encoding='utf-8-sig') as f:
            _schema_cache[path] = json.load(f)
    return _schema_cache[path]

_store: dict = {}  # URI → schema dict, built once

def _build_store() -> dict:
    """Pre-load all local schemas into a URI→dict store for $ref resolution."""
    if _store:
        return _store
    for fname in os.listdir(_SCHEMA_DIR):
        if not fname.endswith('.json'):
            continue
        path = os.path.join(_SCHEMA_DIR, fname)
        with open(path, encoding='utf-8-sig') as f:
            s = json.load(f)
        if '$id' in s:
            _store[s['$id']] = s
    return _store

def _validate(msg: dict) -> None:
    try:
        import jsonschema
    except ImportError:
        return  # jsonschema not installed — skip silently

    type_name = msg.get('type')
    if not type_name:
        return
    schema = _load_schema(type_name)
    if schema is None:
        return  # no schema file for this type — skip silently

    store = _build_store()
    resolver = jsonschema.RefResolver(
        base_uri=schema.get('$id', ''),
        referrer=schema,
        store=store,
    )
    # Strip internal routing key before validating
    clean = {k: v for k, v in msg.items() if k != '_sender'}
    try:
        jsonschema.validate(instance=clean, schema=schema, resolver=resolver)
    except jsonschema.ValidationError as e:
        print(f"[World] SCHEMA ERROR ({type_name}): {e.message}")
        print(f"         path: {' -> '.join(str(p) for p in e.absolute_path)}")
        raise


class World:
    def __init__(self, validate: bool = True):
        self.agents = {}
        self._tid_to_name = {}
        self.claim_log = []           # global append-only log (diagnostics only)
        self._chains = {}             # terminal_id -> [Claim]; each terminal's own anchor chain
        self.message_log = []         # [(sender, receiver, msg)] — TEST OBSERVATION ONLY.
        self.validate = validate

    def register(self, agent):
        self.agents[agent.name] = agent
        self._tid_to_name[agent.terminal_id] = agent.name
        agent.world = self

    def route_by_tid(self, terminal_id):
        """Resolve a terminal_id (UUID) to the routing name used in self.agents."""
        return self._tid_to_name.get(terminal_id, terminal_id)

    def record_claim(self, claim, keeper_name="K"):
        # Each terminal owns an independent anchor chain: sequence_number is per-terminal,
        # monotonic from 1, and prev_hash links to that terminal's previous anchor
        # (RFC-0002 §2.2, §2.6). A global counter would make legitimately interleaved
        # chains look gapped, and would deny every terminal but the first a
        # sequence_number == 1 (and thus its public-key registration).
        chain = self._chains.setdefault(claim.terminal_id, [])
        claim.seq = len(chain) + 1
        claim.prev_hash = chain[-1].hash if chain else None
        claim.hash = hash_claim(claim.to_dict())
        claim.claim_id = str(uuid.uuid4())
        chain.append(claim)
        self.claim_log.append(claim)

        print(f"[World] claim recorded: {claim.terminal_id[:8]}... SEQ{claim.seq:04d}  hash={claim.hash[:8]}...")
        if keeper_name in self.agents:
            self.send(claim.terminal_id, keeper_name, claim.to_anchor_msg())

    def send(self, sender, receiver, schema_dict):
        """Deliver a schema-compliant dict, attaching _sender before routing."""
        if self.validate:
            _validate(schema_dict)
        # Record every delivery for test observation. This lives in the harness — NOT
        # in the agent classes — so scenarios can assert on what a party received
        # without implying the protocol requires any party to retain these messages.
        self.message_log.append((sender, receiver, schema_dict))
        msg = {**schema_dict, "_sender": sender}
        print(f"[World] {sender} -> {receiver}: {msg['type']}")
        if receiver in self.agents:
            self.agents[receiver].receive(msg)

    def last(self, receiver, msg_type):
        """TEST helper — the most recent message of msg_type delivered to receiver (by name)."""
        for sender, r, m in reversed(self.message_log):
            if r == receiver and m.get("type") == msg_type:
                return m
        return None

    def all_of(self, receiver, msg_type):
        """TEST helper — every message of msg_type delivered to receiver, in order."""
        return [m for (sender, r, m) in self.message_log if r == receiver and m.get("type") == msg_type]

