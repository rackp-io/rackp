import hashlib
import json

def hash_claim(claim_dict):
    """SHA-256 hash of a claim dict (RFC 8785 JCS simplified: sort_keys=True).
    Used by World to compute data_hash for CLAIM_ANCHOR, and by Referee to
    independently verify EVIDENCE_SUBMISSION payload integrity."""
    data = json.dumps(claim_dict, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()
