#!/usr/bin/env python3
"""A testing window for Context for Claude: chat on the right, every related log on the left.

The point is correlation. Asking Claude a question and reading a log file separately tells you
almost nothing — what you need to see is *which tools that question actually triggered*, in the
moment it triggered them, next to what the app was doing at the same time. So every turn is
timestamped, the MCP traffic in that window is attributed to it, and the left pane says plainly
when a question caused no tool call at all, which is the failure that looks exactly like success.

    python3 scripts/testbench.py           # then open http://127.0.0.1:8899

No dependencies. Reads only; it never writes to the app's database or config.
"""
from __future__ import annotations

import html
import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.environ.get("TESTBENCH_PORT", "8899"))
HOME = Path.home()
SUPPORT = HOME / "Library/Application Support/ContextForClaude"
DB = SUPPORT / "context.db"
HEARTBEAT = SUPPORT / "capture-state.json"
APP_LOG = Path("/tmp/context-for-claude.log")
MCP_LOG = HOME / "Library/Logs/Claude/mcp-server-context-for-claude.log"

events: "queue.Queue[dict]" = queue.Queue()
subscribers: list["queue.Queue[dict]"] = []
lock = threading.Lock()


def emit(source: str, text: str, level: str = "info") -> None:
    event = {"t": time.time(), "source": source, "level": level, "text": text.rstrip()}
    with lock:
        for sub in list(subscribers):
            sub.put(event)


# --------------------------------------------------------------------------- log tails

def tail(path: Path, source: str) -> None:
    """Follow a file, surviving truncation and re-creation — both happen on every app relaunch."""
    handle = None
    inode = None
    while True:
        try:
            if handle is None:
                if not path.exists():
                    time.sleep(1)
                    continue
                handle = path.open("r", errors="replace")
                handle.seek(0, os.SEEK_END)
                inode = path.stat().st_ino
                emit("bench", f"following {path}")
            line = handle.readline()
            if line:
                level = "error" if re.search(r"\[error\]|error|failed", line, re.I) else "info"
                emit(source, line, level)
                continue
            # No new data: check whether the file was rotated out from under us.
            time.sleep(0.25)
            if not path.exists() or path.stat().st_ino != inode:
                handle.close()
                handle = None
        except Exception as exc:  # a tail that dies takes the whole pane's usefulness with it
            emit("bench", f"tail {path.name} restarting: {exc}", "error")
            handle = None
            time.sleep(1)


# --------------------------------------------------------------------------- capture state

def watch_capture() -> None:
    """Poll the things a log line never tells you: is it capturing, and is the store growing."""
    last = None
    while True:
        try:
            state = json.loads(HEARTBEAT.read_text()) if HEARTBEAT.exists() else None
            counts = (0, 0, 0)
            if DB.exists():
                con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
                counts = tuple(
                    con.execute(f"select count(*) from {t}").fetchone()[0]
                    for t in ("sessions", "segments", "frames")
                )
                con.close()
            age = round(time.time() - state["updatedAt"], 1) if state else None
            snapshot = {
                # A heartbeat older than 90s means the process is gone or wedged, whatever the
                # `capturing` flag last claimed — the exact bug this app shipped once already.
                "capturing": bool(state and state.get("capturing") and age is not None and age < 90),
                "stale": age is None or age >= 90,
                "beat": age,
                "paused": (state or {}).get("pausedReason"),
                "sessions": counts[0], "segments": counts[1], "frames": counts[2],
            }
            if snapshot != last:
                emit("state", json.dumps(snapshot))
                last = snapshot
        except Exception as exc:
            emit("bench", f"state poll: {exc}", "error")
        time.sleep(2)


# --------------------------------------------------------------------------- chat

CLAUDE = shutil.which("claude") or str(HOME / ".local/bin/claude")


