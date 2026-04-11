"""Flask web application for Omi Memory Manager."""

from flask import Flask, render_template, request, jsonify, redirect, url_for

from omi_manager.client import OmiClient

app = Flask(__name__)


def _client() -> OmiClient:
    return OmiClient()


# ── Dashboard ────────────────────────────────────────────


@app.route("/")
def dashboard():
    client = _client()
    errors = {}
    memories = []
    tasks = []
    conversations = []
    try:
        memories = client.list_memories(limit=5)
    except Exception as e:
        errors["memories"] = str(e)
    try:
        tasks = client.list_action_items(completed=False, limit=5)
    except Exception as e:
        errors["tasks"] = str(e)
    try:
        conversations = client.list_conversations(limit=5)
    except Exception as e:
        errors["conversations"] = str(e)
    return render_template("dashboard.html", memories=memories, tasks=tasks, conversations=conversations, errors=errors)


# ══════════════════════════════════════════════════════════
#  MEMORIES
# ══════════════════════════════════════════════════════════


@app.route("/memories")
def memories_page():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    client = _client()
    data = client.list_memories(limit=200, categories=category or None)
    if q:
        q_lower = q.lower()
        data = [m for m in data if q_lower in m.get("content", "").lower() or q_lower in " ".join(m.get("tags", [])).lower()]
    return render_template("memories.html", memories=data, query=q, category=category)


@app.route("/memories/create", methods=["POST"])
def memories_create():
    content = request.form.get("content", "").strip()
    category = request.form.get("category", "") or None
    visibility = request.form.get("visibility", "private")
    tags_raw = request.form.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    if not content:
        return redirect(url_for("memories_page"))
    _client().create_memory(content, category=category, visibility=visibility, tags=tags)
    return redirect(url_for("memories_page"))


@app.route("/memories/<memory_id>/edit", methods=["POST"])
def memories_edit(memory_id):
    content = request.form.get("content")
    visibility = request.form.get("visibility")
    category = request.form.get("category") or None
    _client().update_memory(memory_id, content=content, visibility=visibility, category=category)
    return redirect(url_for("memories_page"))


@app.route("/memories/<memory_id>/delete", methods=["POST"])
def memories_delete(memory_id):
    _client().delete_memory(memory_id)
    return redirect(url_for("memories_page"))


@app.route("/api/memories/bulk-delete", methods=["POST"])
def memories_bulk_delete():
    ids = request.json.get("ids", [])
    client = _client()
    deleted = 0
    errors = []
    for mid in ids:
        try:
            client.delete_memory(mid)
            deleted += 1
        except Exception as e:
            errors.append({"id": mid, "error": str(e)})
    return jsonify({"deleted": deleted, "errors": errors})


# ══════════════════════════════════════════════════════════
#  TASKS
# ══════════════════════════════════════════════════════════


@app.route("/tasks")
def tasks_page():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    client = _client()
    completed = None
    if status == "pending":
        completed = False
    elif status == "done":
        completed = True
    data = client.list_action_items(completed=completed, limit=200)
    if q:
        q_lower = q.lower()
        data = [t for t in data if q_lower in t.get("description", "").lower()]
    return render_template("tasks.html", tasks=data, query=q, status=status)


@app.route("/tasks/create", methods=["POST"])
def tasks_create():
    description = request.form.get("description", "").strip()
    due_at = request.form.get("due_at", "").strip() or None
    if not description:
        return redirect(url_for("tasks_page"))
    if due_at:
        due_at = due_at + ":00+00:00" if len(due_at) == 16 else due_at
    _client().create_action_item(description, due_at=due_at)
    return redirect(url_for("tasks_page"))


@app.route("/tasks/<task_id>/edit", methods=["POST"])
def tasks_edit(task_id):
    description = request.form.get("description")
    due_at = request.form.get("due_at", "").strip() or None
    if due_at:
        due_at = due_at + ":00+00:00" if len(due_at) == 16 else due_at
    _client().update_action_item(task_id, description=description, due_at=due_at)
    return redirect(url_for("tasks_page"))


@app.route("/tasks/<task_id>/toggle", methods=["POST"])
def tasks_toggle(task_id):
    completed = request.form.get("completed") == "true"
    _client().update_action_item(task_id, completed=completed)
    return redirect(url_for("tasks_page"))


@app.route("/tasks/<task_id>/delete", methods=["POST"])
def tasks_delete(task_id):
    _client().delete_action_item(task_id)
    return redirect(url_for("tasks_page"))


@app.route("/api/tasks/bulk-delete", methods=["POST"])
def tasks_bulk_delete():
    ids = request.json.get("ids", [])
    client = _client()
    deleted = 0
    errors = []
    for tid in ids:
        try:
            client.delete_action_item(tid)
            deleted += 1
        except Exception as e:
            errors.append({"id": tid, "error": str(e)})
    return jsonify({"deleted": deleted, "errors": errors})


@app.route("/api/tasks/bulk-complete", methods=["POST"])
def tasks_bulk_complete():
    ids = request.json.get("ids", [])
    client = _client()
    updated = 0
    errors = []
    for tid in ids:
        try:
            client.update_action_item(tid, completed=True)
            updated += 1
        except Exception as e:
            errors.append({"id": tid, "error": str(e)})
    return jsonify({"updated": updated, "errors": errors})


# ══════════════════════════════════════════════════════════
#  CONVERSATIONS
# ══════════════════════════════════════════════════════════


@app.route("/conversations")
def conversations_page():
    q = request.args.get("q", "").strip()
    client = _client()
    data = client.list_conversations(limit=200)
    if q:
        q_lower = q.lower()
        filtered = []
        for c in data:
            s = c.get("structured", {})
            text = f"{s.get('title', '')} {s.get('overview', '')}".lower()
            if q_lower in text:
                filtered.append(c)
        data = filtered
    return render_template("conversations.html", conversations=data, query=q)


@app.route("/conversations/<conversation_id>")
def conversations_detail(conversation_id):
    data = _client().get_conversation(conversation_id)
    return render_template("conversation_detail.html", conversation=data)


@app.route("/conversations/create", methods=["POST"])
def conversations_create():
    text = request.form.get("text", "").strip()
    language = request.form.get("language", "en")
    if not text:
        return redirect(url_for("conversations_page"))
    _client().create_conversation(text, language=language)
    return redirect(url_for("conversations_page"))


@app.route("/conversations/<conversation_id>/delete", methods=["POST"])
def conversations_delete(conversation_id):
    _client().delete_conversation(conversation_id)
    return redirect(url_for("conversations_page"))


@app.route("/api/conversations/bulk-delete", methods=["POST"])
def conversations_bulk_delete():
    ids = request.json.get("ids", [])
    client = _client()
    deleted = 0
    errors = []
    for cid in ids:
        try:
            client.delete_conversation(cid)
            deleted += 1
        except Exception as e:
            errors.append({"id": cid, "error": str(e)})
    return jsonify({"deleted": deleted, "errors": errors})


def run_web(host="127.0.0.1", port=5050, debug=False):
    app.run(host=host, port=port, debug=debug)
