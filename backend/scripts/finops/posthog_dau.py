"""Pull PostHog DAU by platform for a window: clean core-product DAU and legacy all-events DAU."""

import asyncio, sys, os, json, csv, pathlib

# The PostHog MCP client needs a modern `mcp` package. Whichever python launched this may be
# on an older one (the hermes agent venv ships an mcp without streamablehttp_client), so
# re-exec under the skill venv that is known to have it rather than failing at import time.
_VENV = pathlib.Path.home() / ".hermes/skills/omi/omi-improvements-dashboard/.venv/bin/python"
try:
    from mcp.client.streamable_http import streamablehttp_client  # noqa: F401
except Exception:  # noqa: BLE001
    if _VENV.exists() and pathlib.Path(sys.executable).resolve() != _VENV.resolve():
        os.execv(str(_VENV), [str(_VENV), os.path.abspath(__file__), *sys.argv[1:]])
    raise

sys.path.insert(0, os.path.expanduser("~/.claude/skills/omi-posthog-macos/scripts"))
from posthog_http import posthog_mcp_session

PROJECT = 302298
CTX = "Computing daily active users by platform for an Omi unit-cost report across mobile and desktop clients."
START, END = sys.argv[1], sys.argv[2]  # END exclusive
CORE_EVENTS = """('Memory Created','Memory Extracted','Action Items Page Opened','Action Item Completed','Action Item Manually Added','Action Item Edited','Task Extracted','Task Promoted','Task Completed','Task Added','Chat Message Sent','chat_agent_query_completed','chat_tool_call_completed','floating_bar_query_sent','floating_bar_ptt_started','Phone Mic Recording Started','Monitoring Started','Conversation List Item Clicked','Conversation Detail Opened','Daily Summary Detail Viewed','Rewind Screenshot Viewed')"""
Q = {
    "clean": f"""SELECT toDate(timestamp) AS day, properties['$os'] AS os, uniq(person_id) AS users FROM events
   WHERE timestamp >= toDateTime('{START} 00:00:00') AND timestamp < toDateTime('{END} 00:00:00')
   AND properties['$os'] IN ('iOS','Android','macOS','Windows') AND event IN {CORE_EVENTS}
   AND event NOT LIKE 'cfc_%' GROUP BY day, os ORDER BY day, os""",
    "all_events": f"""SELECT toDate(timestamp) AS day, properties['$os'] AS os, uniq(person_id) AS users FROM events
   WHERE timestamp >= toDateTime('{START} 00:00:00') AND timestamp < toDateTime('{END} 00:00:00')
   AND properties['$os'] IN ('iOS','Android','macOS','Windows') AND event NOT LIKE 'cfc_%'
   GROUP BY day, os ORDER BY day, os""",
}


def parse(text):
    lines = [l.strip() for l in text.splitlines() if "|" in l and not l.startswith("Error:")]
    if not lines:
        return [], text[:400]
    h = lines[0].split("|")
    return [dict(zip(h, l.split("|"))) for l in lines[1:] if len(l.split("|")) == len(h)], ""


async def main():
    out = []
    async with posthog_mcp_session() as s:
        await s.call_tool("switch-project", {"projectId": PROJECT, "context": CTX})
        for name, sql in Q.items():
            r = await s.call_tool("execute-sql", {"query": sql, "context": CTX})
            raw = "\n".join(getattr(i, "text", repr(i)) for i in r.content)
            rows, err = parse(raw)
            if err:
                print(name, "ERR", err, file=sys.stderr)
            for row in rows:
                out.append({"definition": name, **row})
    with open(sys.argv[3], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["definition", "day", "os", "users"])
        w.writeheader()
        w.writerows(out)
    print(len(out), "rows")


asyncio.run(main())