def ask(prompt: str) -> dict:
    """Run one turn through the real Claude CLI, then report which of our tools it actually used."""
    before = MCP_LOG.stat().st_size if MCP_LOG.exists() else 0
    started = time.time()
    emit("bench", f"asking Claude: {prompt[:120]}")

    # Non-interactive Claude will not call an MCP tool it has no permission for, and there is no
    # prompt to answer in this mode — it simply reports the tool as blocked. The seven are named
    # individually rather than wildcarded: this window should grant exactly what it is testing.
    allowed = ",".join(
        f"mcp__context-for-claude__{t}"
        for t in ("recall", "recent", "conversations", "transcript", "screen", "activity", "status")
    )

    try:
        proc = subprocess.run(
            # `stream-json` is what makes attribution exact. The MCP log under ~/Library/Logs/Claude
            # belongs to Claude *Desktop*; the CLI never writes there, so scanning it reported "no
            # tool was called" for turns that had plainly just called one — the same false negative
            # this product exists to avoid. The CLI's own tool_use blocks are the ground truth.
            [CLAUDE, "-p", prompt, "--allowedTools", allowed,
             "--output-format", "stream-json", "--verbose"],
            capture_output=True, text=True, timeout=300, cwd=str(HOME),
        )
    except FileNotFoundError:
        return {"reply": f"claude CLI not found at {CLAUDE}", "tools": [], "seconds": 0}
    except subprocess.TimeoutExpired:
        return {"reply": "timed out after 300s", "tools": [], "seconds": 300}

    reply, tools = "", []
    for line in (proc.stdout or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            reply = (event.get("result") or "").strip()
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "")
                if name.startswith("mcp__context-for-claude__"):
                    tools.append(name.rsplit("__", 1)[-1])
    if not reply:
        reply = (proc.stderr or "").strip() or "(no output)"

    # Anything Claude Desktop called in the same window, on top of this turn's own calls.
    if MCP_LOG.exists():
        with MCP_LOG.open("r", errors="replace") as fh:
            fh.seek(before)
            for line in fh:
                match = re.search(
                    r'"name"\s*:\s*"(recall|recent|conversations|transcript|screen|activity|status)"',
                    line)
                if match:
                    tools.append(match.group(1))

    emit("bench", f"turn finished in {time.time()-started:.1f}s, tools: {tools or 'NONE'}",
         "error" if not tools else "info")
    return {"reply": reply, "tools": tools, "seconds": round(time.time() - started, 1)}


# --------------------------------------------------------------------------- http

