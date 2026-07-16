# base_11_discovery.py
# §6.18 (REFEREE_DISCOVERY_REQUEST), §6.19 (REFEREE_PROFILE),
#           §6.20 (REFEREE_STATS_QUERY), §6.21 (REFEREE_STATS_RESULT)
# What makes this scenario distinct from the others is the *search* surface: a Claimant
# locates Referees and reads their track record from the Keeper. The flow is therefore
# three acts around a base-conformant incident:
#   Act 1 — search → hit: R is discoverable, but has no assessment history yet.
#   Act 2 — incident: a full base_01-style assessment, so R earns one assessment.
#   Act 3 — search again: the same queries now reflect that incident (stats count 0→1,
#           and the min_assessments gate that filtered R out before now lets it through).
from classes.topology import standard_world

NORM_PROFILE_ID = "rackp.standard.v1"
NORM_FETCH_URL  = "https://rackp.io/norms/standard/v1"

def run():
    # publish_profile=False: this scenario publishes the profile explicitly in Act 1.
    world, R, A, C, Kr, Kc, Ka = standard_world(publish_profile=False)

    print("=== Scenario 11: Referee Discovery ===")
    INC_011 = "00000011-0000-4000-8000-000000000011"

    # ================= Act 1: search → hit (no history yet) =================
    print("\n--- Act 1: discover the Referee (no track record yet) ---")
    # Referee publishes its profile to the Keeper registry.
    R.publish_profile(keeper_name="Kr")

    # Discovery by network/availability finds R.
    C.discover_referees(keeper_name="Kr", filters={
        "network": "TESTNET",
        "availability_status": "AVAILABLE"
    })
    # The same registry, gated on min_assessments=1, filters R out — it has no history.
    C.discover_referees(keeper_name="Kr", filters={"min_assessments": 1})
    # Stats: R is known to the Keeper (publishing anchored a SESSION_START) but with
    # assessment_count=0 — no assessment issued yet.
    C.query_referee_stats("R", keeper_name="Kr")

    # ================= Act 2: a full base-conformant incident =================
    # Identical in shape to base_01 (Norm declaration → filing → evidence → settlement),
    # so R legitimately earns exactly one assessment on its record.
    print("\n--- Act 2: base-conformant incident INC-011 (R earns one assessment) ---")
    A.session_start([{"norm_profile_id": NORM_PROFILE_ID, "norm_fetch_url": NORM_FETCH_URL}])
    C.session_start([{"norm_profile_id": NORM_PROFILE_ID, "norm_fetch_url": NORM_FETCH_URL}])
    A.act("navigate", {"destination": "zone_C"})
    C.act("observe",  {"target": "zone_C"})

    C.deposit_fee(INC_011, amount=100, currency="USD")
    C.send_assessment_request(actor_name="A", incident_id=INC_011)
    R.notify_actor("A", incident_id=INC_011)
    R.notify_actor_named("A", incident_id=INC_011)
    A.acknowledge(INC_011)
    R.notify_actor_keeper_open(INC_011)
    A.deposit_fee(INC_011, amount=100, currency="USD")

    R.request_evidence("A", incident_id=INC_011)
    A.submit_evidence(INC_011)
    R.request_evidence("C", incident_id=INC_011)
    C.submit_evidence(INC_011)

    R.verify_claim_chain("A", incident_id=INC_011, keeper_name="Ka")
    R.verify_claim_chain("C", incident_id=INC_011, keeper_name="Kc")

    R.query_fee_status(INC_011)
    R.issue_contribution_result(INC_011)
    R.notify_assessment_complete(INC_011)
    Kc.release_fee(INC_011)
    Ka.release_fee(INC_011)
    R.send_fee_receipt(INC_011)

    # ================= Act 3: search again → reflects the incident =================
    print("\n--- Act 3: re-search - the registry now reflects the incident ---")
    # Stats now report assessment_count=1.
    C.query_referee_stats("R", keeper_name="Kr")
    # The min_assessments=1 gate that filtered R out in Act 1 now lets it through.
    C.discover_referees(keeper_name="Kr", filters={"min_assessments": 1})

    # --- assertions: the search surfaces reflect R's track record before vs after ---
    print("\n--- assertions ---")

    # Three discovery queries, in order: AVAILABLE → 1, min_assessments before → 0,
    # min_assessments after → 1. A no-history Referee is discoverable but filtered out by
    # a min_assessments gate until it has actually issued an assessment (RFC §6.18).
    discos = world.all_of("C", "REFEREE_DISCOVERY_RESULT")
    assert [d["count"] for d in discos] == [1, 0, 1], \
        f"discovery counts must be [1,0,1], got {[d['count'] for d in discos]}"
    assert discos[0]["profiles"][0]["referee_id"] == R.terminal_id, "the matched profile is R's"
    assert discos[2]["profiles"][0]["referee_id"] == R.terminal_id

    # Two stats queries on R's terminal: R is known to the Keeper both times (the profile
    # anchored a SESSION_START), and assessment_count moves 0 → 1 once the incident is
    # assessed (RFC §6.20). This is the "search reflects the incident" link.
    stats = world.all_of("C", "REFEREE_STATS_RESULT")
    assert len(stats) == 2, f"expected 2 stats results, got {len(stats)}"
    assert all(s["terminal_id"] == R.terminal_id for s in stats)
    assert stats[0]["found"] is True and stats[0]["assessment_count"] == 0, \
        f"known terminal, no assessments yet, got {stats[0]}"
    assert stats[1]["found"] is True and stats[1]["assessment_count"] == 1, \
        f"after one incident, assessment_count must be 1, got {stats[1]}"

    # The incident that drove the count was a REAL, base-conformant assessment: both
    # parties verified and a single cert was issued (the source of the 0 → 1 increment).
    result = world.last("C", "CONTRIBUTION_RESULT")
    assert result is not None and result["incident_id"] == INC_011, "Act 2 must produce a verdict"
    verdict = result["assessment"]
    fault = verdict["fault"]
    assert (fault["actor_fault"], fault["claimant_fault"], fault["external_factor"]) == (0.5, 0.5, 0.0), f"got {fault}"
    assert verdict["evidence_sufficiency"]["assessment_status"] == "DEFINITIVE", \
        "a full base-conformant incident is DEFINITIVE, not PROVISIONAL"
    assert "VERIFIED" in result["evidence_provenance"] and "FAILED" not in result["evidence_provenance"]

    print("[OK] Act1 search: discoverable but no history (count 0, min_assessments->0);"
          " Act2 DEFINITIVE incident (0.5/0.5, both verified); Act3 re-search reflects it"
          " (assessment_count->1, min_assessments->1 match).")

if __name__ == "__main__":
    run()
