"""
AI Clone Demo — runs in your browser on Windows.
pip install flask anthropic
set ANTHROPIC_API_KEY=sk-ant-...
python ai_clone_demo.py
Then open http://localhost:5050
"""

import os
import json
import anthropic
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Simulated user memories (in prod these come from Omi's Firestore store)
# Edit these to match your actual personality / facts about you
# ---------------------------------------------------------------------------
USER_MEMORIES = """
- Name: Karthik
- Software engineer, interested in AI and hackathons
- Casual and direct communication style — gets to the point
- Based in the US
- Likes building things quickly and experimenting with new tech
- Uses short sentences when texting, rarely uses punctuation at the end
"""

# ---------------------------------------------------------------------------
# Core clone logic (mirrors backend/utils/llm/clone.py)
# ---------------------------------------------------------------------------

def generate_clone_reply(sender: str, message: str, platform: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    platform_label = {
        "imessage": "iMessage (casual, personal)",
        "telegram": "Telegram (informal messaging)",
        "whatsapp": "WhatsApp (casual messaging)",
    }.get(platform, platform)

    prompt = f"""You are roleplaying as Karthik. Write a reply to a message received on {platform_label}.

What you know about Karthik:
{USER_MEMORIES.strip()}

Message from {sender}:
"{message}"

Write a reply exactly as Karthik would send it. Rules:
- Match his natural tone and vocabulary (casual, not formal)
- Be concise — 1-3 sentences typical for messaging apps
- Do NOT start with a greeting or their name unless it fits naturally
- Sound like a real person texting, not an AI assistant
- Only output the reply text itself, nothing else"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/api/generate-reply")
def api_generate_reply():
    data = request.json or {}
    sender = (data.get("sender") or "").strip()
    message = (data.get("message") or "").strip()
    platform = data.get("platform", "imessage")

    if not sender or not message:
        return jsonify({"error": "sender and message are required"}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set. Set it and restart."}), 500

    try:
        reply = generate_clone_reply(sender, message, platform)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/")
def index():
    return render_template_string(HTML)


# ---------------------------------------------------------------------------
# Inline HTML — the full demo UI
# ---------------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Omi — AI Clone Demo</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0d0d0f;
    color: #e8e8ed;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  .header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 20px 32px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .header-icon {
    width: 40px; height: 40px;
    background: rgba(139,92,246,0.2);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
  }
  .header-title { font-size: 20px; font-weight: 700; color: #fff; }
  .header-sub { font-size: 12px; color: #888; margin-top: 2px; }
  .header-badge {
    margin-left: auto;
    background: rgba(139,92,246,0.2);
    color: #a78bfa;
    font-size: 11px; font-weight: 600;
    padding: 4px 12px;
    border-radius: 20px;
    border: 1px solid rgba(139,92,246,0.3);
  }

  /* ── Layout ── */
  .main { display: flex; flex: 1; overflow: hidden; }

  /* ── Left panel ── */
  .panel {
    width: 260px;
    border-right: 1px solid rgba(255,255,255,0.08);
    padding: 24px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .panel-label {
    font-size: 11px; font-weight: 600; color: #555;
    text-transform: uppercase; letter-spacing: 0.5px;
    padding: 0 8px 8px;
  }
  .platform-row {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 12px;
    border-radius: 10px;
    background: rgba(255,255,255,0.04);
    cursor: pointer;
    transition: background 0.15s;
  }
  .platform-row:hover { background: rgba(255,255,255,0.07); }
  .platform-row.active { background: rgba(139,92,246,0.15); }
  .platform-icon {
    width: 34px; height: 34px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; flex-shrink: 0;
  }
  .platform-name { font-size: 13px; font-weight: 500; }
  .platform-status { font-size: 11px; color: #4ade80; margin-top: 1px; }
  .platform-dot {
    width: 8px; height: 8px; border-radius: 50%;
    margin-left: auto; flex-shrink: 0;
  }
  .dot-green { background: #4ade80; }
  .dot-grey { background: #444; }

  .divider { border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 8px 0; }

  .memories-box {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 12px;
    margin-top: 8px;
  }
  .memories-title { font-size: 11px; font-weight: 600; color: #555; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
  .memories-item { font-size: 12px; color: #888; margin-bottom: 4px; padding-left: 10px; position: relative; }
  .memories-item::before { content: '·'; position: absolute; left: 0; color: #a78bfa; }

  /* ── Feed ── */
  .feed {
    flex: 1;
    padding: 24px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* ── Compose form ── */
  .compose {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 20px;
  }
  .compose-title { font-size: 13px; font-weight: 600; color: #ccc; margin-bottom: 16px; }
  .field-row { display: flex; gap: 12px; margin-bottom: 12px; }
  .field { display: flex; flex-direction: column; gap: 6px; flex: 1; }
  .field label { font-size: 11px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
  .field input, .field select, .field textarea {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    color: #e8e8ed;
    font-size: 13px;
    padding: 9px 12px;
    outline: none;
    font-family: inherit;
    transition: border-color 0.15s;
  }
  .field input:focus, .field select:focus, .field textarea:focus {
    border-color: rgba(139,92,246,0.5);
  }
  .field textarea { resize: vertical; min-height: 70px; }
  .field select option { background: #1a1a1f; }
  .btn-generate {
    background: #7c3aed;
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, opacity 0.15s;
    display: flex; align-items: center; gap: 8px;
  }
  .btn-generate:hover { background: #6d28d9; }
  .btn-generate:disabled { opacity: 0.5; cursor: not-allowed; }

  /* ── Message card ── */
  .card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 18px;
    animation: slideIn 0.25s ease;
  }
  @keyframes slideIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: none; } }

  .card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
  .card-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px;
  }
  .card-sender { font-size: 13px; font-weight: 600; }
  .card-time { font-size: 11px; color: #555; margin-top: 1px; }
  .card-platform-badge {
    margin-left: auto;
    font-size: 10px; font-weight: 600;
    padding: 3px 8px; border-radius: 5px;
  }

  .bubble-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; color: #555; margin-bottom: 6px; }
  .bubble {
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 14px;
  }
  .bubble-incoming { background: rgba(255,255,255,0.06); color: #bbb; }
  .bubble-draft { background: rgba(139,92,246,0.12); border: 1px solid rgba(139,92,246,0.2); color: #e8e8ed; }
  .bubble-draft.editing { border-color: rgba(139,92,246,0.5); }

  .draft-header { display: flex; align-items: center; margin-bottom: 6px; }
  .draft-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; color: #a78bfa; }
  .btn-edit {
    margin-left: auto;
    background: none; border: none;
    color: #a78bfa; font-size: 11px; font-weight: 600;
    cursor: pointer; padding: 2px 6px; border-radius: 4px;
  }
  .btn-edit:hover { background: rgba(139,92,246,0.15); }

  .draft-text {
    font-size: 13px; line-height: 1.5; color: #e8e8ed;
    white-space: pre-wrap; word-break: break-word;
  }
  .draft-textarea {
    width: 100%;
    background: transparent;
    border: none;
    color: #e8e8ed;
    font-size: 13px;
    line-height: 1.5;
    font-family: inherit;
    outline: none;
    resize: none;
    min-height: 60px;
  }

  .card-actions { display: flex; gap: 10px; margin-top: 4px; align-items: center; }
  .btn-send {
    background: #7c3aed; color: white; border: none;
    border-radius: 8px; padding: 8px 18px;
    font-size: 13px; font-weight: 600; cursor: pointer;
    display: flex; align-items: center; gap: 6px;
    transition: background 0.15s;
  }
  .btn-send:hover { background: #6d28d9; }
  .btn-dismiss {
    background: rgba(255,255,255,0.05); color: #888; border: none;
    border-radius: 8px; padding: 8px 16px;
    font-size: 13px; cursor: pointer;
    transition: background 0.15s;
  }
  .btn-dismiss:hover { background: rgba(255,255,255,0.09); }
  .status-sent {
    margin-left: auto;
    font-size: 11px; font-weight: 600; color: #4ade80;
    display: flex; align-items: center; gap: 5px;
  }
  .imessage-hint { margin-left: auto; font-size: 11px; color: #444; }

  /* ── Spinner ── */
  .spinner {
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    display: inline-block;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .empty {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    color: #444; gap: 12px;
    text-align: center;
  }
  .empty-icon { font-size: 48px; opacity: 0.4; }
  .empty-text { font-size: 15px; }
  .empty-sub { font-size: 13px; color: #333; }

  .copy-toast {
    position: fixed; bottom: 24px; left: 50%;
    transform: translateX(-50%);
    background: #4ade80; color: #0a0a0a;
    font-size: 13px; font-weight: 600;
    padding: 10px 20px; border-radius: 20px;
    opacity: 0; transition: opacity 0.2s;
    pointer-events: none;
  }
  .copy-toast.show { opacity: 1; }
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="header-icon">👥</div>
  <div>
    <div class="header-title">AI Clone</div>
    <div class="header-sub">Respond to messages as you, powered by your memories</div>
  </div>
  <div class="header-badge">● Active</div>
</div>

<div class="main">
  <!-- Left panel -->
  <div class="panel">
    <div class="panel-label">Platforms</div>

    <div class="platform-row active" onclick="setPlatform('imessage', this)">
      <div class="platform-icon" style="background:rgba(74,222,128,0.15)">💬</div>
      <div>
        <div class="platform-name">iMessage</div>
        <div class="platform-status">Connected</div>
      </div>
      <div class="platform-dot dot-green"></div>
    </div>

    <div class="platform-row" onclick="setPlatform('telegram', this)">
      <div class="platform-icon" style="background:rgba(52,152,255,0.15)">✈️</div>
      <div>
        <div class="platform-name">Telegram</div>
        <div class="platform-status">Bot connected</div>
      </div>
      <div class="platform-dot dot-green"></div>
    </div>

    <div class="platform-row" style="opacity:0.4;cursor:default">
      <div class="platform-icon" style="background:rgba(74,222,128,0.1)">📱</div>
      <div>
        <div class="platform-name">WhatsApp</div>
        <div style="font-size:11px;color:#555">Coming soon</div>
      </div>
      <div class="platform-dot dot-grey"></div>
    </div>

    <hr class="divider">

    <div class="memories-box">
      <div class="memories-title">Your Memories</div>
      <div class="memories-item">Software engineer, AI enthusiast</div>
      <div class="memories-item">Casual, direct texting style</div>
      <div class="memories-item">Based in the US</div>
      <div class="memories-item">Into hackathons + building fast</div>
      <div style="margin-top:10px;font-size:11px;color:#444">
        Edit USER_MEMORIES in ai_clone_demo.py to personalize
      </div>
    </div>
  </div>

  <!-- Main feed -->
  <div class="feed" id="feed">
    <!-- Compose -->
    <div class="compose">
      <div class="compose-title">Simulate an incoming message</div>
      <div class="field-row">
        <div class="field">
          <label>From</label>
          <input id="sender" type="text" placeholder="e.g. Alex" value="Alex">
        </div>
        <div class="field">
          <label>Platform</label>
          <select id="platform">
            <option value="imessage">iMessage</option>
            <option value="telegram">Telegram</option>
            <option value="whatsapp">WhatsApp</option>
          </select>
        </div>
      </div>
      <div class="field" style="margin-bottom:14px">
        <label>Message</label>
        <textarea id="message" placeholder="e.g. Hey are you free this weekend?"></textarea>
      </div>
      <button class="btn-generate" id="genBtn" onclick="generateReply()">
        <span id="genBtnIcon">✨</span> Generate Reply
      </button>
    </div>

    <!-- Cards injected here -->
    <div id="cards"></div>
  </div>
</div>

<div class="copy-toast" id="toast">✓ Copied to clipboard</div>

<script>
let currentPlatform = 'imessage';
let cardCount = 0;

function setPlatform(p, el) {
  currentPlatform = p;
  document.querySelectorAll('.platform-row').forEach(r => r.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('platform').value = p;
}

const platformMeta = {
  imessage: { emoji: '💬', color: 'rgba(74,222,128,0.15)', label: 'iMessage', badge: '#1a3a2a', badgeColor: '#4ade80' },
  telegram: { emoji: '✈️', color: 'rgba(52,152,255,0.15)', label: 'Telegram', badge: '#1a2a3a', badgeColor: '#60a5fa' },
  whatsapp: { emoji: '📱', color: 'rgba(74,222,128,0.12)', label: 'WhatsApp', badge: '#1a3a22', badgeColor: '#4ade80' },
};

async function generateReply() {
  const sender = document.getElementById('sender').value.trim();
  const message = document.getElementById('message').value.trim();
  const platform = document.getElementById('platform').value;

  if (!sender || !message) {
    alert('Please fill in sender and message.');
    return;
  }

  const btn = document.getElementById('genBtn');
  const icon = document.getElementById('genBtnIcon');
  btn.disabled = true;
  icon.innerHTML = '<span class="spinner"></span>';

  let reply = '';
  try {
    const res = await fetch('/api/generate-reply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sender, message, platform }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    reply = data.reply;
  } catch (e) {
    alert('Error: ' + e.message);
    btn.disabled = false;
    icon.textContent = '✨';
    return;
  }

  btn.disabled = false;
  icon.textContent = '✨';

  const meta = platformMeta[platform] || platformMeta.imessage;
  const id = 'card-' + (++cardCount);
  const now = 'just now';

  const card = document.createElement('div');
  card.className = 'card';
  card.id = id;
  card.innerHTML = `
    <div class="card-header">
      <div class="card-avatar" style="background:${meta.color}">${meta.emoji}</div>
      <div>
        <div class="card-sender">${esc(sender)}</div>
        <div class="card-time">${now}</div>
      </div>
      <div class="card-platform-badge" style="background:${meta.badge};color:${meta.badgeColor}">
        ${meta.label}
      </div>
    </div>

    <div class="bubble-label">Received</div>
    <div class="bubble bubble-incoming">${esc(message)}</div>

    <div class="draft-header">
      <div class="draft-label">AI Draft</div>
      <button class="btn-edit" onclick="toggleEdit('${id}')">Edit</button>
    </div>
    <div class="bubble bubble-draft" id="${id}-bubble">
      <div class="draft-text" id="${id}-text">${esc(reply)}</div>
    </div>

    <div class="card-actions" id="${id}-actions">
      <button class="btn-send" onclick="handleSend('${id}', '${esc(platform)}')">
        ✉ Send
      </button>
      <button class="btn-dismiss" onclick="dismiss('${id}')">Dismiss</button>
      ${platform === 'imessage' ? '<div class="imessage-hint">💡 Copy & paste into Messages</div>' : ''}
    </div>
  `;

  const cardsEl = document.getElementById('cards');
  cardsEl.insertBefore(card, cardsEl.firstChild);

  // Clear form
  document.getElementById('message').value = '';
}

function toggleEdit(id) {
  const bubble = document.getElementById(id + '-bubble');
  const textEl = document.getElementById(id + '-text');
  const btn = bubble.parentElement.querySelector('.btn-edit');

  if (bubble.classList.contains('editing')) {
    // Save
    const ta = bubble.querySelector('textarea');
    textEl.textContent = ta.value;
    textEl.style.display = '';
    ta.remove();
    bubble.classList.remove('editing');
    btn.textContent = 'Edit';
  } else {
    // Edit mode
    const ta = document.createElement('textarea');
    ta.className = 'draft-textarea';
    ta.value = textEl.textContent;
    textEl.style.display = 'none';
    bubble.appendChild(ta);
    bubble.classList.add('editing');
    btn.textContent = 'Done';
    ta.focus();
  }
}

function handleSend(id, platform) {
  const textEl = document.getElementById(id + '-text');
  const text = textEl.textContent;

  if (platform === 'imessage') {
    navigator.clipboard.writeText(text).then(() => {
      showToast('✓ Copied — paste into Messages app');
    });
  } else {
    showToast('✓ Sent via ' + (platformMeta[platform]?.label || platform));
  }

  const actions = document.getElementById(id + '-actions');
  actions.innerHTML = '<div class="status-sent">✓ Sent</div>';
}

function dismiss(id) {
  const card = document.getElementById(id);
  card.style.opacity = '0';
  card.style.transition = 'opacity 0.2s';
  setTimeout(() => card.remove(), 200);
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("\n⚠  ANTHROPIC_API_KEY not set.")
        print("   Set it with:  set ANTHROPIC_API_KEY=sk-ant-...\n")
    else:
        print(f"\n✓  API key loaded ({key[:12]}...)")

    print("Starting AI Clone Demo at http://localhost:5050\n")
    app.run(port=5050, debug=False)
