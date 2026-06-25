from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CalendarMutationResult:
    succeeded: list[dict] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def event_title(event: dict) -> str:
    return event.get('summary', 'Untitled')


def format_deleted_calendar_events(result: CalendarMutationResult) -> str:
    if result.succeeded:
        message = f"✅ Successfully deleted {len(result.succeeded)} calendar event(s):\n"
        for event in result.succeeded:
            summary = event_title(event)
            start = event.get('start', {})
            if 'dateTime' in start:
                try:
                    start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                    message += f"   - {summary} ({start_dt.strftime('%Y-%m-%d %H:%M')})\n"
                except ValueError:
                    message += f"   - {summary}\n"
            else:
                message += f"   - {summary}\n"

        if result.failed:
            message += f"\n⚠️ Failed to delete {len(result.failed)} event(s):\n"
            for title, error in result.failed:
                message += f"   - {title}: {error}\n"
        return message.strip()

    if result.failed:
        error_msgs = '; '.join([f"{title}: {error}" for title, error in result.failed])
        return f"Error: Failed to delete events: {error_msgs}"
    return "No events were deleted."
