# base_07_phi_cert.py
# RFC §8 (Proof of Human Involvement): a Claimant certifies the human involvement in an
# artifact, with NO Actor. The canonical §8 flow reuses the GENERIC protocol messages —
# it does NOT define PoHI-specific message types:
#
#   Claimant --[ASSESSMENT_REQUEST (no actor_id)]--> Referee
#   Referee  --[EVIDENCE_QUERY_REQUEST]------------> Claimant
#   Claimant --[EVIDENCE_SUBMISSION]---------------> Referee   (artifact binding in payload)
#   Referee  --[ANCHOR_CHAIN_QUERY]----------------> Keeper    (evaluates anchor density)
#   Referee  --[POH_CERTIFICATE]-------------------> Claimant
#
# The artifact binding (subject_data_hash, anchor_range, content_id) rides in the
# EVIDENCE_SUBMISSION payload (additionalProperties), so no PoHI-specific message or schema
# is needed. The Referee issues a POH_CERTIFICATE — instead of a CONTRIBUTION_RESULT — for a
# no-Actor assessment whose submission carries such a binding.
# Expected: POH_CERTIFICATE with human_ratio derived from anchor density.
# Keeper: split topology — Kr is the Referee's Keeper, Kc the Claimant's; R queries Kc for
# the anchor chain (cross-Keeper ANCHOR_CHAIN_QUERY via R.verify_claim_chain).
from classes.World import World
from classes.Claimant import Claimant
from classes.Referee import Referee
from classes.Keeper import Keeper
from classes.Hasher import hash_claim
from datetime import datetime, timezone

def run():
    world = World()
    R  = Referee("R",  keeper_name="Kr")
    C  = Claimant("C", keeper_name="Kc")
    Kr = Keeper("Kr")
    Kc = Keeper("Kc")
    for agent in [R, C, Kr, Kc]:
        world.register(agent)

    print("=== Scenario 07: Proof of Human Involvement certificate (canonical §8 flow) ===")
    PHI_007 = "00000007-0000-4000-8000-000000000007"

    # Referee publishes profile → SESSION_START anchor to Kr (RFC §6.19)
    R.publish_profile(keeper_name="Kr")

    # Phase 1: Norm declaration (Actor absent — PoHI is a Claimant-only flow).
    C.session_start([{"norm_profile_id": "rackp.standard.v1", "norm_fetch_url": "https://rackp.io/norms/standard/v1"}])

    # C continuously anchors each step of its creative process (keystrokes, editing
    # session, video frames, …) to its Keeper. anchor_range brackets that activity.
    anchor_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(5):
        C.act("creation_step", {"step": i, "type": "human_input", "chars_typed": 120 + i * 30})
    anchor_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # The artifact C produced — its hash binds the certificate to this specific output.
    content_id    = "doc-manuscript-2026-001"
    artifact_data = {"title": "manuscript", "author": C.terminal_id, "word_count": 4200}
    data_hash     = hash_claim(artifact_data)

    # PoHI service fee (single depositor — the Claimant, STD-029).
    C.deposit_fee(PHI_007, amount=50, currency="USD")

    print(f"\n--- C files a Claimant-only assessment for content_id={content_id} ---")
    # Phase 2: a generic ASSESSMENT_REQUEST with NO actor_id is the PoHI filing (RFC §8.1 /
    # assessment_request.json: "Omit for Claimant-only assessments").
    C.send_assessment_request(actor_name=None, incident_id=PHI_007,
                              incident_summary=f"PoHI certification for {content_id}")

    # Phase 3: generic evidence collection. The artifact binding travels in the submission
    # payload — no PoHI-specific message.
    R.request_evidence("C", incident_id=PHI_007)
    C.submit_evidence(PHI_007, pohi={
        "subject_data_hash": data_hash,
        "anchor_range": {"start": anchor_start, "end": anchor_end},
        "content_id": content_id,
    })
    # The Referee evaluates the anchor density of C's chain (the basis for human_ratio).
    R.verify_claim_chain("C", incident_id=PHI_007, keeper_name="Kc")

    # Phase 4: the no-Actor + artifact-binding assessment resolves to a POH_CERTIFICATE.
    # notify_assessment_complete is implicit in issue_phi_cert (it notifies C's Keeper so the
    # pull-based fee claim can be validated). There is no opposing party to notify.
    R.issue_phi_cert(PHI_007)
    R.claim_fee(PHI_007)         # pull-based payment from C's Keeper (RFC §6.22)
    R.send_fee_receipt(PHI_007)

    # --- assertions: PoHI certificate via the canonical generic flow (no Actor) ---
    print("\n--- assertions ---")
    cert = world.last("C", "POH_CERTIFICATE")
    assert cert is not None, "C must receive a POH_CERTIFICATE"
    assert cert["subject_terminal_id"] == C.terminal_id, "cert must be about C"
    # The artifact binding carried in the generic EVIDENCE_SUBMISSION payload reached the
    # certificate intact — proving no PoHI-specific message was needed.
    assert cert["subject_data_hash"] == data_hash, "the cert must bind the submitted artifact hash"
    assert cert["anchor_range"] == {"start": anchor_start, "end": anchor_end}, \
        f"the cert must carry the submitted anchor_range, got {cert['anchor_range']}"
    prov = cert["provenance"]
    # All 6 anchors (1 SESSION_START + 5 human creation steps) are human input → ratio 1.0.
    assert prov["human_ratio"] == 1.0 and prov["ai_ratio"] == 0.0, f"got {prov}"
    assert prov["confidence_level"] == "HIGH"
    # Provenance ratios partition 1.0 (§8), as in every assessment.
    assert round(prov["human_ratio"] + prov["ai_ratio"], 10) == 1.0
    # The filing used a generic, no-Actor ASSESSMENT_REQUEST — actor_id omitted entirely.
    req = world.last("R", "ASSESSMENT_REQUEST")
    assert req is not None and "actor_id" not in req, "a PoHI filing omits actor_id (Claimant-only)"
    # The single PoHI fee was settled via the pull path on C's Keeper.
    assert Kc._escrow[PHI_007]["state"] == "SETTLED"

    # The cert issuance was self-anchored as POH_CERT_ISSUED to the Referee's own Keeper
    # (Kr), feeding poh_cert_count (RFC §8.4). This is the verifiable record the license
    # fee reconciles against (RFC-0002 §1.3) — without it a PoHI cert would be unbillable
    # and invisible. Crucially it is counted SEPARATELY from assessment_count: a PoHI cert
    # is not an incident assessment, so it must not enter the appeal_rate / named_as_actor_rate
    # denominators (RFC §6.21).
    rstats = Kr._j_stats[R.terminal_id]
    assert rstats["poh_cert_count"] == 1, \
        f"one PoHI cert issued -> poh_cert_count==1 (license-billable), got {rstats['poh_cert_count']}"
    assert rstats["assessment_count"] == 0, \
        f"a PoHI cert is not an incident assessment -> assessment_count stays 0, got {rstats['assessment_count']}"

    print("[OK] PoHI via canonical §8 flow (generic messages, no PoHI-specific type):"
          " no-Actor ASSESSMENT_REQUEST + artifact binding in EVIDENCE_SUBMISSION payload ->"
          " POH_CERTIFICATE, human_ratio=1.0/ai_ratio=0.0 (sum 1.0), HIGH; binding intact;"
          " single-depositor fee SETTLED; POH_CERT_ISSUED -> poh_cert_count=1 (license-billable),"
          " assessment_count=0 (reputation denominators uncontaminated).")

if __name__ == "__main__":
    run()
