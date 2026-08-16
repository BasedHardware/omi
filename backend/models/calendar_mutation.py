from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

CalendarEvent = dict[str, object]


@dataclass
class CalendarMutationResult:
    succeeded: list[CalendarEvent] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])


def event_title(event: CalendarEvent) -> str:
    summary = event.get('summary', 'Untitled')
    if isinstance(summary, str):
        return summary
    return str(summary)


def format_deleted_calendar_events(result: CalendarMutationResult) -> str:
    if result.succeeded:
        message = f"✅ Successfully deleted {len(result.succeeded)} calendar event(s):\n"
        for event in result.succeeded:
            summary = event_title(event)
            start = event.get('start', {})
            if isinstance(start, dict) and 'dateTime' in start:
                start_data = cast(dict[object, object], start)
                date_time = start_data['dateTime']
                if not isinstance(date_time, str):
                    message += f"   - {summary}\n"
                    continue
                try:
                    start_dt = datetime.fromisoformat(date_time.replace('Z', '+00:00'))
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
