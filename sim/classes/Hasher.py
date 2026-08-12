import hashlib
import json

def hash_norm_document(profile_id):
    """SHA-256 of the JCS canonical form of a Norm Profile document (RFC-0001 §8.4).

    Resolves the profile_id to the document published in this repository's norms/
    directory (rackp.standard.v1 -> norms/rackp-standard-v1.json) and hashes the
    parsed-and-recanonicalized JSON rather than the retrieved bytes, so line endings,
    indentation and key order cannot change the value. Profiles a scenario invents
    have no document to read; those fall back to a deterministic stand-in so the
    flow still exercises the field.
    """
    import os
    root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
    path = os.path.join(root, 'norms', profile_id.replace('.', '-') + '.json')
    if not os.path.exists(path):
        return hashlib.sha256(f"absent:{profile_id}".encode()).hexdigest()
    with open(path, encoding='utf-8-sig') as f:
        return hash_claim(json.load(f))


def hash_claim(claim_dict):
    """SHA-256 hash of a claim dict (RFC 8785 JCS simplified: sort_keys=True).
    Used by World to compute data_hash for CLAIM_ANCHOR, and by Referee to
    independently verify EVIDENCE_SUBMISSION payload integrity."""
    data = json.dumps(claim_dict, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()
