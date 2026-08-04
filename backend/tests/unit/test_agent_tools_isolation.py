from unittest.mock import MagicMock, patch

import routers.agent_tools as agent_tools


def _tool(name: str, schema_raises: bool = False):
    t = MagicMock()
    t.name = name
    t.description = f"{name} description"
    if schema_raises:
        t.args_schema.model_json_schema.side_effect = RuntimeError("broken schema")
    else:
        t.args_schema.model_json_schema.return_value = {"properties": {}, "required": []}
    return t


class TestListToolsIsolation:
    def test_one_malformed_schema_does_not_drop_remaining_tools(self):
        good_a = _tool("good_a")
        bad = _tool("bad", schema_raises=True)
        good_b = _tool("good_b")
        with (
            patch.object(agent_tools, "load_app_tools", return_value=[good_a, bad, good_b]),
            patch.object(agent_tools, "record_fallback") as fallback,
        ):
            result = agent_tools.list_tools(uid="u1")
        names = [t["name"] for t in result["tools"]]
        assert "good_a" in names
        assert "good_b" in names
        assert "bad" not in names
        # Exactly one degraded event per request, not per tool.
        assert fallback.call_count == 1
        assert fallback.call_args.kwargs["outcome"] == "degraded"

    def test_whole_lane_failure_keeps_core_tools_and_records_fallback(self):
        with (
            patch.object(agent_tools, "load_app_tools", side_effect=RuntimeError("redis down")),
            patch.object(agent_tools, "record_fallback") as fallback,
        ):
            result = agent_tools.list_tools(uid="u1")
        assert len(result["tools"]) == len(agent_tools.CORE_TOOLS)
        assert fallback.call_count == 1

    def test_healthy_path_records_nothing(self):
        with (
            patch.object(agent_tools, "load_app_tools", return_value=[_tool("good")]),
            patch.object(agent_tools, "record_fallback") as fallback,
        ):
            result = agent_tools.list_tools(uid="u1")
        assert any(t["name"] == "good" for t in result["tools"])
        assert fallback.call_count == 0