PAGE = r"""<!doctype html><meta charset=utf-8><title>Context for Claude — testing window</title>
<style>
:root{--paper:#FBF8F4;--ink:#171412;--line:#E6DFD6;--mid:#6B625B;--faint:#A39A92;--bronze:#8F6420;--red:#C9352B}
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;font:13px/1.5 -apple-system,system-ui,sans-serif;background:var(--paper);color:var(--ink)}
#left{flex:1.15;display:flex;flex-direction:column;border-right:1px solid var(--line);min-width:0}
#right{flex:1;display:flex;flex-direction:column;min-width:0}
header{padding:10px 14px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap}
h1{font-size:13px;margin:0;font-weight:600}
#status{font-size:12px;color:var(--mid)}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px}
.on{background:#2E8B57}.off{background:var(--red)}
input[type=text]{border:1px solid var(--line);border-radius:7px;padding:5px 9px;font:inherit;background:#fff;color:inherit}
#log{flex:1;overflow:auto;padding:8px 12px;font:11.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word}
.row{display:flex;gap:8px;padding:1px 0}
.ts{color:var(--faint);flex:none}
.src{flex:none;width:64px;color:var(--bronze)}
.src.mcp{color:#2E8B57}.src.state{color:var(--mid)}.src.bench{color:var(--faint)}
.err .msg{color:var(--red)}
#chat{flex:1;overflow:auto;padding:14px}
.msg-you,.msg-claude{margin-bottom:14px}
.who{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);margin-bottom:3px}
.body{word-break:break-word}
.body p{margin:0 0 9px}
.body h3,.body h4,.body h5,.body h6{margin:14px 0 6px;font-size:13px;font-weight:600}
.body ul,.body ol{margin:0 0 9px;padding-left:20px}
.body li{margin:2px 0}
.body code{background:#EFE9DE;border:1px solid var(--line);border-radius:4px;padding:0 4px;font:11.5px ui-monospace,Menlo,monospace}
.body pre{background:#EFE9DE;border:1px solid var(--line);border-radius:7px;padding:9px 11px;overflow-x:auto;margin:0 0 9px}
.body pre code{background:none;border:0;padding:0}
.body table{border-collapse:collapse;margin:0 0 10px;font-size:12px;display:block;overflow-x:auto}
.body th,.body td{border:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
.body th{background:#EFE9DE;font-weight:600}
.body a{color:var(--bronze)}
.msg-you .body{white-space:pre-wrap}
.tools{margin-top:6px;font-size:11.5px;color:var(--mid)}
.tag{display:inline-block;background:#EFE9DE;border:1px solid var(--line);border-radius:20px;padding:1px 8px;margin-right:4px}
.none{color:var(--red)}
form{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)}
form input{flex:1}
button{border:0;background:var(--ink);color:var(--paper);border-radius:20px;padding:6px 16px;font:inherit;font-weight:600;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
</style>
<div id=left>
  <header><h1>Logs</h1><span id=status>connecting…</span>
    <input type=text id=filter placeholder="filter…" style="margin-left:auto;width:150px">
  </header>
  <div id=log></div>
</div>
<div id=right>
  <header><h1>Claude</h1><span id=hint style="color:var(--mid);font-size:12px">asks the real CLI, with the context-for-claude connector</span></header>
  <div id=chat></div>
  <form id=f><input type=text id=q placeholder="Ask something that should need your context…" autocomplete=off><button id=send>Send</button></form>
</div>
<script>
// Markdown, rendered locally. Every reply is markdown — the tools deliberately return it — so
// showing it as plain text put ## and ** in front of the reader. Escaping happens FIRST and
// unconditionally: these replies quote the user's own OCR'd screen text, which routinely contains
// angle brackets and markup, and none of it may reach the DOM as HTML.
function esc(s){return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function inline(s){
  return s
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g,'$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md(src){
  const lines = esc(src).split('\n');
  const out = []; let i = 0, list = null;
  const closeList = () => { if(list){ out.push(`</${list}>`); list = null; } };
  while(i < lines.length){
    const line = lines[i];
    if(/^```/.test(line)){                       // fenced code
      closeList(); const body = [];
      for(i++; i < lines.length && !/^```/.test(lines[i]); i++) body.push(lines[i]);
      i++; out.push(`<pre><code>${body.join('\n')}</code></pre>`); continue;
    }
    if(/^\s*\|.*\|\s*$/.test(line) && /^\s*\|[-: |]+\|\s*$/.test(lines[i+1]||'')){
      closeList();                                // table
      const cells = r => r.trim().replace(/^\||\|$/g,'').split('|').map(c=>inline(c.trim()));
      const head = cells(line); i += 2;
      const rows = [];
      while(i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push(`<table><thead><tr>${head.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${
        rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      continue;
    }
    let m;
    if((m = line.match(/^(#{1,4})\s+(.*)$/))){    // heading
      closeList(); out.push(`<h${m[1].length+2}>${inline(m[2])}</h${m[1].length+2}>`); i++; continue;
    }
    if((m = line.match(/^\s*[-*]\s+(.*)$/))){     // bullet
      if(list !== 'ul'){ closeList(); out.push('<ul>'); list = 'ul'; }
      out.push(`<li>${inline(m[1])}</li>`); i++; continue;
    }
    if((m = line.match(/^\s*\d+\.\s+(.*)$/))){    // numbered
      if(list !== 'ol'){ closeList(); out.push('<ol>'); list = 'ol'; }
      out.push(`<li>${inline(m[1])}</li>`); i++; continue;
    }
    if(!line.trim()){ closeList(); i++; continue; }
    closeList();
    const para = [];
    while(i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*[-*]\s|\s*\d+\.\s|\s*\|)/.test(lines[i]))
      para.push(lines[i++]);
    out.push(`<p>${inline(para.join('<br>'))}</p>`);
  }
  closeList();
  return out.join('');
}
const logEl=document.getElementById('log'),chat=document.getElementById('chat'),
      statusEl=document.getElementById('status'),filter=document.getElementById('filter');
let rows=[];
function paint(){
  const f=filter.value.toLowerCase();
  logEl.innerHTML=rows.filter(r=>!f||r.text.toLowerCase().includes(f)||r.source.includes(f))
    .slice(-1200).map(r=>`<div class="row ${r.level==='error'?'err':''}"><span class=ts>${
      new Date(r.t*1000).toLocaleTimeString()}</span><span class="src ${r.source}">${r.source}</span><span class=msg>${
      r.text.replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</span></div>`).join('');
  logEl.scrollTop=logEl.scrollHeight;
}
filter.oninput=paint;
new EventSource('/events').onmessage=e=>{
  const ev=JSON.parse(e.data);
  if(ev.source==='state'){
    const s=JSON.parse(ev.text);
    statusEl.innerHTML=`<span class="dot ${s.capturing?'on':'off'}"></span>`+
      (s.stale?'no heartbeat — not running':(s.capturing?'capturing':'paused'))+
      ` · ${s.frames} frames · ${s.segments} lines`+(s.paused?` · ${s.paused}`:'');
    return;
  }
  rows.push(ev); paint();
};
document.getElementById('f').onsubmit=async e=>{
  e.preventDefault();
  const q=document.getElementById('q'),send=document.getElementById('send');
  const text=q.value.trim(); if(!text)return;
  q.value=''; send.disabled=true;
  chat.insertAdjacentHTML('beforeend',`<div class=msg-you><div class=who>You</div><div class=body></div></div>`);
  chat.lastElementChild.querySelector('.body').textContent=text;
  chat.scrollTop=chat.scrollHeight;
  const r=await (await fetch('/ask',{method:'POST',body:JSON.stringify({q:text})})).json();
  const tools=r.tools.length
    ? r.tools.map(t=>`<span class=tag>${t}</span>`).join('')
    : `<span class=none>no tool was called — Claude answered without your context</span>`;
  chat.insertAdjacentHTML('beforeend',
    `<div class=msg-claude><div class=who>Claude · ${r.seconds}s</div><div class=body></div><div class=tools>${tools}</div></div>`);
  const bodies=chat.querySelectorAll('.msg-claude .body');
  bodies[bodies.length-1].innerHTML=md(r.reply);
  chat.scrollTop=chat.scrollHeight; send.disabled=false; q.focus();
};
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):  # the page has its own log pane; stdout noise helps nobody
        pass

    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            mine: "queue.Queue[dict]" = queue.Queue()
            with lock:
                subscribers.append(mine)
            try:
                while True:
                    event = mine.get()
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                with lock:
                    if mine in subscribers:
                        subscribers.remove(mine)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/ask":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", 0))
        prompt = json.loads(self.rfile.read(length))["q"]
        result = ask(prompt)
        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    for target, args in (
        (tail, (APP_LOG, "app")),
        (tail, (MCP_LOG, "mcp")),
        (watch_capture, ()),
    ):
        threading.Thread(target=target, args=args, daemon=True).start()
    print(f"testing window: http://127.0.0.1:{PORT}")
    print(f"  app log: {APP_LOG}")
    print(f"  mcp log: {MCP_LOG}")
    print("  note: the app only writes its log when launched with CONTEXT_DEBUG=1")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
