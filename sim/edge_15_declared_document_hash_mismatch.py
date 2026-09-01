# edge_15_declared_document_hash_mismatch.py
# RFC §8.4, §9.3 (rackp#18): a PoHI flow in which the Claimant's SESSION_START declares
# a norm_document_hash that does NOT match the Norm document the Referee actually applied
# — e.g. the Claimant fetched an older or tampered copy of the profile. base_07 exercises
# declared_document_hash reaching the certificate when it AGREES with applied_document_hash;
# this scenario is the other half named in rackp#18: "the divergence case described in
# Section 8.4 goes unexercised."
#
# How a divergence is handled (§8.4): the Referee records BOTH hashes side by side and
# draws NO conclusion from the difference — same disclosure-only treatment as
# norm_jurisdiction_mismatch (§9.5, edge_06). It does not invalidate the certificate, does
# not prefer one hash over the other, and does not fold the mismatch into provenance.
from classes.World import World
from classes.Claimant import Claimant
from classes.Referee import Referee
from classes.Keeper import Keeper
from classes.Hasher import hash_claim, hash_norm_document
from datetime import datetime, timezone

def run():
    world = World()
    R  = Referee("R",  keeper_name="Kr")
    C  = Claimant("C", keeper_name="Kc")
    Kr = Keeper("Kr")
    Kc = Keeper("Kc")
    for agent in [R, C, Kr, Kc]:
        world.register(agent)

    print("=== Scenario edge-15: declared_document_hash diverges from applied (§8.4) ===")
    INC_E15 = "0000e15a-0000-4000-8000-00000000e15a"

    R.publish_profile(keeper_name="Kr")

    # C declares a norm_document_hash that is simply wrong — not the hash of any document
    # the Referee could have retrieved, standing in for "fetched a stale or tampered copy".
    # A real mismatch would arise from an actual older document; a synthetic wrong value
    # exercises the same code path without needing a second document fixture.
    stale_hash = "1234" * 16
    applied_hash = hash_norm_document("rackp.standard.v1")
    assert stale_hash != applied_hash, "the scenario requires the declared hash to diverge"
    C.session_start([{"norm_profile_id": "rackp.standard.v1",
                      "norm_fetch_url": "https://rackp.io/norms/rackp-standard-v1.json",
                      "norm_document_hash": stale_hash}])

    anchor_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(5):
        C.act("creation_step", {"step": i, "type": "human_input", "chars_typed": 120 + i * 30})
    anchor_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    content_id    = "doc-manuscript-e15-001"
    artifact_data = {"title": "manuscript", "author": C.terminal_id, "word_count": 4200}
    data_hash     = hash_claim(artifact_data)

    C.deposit_fee(INC_E15, amount=50, currency="USD")
    C.send_assessment_request(actor_name=None, incident_id=INC_E15,
                              incident_summary=f"PoHI certification for {content_id}")
    R.request_evidence("C", incident_id=INC_E15)
    C.submit_evidence(INC_E15, pohi={
        "subject_data_hash": data_hash,
        "anchor_range": {"start": anchor_start, "end": anchor_end},
        "content_id": content_id,
    })
    R.verify_claim_chain("C", incident_id=INC_E15, keeper_name="Kc")
    R.issue_phi_cert(INC_E15)
    R.claim_fee(INC_E15)
    R.send_fee_receipt(INC_E15)

    # --- assertions: both hashes recorded, neither preferred, nothing invalidated ---
    print("\n--- assertions ---")
    cert = world.last("C", "POH_CERTIFICATE")
    assert cert is not None, "C must receive a POH_CERTIFICATE despite the divergence"

    # THE point: applied_document_hash is what the Referee actually used (the ratio below
    # is computed under THIS document, regardless of what C declared) and
    # declared_document_hash is C's unmodified declaration — the two disagree, and the
    # certificate carries both rather than silently preferring or reconciling them.
    assert cert["norms_used"] == [
        {"profile_id": "rackp.standard.v1",
         "applied_document_hash": applied_hash,
         "declared_document_hash": stale_hash}
    ], f"the cert must record both hashes unreconciled, got {cert.get('norms_used')}"
    assert cert["norms_used"][0]["applied_document_hash"] != cert["norms_used"][0]["declared_document_hash"], \
        "the scenario is void if the two hashes happen to match"

    # The divergence does NOT invalidate the certificate or degrade the ratio: 5 human
    # creation steps + 1 SESSION_START -> the same HIGH-confidence 1.0 base_07 gets when
    # the declaration matches. §8.4 is disclosure only, same as norm_jurisdiction_mismatch.
    prov = cert["provenance"]
    assert prov["human_ratio"] == 1.0 and prov["confidence_level"] == "HIGH", \
        f"a document-hash mismatch must not degrade provenance, got {prov}"

    # proof_hash still recomputes correctly with the divergence present — the mismatch is
    # additional content in norms_used, not a special case for the hash's own exclusion rule.
    stripped_cert = {k: v for k, v in cert.items() if k not in ("proof_hash", "signature")}
    assert cert["proof_hash"] == hash_claim(stripped_cert), \
        "proof_hash must still equal the hash of the certificate with proof_hash/signature excluded"

    assert Kc._escrow[INC_E15]["state"] == "SETTLED"

    print("[OK] declared_document_hash diverging from applied_document_hash: both recorded"
          " in norms_used unreconciled; certificate still issued; human_ratio=1.0/HIGH"
          " unaffected by the divergence (§8.4 disclosure-only, matching §9.5's treatment"
          " of norm_jurisdiction_mismatch); proof_hash exclusion rule still holds.")

if __name__ == "__main__":
    run()
