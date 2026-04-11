"""Rich terminal display helpers for Omi Memory Manager."""

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def format_dt(value) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return value
    return value.strftime("%Y-%m-%d %H:%M")


# ── Memories ─────────────────────────────────────────────


def show_memories_table(memories: list):
    if not memories:
        console.print("[yellow]No memories found.[/yellow]")
        return
    table = Table(title="Memories", show_lines=True)
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Content", min_width=30)
    table.add_column("Category", style="cyan")
    table.add_column("Visibility", style="green")
    table.add_column("Tags")
    table.add_column("Created", style="dim")
    for m in memories:
        table.add_row(
            m.get("id", "")[:12],
            m.get("content", ""),
            m.get("category", ""),
            m.get("visibility", ""),
            ", ".join(m.get("tags", [])) or "-",
            format_dt(m.get("created_at")),
        )
    console.print(table)


def show_memory_detail(m: dict):
    content = Text(m.get("content", ""))
    meta = (
        f"ID:         {m.get('id', '')}\n"
        f"Category:   {m.get('category', '')}\n"
        f"Visibility: {m.get('visibility', '')}\n"
        f"Tags:       {', '.join(m.get('tags', [])) or '-'}\n"
        f"Created:    {format_dt(m.get('created_at'))}\n"
        f"Updated:    {format_dt(m.get('updated_at'))}"
    )
    console.print(Panel(content, title="Memory", subtitle=meta, border_style="blue"))


# ── Action Items (Tasks) ─────────────────────────────────


def show_tasks_table(items: list):
    if not items:
        console.print("[yellow]No tasks found.[/yellow]")
        return
    table = Table(title="Tasks (Action Items)", show_lines=True)
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Description", min_width=30)
    table.add_column("Status")
    table.add_column("Due", style="magenta")
    table.add_column("Created", style="dim")
    for item in items:
        done = item.get("completed", False)
        status = Text("[done]", style="green bold") if done else Text("[pending]", style="yellow")
        table.add_row(
            item.get("id", "")[:12],
            item.get("description", ""),
            status,
            format_dt(item.get("due_at")),
            format_dt(item.get("created_at")),
        )
    console.print(table)


def show_task_detail(item: dict):
    done = item.get("completed", False)
    status = "[green]Completed[/green]" if done else "[yellow]Pending[/yellow]"
    meta = (
        f"ID:          {item.get('id', '')}\n"
        f"Status:      {status}\n"
        f"Due:         {format_dt(item.get('due_at'))}\n"
        f"Completed:   {format_dt(item.get('completed_at'))}\n"
        f"Created:     {format_dt(item.get('created_at'))}\n"
        f"Updated:     {format_dt(item.get('updated_at'))}\n"
        f"Conversation: {item.get('conversation_id') or '-'}"
    )
    console.print(Panel(item.get("description", ""), title="Task", subtitle=meta, border_style="magenta"))


# ── Conversations ────────────────────────────────────────


def show_conversations_table(conversations: list):
    if not conversations:
        console.print("[yellow]No conversations found.[/yellow]")
        return
    table = Table(title="Conversations", show_lines=True)
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Title", min_width=25)
    table.add_column("Category", style="cyan")
    table.add_column("Overview", max_width=50)
    table.add_column("Created", style="dim")
    for c in conversations:
        structured = c.get("structured", {})
        table.add_row(
            c.get("id", "")[:12],
            structured.get("title", ""),
            structured.get("category", ""),
            (structured.get("overview", "") or "")[:80],
            format_dt(c.get("created_at")),
        )
    console.print(table)


def show_conversation_detail(c: dict):
    structured = c.get("structured", {})
    title = structured.get("title", "Untitled")
    overview = structured.get("overview", "")
    emoji = structured.get("emoji", "")
    category = structured.get("category", "")

    # Build transcript text
    segments = c.get("transcript_segments") or []
    transcript_lines = []
    for seg in segments:
        speaker = seg.get("speaker_name") or f"Speaker {seg.get('speaker_id', '?')}"
        transcript_lines.append(f"  {speaker}: {seg.get('text', '')}")
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no transcript)"

    # Action items from structured
    action_items = structured.get("action_items", [])
    ai_text = ""
    if action_items:
        ai_text = "\n\nAction Items:\n"
        for ai in action_items:
            check = "[x]" if ai.get("completed") else "[ ]"
            ai_text += f"  {check} {ai.get('description', '')}\n"

    body = f"{overview}\n\nTranscript:\n{transcript}{ai_text}"

    meta = (
        f"ID:       {c.get('id', '')}\n"
        f"Category: {category}\n"
        f"Emoji:    {emoji}\n"
        f"Source:   {c.get('source', '')}\n"
        f"Created:  {format_dt(c.get('created_at'))}\n"
        f"Started:  {format_dt(c.get('started_at'))}\n"
        f"Finished: {format_dt(c.get('finished_at'))}"
    )
    console.print(Panel(body, title=f"Conversation: {title}", subtitle=meta, border_style="green"))


# ── Generic ──────────────────────────────────────────────


def show_success(message: str):
    console.print(f"[green bold]{message}[/green bold]")


def show_error(message: str):
    console.print(f"[red bold]Error: {message}[/red bold]")
