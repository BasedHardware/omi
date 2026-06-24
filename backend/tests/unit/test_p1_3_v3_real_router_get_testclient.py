import importlib.util
from pathlib import Path


def _load_module(script_path: Path):
    spec = importlib.util.spec_from_file_location("p1_3_v3_real_router_get_testclient", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_router_get_testclient_runner_exists_and_preserves_safety_flags():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_v3_real_router_get_testclient.py"
    assert script_path.exists(), "missing controlled real-router GET TestClient proof runner"

    module = _load_module(script_path)
    report = module.build_report(execute=True)

    assert report["status"] == "BLOCKED"
    assert report["read_only"] is True
    assert report["mutation_allowed"] is False
    assert report["app_startup_executed"] is False
    assert report["production_app_imported"] is False
    assert report["minimal_fastapi_app_created"] is True
    assert report["real_router_included_under_stubs"] is True
    assert report["network_or_provider_calls_executed"] is False
    assert report["provider_calls_executed"] is False
    assert report["real_firestore_reads_executed"] is False
    assert report["firestore_writes_executed"] is False
    assert report["pinecone_calls_executed"] is False
    assert report["runtime_cutover_claimed"] is False
    assert report["production_rollout_approved"] is False


def test_real_router_get_testclient_executes_get_only_and_keeps_mutations_blocked():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_real_router_get_testclient.py")
    report = module.build_report(execute=True)
    probe = report["probe"]

    assert probe["testclient_ok"] is True
    assert probe["executed_routes"] == ["GET /v3/memories", "GET /v3/memories?limit=17&offset=3"]
    assert probe["unexecuted_mutating_routes"] == ["POST /v3/memories", "DELETE /v3/memories/{memory_id}"]
    assert probe["mutation_flags"] == {
        "create_memory": False,
        "save_memories": False,
        "delete_memory": False,
        "delete_all_memories": False,
        "upsert_memory_vector": False,
        "upsert_memory_vectors_batch": False,
        "delete_memory_vector": False,
        "delete_memory_vectors_batch": False,
        "update_personas_async": False,
        "executor_submit": False,
        "run_blocking": False,
    }
    assert probe["auth_dependency_overridden"] is True
    assert probe["stubbed_legacy_get_memories_call_count"] == 2
    assert report["summary"]["post_delete_unexecuted"] is True
    assert report["summary"]["mutation_flags_clear"] is True


def test_real_router_get_testclient_pins_current_legacy_get_runtime_behavior():
    root = Path(__file__).resolve().parents[2]
    module = _load_module(root / "scripts" / "p1_3_v3_real_router_get_testclient.py")
    report = module.build_report(execute=True)
    probe = report["probe"]

    assert probe["default_get"]["status_code"] == 200
    assert probe["explicit_get"]["status_code"] == 200
    assert probe["observed_get_memories_calls"] == [
        {"uid": "stubbed-test-uid", "limit": 5000, "offset": 0},
        {"uid": "stubbed-test-uid", "limit": 17, "offset": 3},
    ]
    assert probe["default_get"]["observed_legacy_call"] == {"uid": "stubbed-test-uid", "limit": 5000, "offset": 0}
    assert probe["explicit_get"]["observed_legacy_call"] == {"uid": "stubbed-test-uid", "limit": 17, "offset": 3}
    assert probe["current_first_page_limit_override"] == "offset=0 coerces limit to 5000 before legacy get_memories"
    assert probe["explicit_limit_offset_preserved_when_offset_nonzero"] is True
    default_item = probe["default_get"]["body"][0]
    assert default_item["id"] == "legacy-default"
    assert default_item["uid"] == "stubbed-test-uid"
    assert default_item["content"] == "legacy default page memory"
    assert default_item["category"] == "system"
    assert default_item["visibility"] == "private"
    assert default_item["tags"] == ["legacy"]
    assert default_item["reviewed"] is True
    assert default_item["manually_added"] is False
    assert default_item["edited"] is False
    assert default_item["is_locked"] is False
    assert default_item["kg_extracted"] is False
    assert default_item["evidence"] == []
    assert default_item["arguments"] == {}
    assert default_item["subject_attribution"] == "legacy_assumed"
    assert "memory_source" not in default_item
    assert "projection_generation" not in default_item
    assert "archive_default_visible" not in default_item


def test_real_router_get_testclient_confirms_memory_adapters_not_invoked_and_links_readiness():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "p1_3_v3_real_router_get_testclient.py"
    module = _load_module(script_path)
    report = module.build_report(execute=True)

    assert report["memory_adapters_invoked"] is False
    assert report["probe"]["memory_adapter_modules_loaded"] == []
    assert report["future_get_wiring_seam"] == [
        "GET /v3/memories query params",
        "adapt_v3_request_parameters(...) request adapter",
        "plan_v3_memory_route(...) route planner",
        "adapt_v3_memory_response(...) response adapter",
    ]

    readiness = _load_module(root / "scripts" / "p1_3_v3_external_compatibility_readiness.py").build_report(
        execute=True
    )
    proof = readiness["real_router_get_testclient_proof"]
    assert proof["service"] == "backend/scripts/p1_3_v3_real_router_get_testclient.py"
    assert proof["test"] == "backend/tests/unit/test_p1_3_v3_real_router_get_testclient.py"
    assert proof["runtime_wired"] is False
    assert proof["production_rollout_approved"] is False
    assert proof["external_calls"] == []
    assert proof["get_only_testclient_under_stubs"] is True
    assert proof["post_delete_unexecuted"] is True
    assert readiness["summary"]["real_router_get_testclient_proof_present"] is True

    test_sh = (root / "test.sh").read_text(encoding="utf-8")
    ticket_doc = (root.parent / "docs" / "epics" / "memory_implementation_tickets.md").read_text(encoding="utf-8")
    oracle_doc = (root.parent / "docs" / "epics" / "memory_t20_oracle_milestone_review.md").read_text(encoding="utf-8")
    assert "test_p1_3_v3_real_router_get_testclient.py" in test_sh
    assert "p1_3_v3_real_router_get_testclient.py" in ticket_doc
    assert "p1_3_v3_real_router_get_testclient.py" in oracle_doc
