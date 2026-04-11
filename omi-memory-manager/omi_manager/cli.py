"""CLI entry point for Omi Memory Manager."""

import click

from omi_manager.client import OmiClient
from omi_manager.config import save_config, get_config
from omi_manager.display import (
    console,
    show_conversations_table,
    show_conversation_detail,
    show_memories_table,
    show_memory_detail,
    show_success,
    show_task_detail,
    show_tasks_table,
)


def _client() -> OmiClient:
    return OmiClient()


# ── Root ─────────────────────────────────────────────────


@click.group()
@click.version_option(package_name="omi-memory-manager")
def main():
    """Omi Memory Manager - manage tasks, memories, and conversations."""


# ── Configure ────────────────────────────────────────────


@main.command()
@click.option("--api-key", prompt="Omi Developer API Key", help="Your omi_dev_* API key")
@click.option("--base-url", default=None, help="API base URL (default: https://api.omi.me)")
def configure(api_key: str, base_url: str):
    """Save API credentials locally."""
    config = get_config()
    config["api_key"] = api_key.strip()
    if base_url:
        config["base_url"] = base_url.strip()
    save_config(config)
    show_success("Configuration saved to ~/.omi-manager/config.json")


# ══════════════════════════════════════════════════════════
#  MEMORIES
# ══════════════════════════════════════════════════════════


@main.group()
def memories():
    """Manage memories (facts the AI learned about you)."""


@memories.command("list")
@click.option("--limit", "-n", default=25, help="Max results")
@click.option("--offset", "-o", default=0, help="Skip N results")
@click.option("--category", "-c", default=None, help="Filter by category (interesting, system, manual)")
def memories_list(limit, offset, category):
    """List your memories."""
    data = _client().list_memories(limit=limit, offset=offset, categories=category)
    show_memories_table(data)


@memories.command("create")
@click.argument("content")
@click.option("--category", "-c", default=None, help="Category: interesting, system, manual")
@click.option("--visibility", "-v", default="private", help="public or private")
@click.option("--tag", "-t", multiple=True, help="Tags (repeatable)")
def memories_create(content, category, visibility, tag):
    """Create a new memory."""
    result = _client().create_memory(content, category=category, visibility=visibility, tags=list(tag))
    show_success("Memory created!")
    show_memory_detail(result)


@memories.command("edit")
@click.argument("memory_id")
@click.option("--content", "-c", default=None, help="New content")
@click.option("--visibility", "-v", default=None, help="public or private")
@click.option("--category", default=None, help="New category")
@click.option("--tag", "-t", multiple=True, help="Replace tags (repeatable)")
def memories_edit(memory_id, content, visibility, category, tag):
    """Edit an existing memory."""
    tags = list(tag) if tag else None
    result = _client().update_memory(memory_id, content=content, visibility=visibility, tags=tags, category=category)
    show_success("Memory updated!")
    show_memory_detail(result)


@memories.command("delete")
@click.argument("memory_id")
@click.confirmation_option(prompt="Are you sure you want to delete this memory?")
def memories_delete(memory_id):
    """Delete a memory by ID."""
    _client().delete_memory(memory_id)
    show_success(f"Memory {memory_id} deleted.")


@memories.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=25, help="Max results")
def memories_search(query, limit):
    """Search memories by content (client-side filter)."""
    data = _client().list_memories(limit=100)
    query_lower = query.lower()
    filtered = [m for m in data if query_lower in m.get("content", "").lower() or query_lower in " ".join(m.get("tags", [])).lower()]
    show_memories_table(filtered[:limit])
    console.print(f"[dim]Showing {min(len(filtered), limit)} of {len(filtered)} matches.[/dim]")


# ══════════════════════════════════════════════════════════
#  TASKS (Action Items)
# ══════════════════════════════════════════════════════════


@main.group()
def tasks():
    """Manage tasks (action items / to-dos)."""


@tasks.command("list")
@click.option("--limit", "-n", default=100, help="Max results")
@click.option("--offset", "-o", default=0, help="Skip N results")
@click.option("--pending", "status", flag_value="pending", help="Show only pending tasks")
@click.option("--done", "status", flag_value="done", help="Show only completed tasks")
@click.option("--all", "status", flag_value="all", default=True, help="Show all tasks (default)")
def tasks_list(limit, offset, status):
    """List your tasks."""
    completed = None
    if status == "pending":
        completed = False
    elif status == "done":
        completed = True
    data = _client().list_action_items(completed=completed, limit=limit, offset=offset)
    show_tasks_table(data)


@tasks.command("create")
@click.argument("description")
@click.option("--due", "-d", default=None, help="Due date in ISO format (e.g. 2025-12-31T23:59:00+00:00)")
def tasks_create(description, due):
    """Create a new task."""
    result = _client().create_action_item(description, due_at=due)
    show_success("Task created!")
    show_task_detail(result)


@tasks.command("edit")
@click.argument("task_id")
@click.option("--description", "-d", default=None, help="New description")
@click.option("--due", default=None, help="New due date (ISO format)")
def tasks_edit(task_id, description, due):
    """Edit a task description or due date."""
    result = _client().update_action_item(task_id, description=description, due_at=due)
    show_success("Task updated!")
    show_task_detail(result)


@tasks.command("complete")
@click.argument("task_id")
def tasks_complete(task_id):
    """Mark a task as completed."""
    result = _client().update_action_item(task_id, completed=True)
    show_success("Task marked as completed!")
    show_task_detail(result)


@tasks.command("reopen")
@click.argument("task_id")
def tasks_reopen(task_id):
    """Reopen a completed task."""
    result = _client().update_action_item(task_id, completed=False)
    show_success("Task reopened!")
    show_task_detail(result)


@tasks.command("delete")
@click.argument("task_id")
@click.confirmation_option(prompt="Are you sure you want to delete this task?")
def tasks_delete(task_id):
    """Delete a task by ID."""
    _client().delete_action_item(task_id)
    show_success(f"Task {task_id} deleted.")


@tasks.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=100, help="Max results")
def tasks_search(query, limit):
    """Search tasks by description (client-side filter)."""
    data = _client().list_action_items(limit=200)
    query_lower = query.lower()
    filtered = [t for t in data if query_lower in t.get("description", "").lower()]
    show_tasks_table(filtered[:limit])
    console.print(f"[dim]Showing {min(len(filtered), limit)} of {len(filtered)} matches.[/dim]")


# ══════════════════════════════════════════════════════════
#  CONVERSATIONS
# ══════════════════════════════════════════════════════════


@main.group()
def conversations():
    """Manage conversations."""


@conversations.command("list")
@click.option("--limit", "-n", default=25, help="Max results")
@click.option("--offset", "-o", default=0, help="Skip N results")
def conversations_list(limit, offset):
    """List your conversations."""
    data = _client().list_conversations(limit=limit, offset=offset)
    show_conversations_table(data)


@conversations.command("get")
@click.argument("conversation_id")
def conversations_get(conversation_id):
    """View a conversation in detail."""
    data = _client().get_conversation(conversation_id)
    show_conversation_detail(data)


@conversations.command("create")
@click.argument("text")
@click.option("--source", "-s", default="other", help="Source: audio_transcript, message, other")
@click.option("--language", "-l", default="en", help="Language code (e.g. en, pt, es)")
def conversations_create(text, source, language):
    """Create a conversation from text."""
    result = _client().create_conversation(text, text_source=source, language=language)
    show_success("Conversation created!")
    console.print(f"ID: {result.get('id', 'N/A')}")


@conversations.command("delete")
@click.argument("conversation_id")
@click.confirmation_option(prompt="Are you sure you want to delete this conversation?")
def conversations_delete(conversation_id):
    """Delete a conversation by ID."""
    _client().delete_conversation(conversation_id)
    show_success(f"Conversation {conversation_id} deleted.")


@conversations.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=25, help="Max results")
def conversations_search(query, limit):
    """Search conversations by title or overview (client-side filter)."""
    data = _client().list_conversations(limit=100)
    query_lower = query.lower()
    filtered = []
    for c in data:
        s = c.get("structured", {})
        text = f"{s.get('title', '')} {s.get('overview', '')}".lower()
        if query_lower in text:
            filtered.append(c)
    show_conversations_table(filtered[:limit])
    console.print(f"[dim]Showing {min(len(filtered), limit)} of {len(filtered)} matches.[/dim]")


# ══════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════


@main.command()
@click.option("--limit", "-n", default=5, help="Items per section")
def dashboard(limit):
    """Show a quick overview of recent data."""
    client = _client()
    console.rule("[bold blue]Omi Dashboard[/bold blue]")

    console.print("\n[bold]Recent Memories[/bold]")
    show_memories_table(client.list_memories(limit=limit))

    console.print("\n[bold]Pending Tasks[/bold]")
    show_tasks_table(client.list_action_items(completed=False, limit=limit))

    console.print("\n[bold]Recent Conversations[/bold]")
    show_conversations_table(client.list_conversations(limit=limit))


if __name__ == "__main__":
    main()
