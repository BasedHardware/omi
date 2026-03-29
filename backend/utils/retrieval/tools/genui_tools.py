"""
Tools for creating generative UI blocks in chat responses.

These tools allow the LLM to render rich, interactive UI components inline
in chat messages — maps, cards, buttons, images, and more — using the A2UI
protocol consumed by Flutter's genui package on the client.
"""

from typing import List, Optional

from langchain_core.tools import tool

from utils.retrieval.context import agent_config_context


def _store_ui_blocks(blocks: list):
    """Append UI blocks to the agent config for the current request."""
    try:
        config = agent_config_context.get()
    except LookupError:
        config = None

    if config:
        configurable = config.get('configurable', {})
        existing = configurable.setdefault('ui_blocks', [])
        existing.extend(blocks)


@tool
def create_map_ui(
    latitude: float,
    longitude: float,
    title: str,
    description: Optional[str] = None,
    zoom: int = 15,
) -> str:
    """
    Show an interactive map card inline in the chat response.

    Use this tool when the user asks about locations, directions, places, or
    "where" questions. The map will render as a tappable card that opens the
    native maps app.

    IMPORTANT: Only call this tool when you have ACTUAL coordinates from
    retrieved data (conversation geolocation, calendar event location, etc.).
    Do NOT guess or make up coordinates.

    Args:
        latitude: Latitude of the location (e.g. 37.7749)
        longitude: Longitude of the location (e.g. -122.4194)
        title: Location name displayed above the map (e.g. "Starbucks Reserve")
        description: Optional address or details below the map
        zoom: Map zoom level, 1-20 (default 15, good for street-level)

    Returns:
        Confirmation that the map will be displayed inline.
    """
    if not (-90 <= latitude <= 90):
        return "Error: latitude must be between -90 and 90."
    if not (-180 <= longitude <= 180):
        return "Error: longitude must be between -180 and 180."
    if not (1 <= zoom <= 20):
        zoom = 15

    block = {
        "type": "map",
        "props": {
            "latitude": latitude,
            "longitude": longitude,
            "title": title,
            "description": description,
            "zoom": zoom,
        },
    }

    _store_ui_blocks([block])

    return f"Map displayed: {title} ({latitude}, {longitude}). The map card will appear inline in the chat."


@tool
def create_action_buttons_ui(
    buttons: List[str],
    title: Optional[str] = None,
) -> str:
    """
    Show a set of tappable action buttons inline in the chat response.

    Use this tool when you want to offer the user quick follow-up options,
    such as suggested next questions or actions they can take.

    Args:
        buttons: List of button labels (1-5 buttons). Each button sends its
                 label text as a follow-up message when tapped.
        title: Optional header text above the buttons.

    Returns:
        Confirmation that the buttons will be displayed.
    """
    if not buttons or len(buttons) == 0:
        return "Error: at least one button is required."
    if len(buttons) > 5:
        buttons = buttons[:5]

    block = {
        "type": "action_buttons",
        "props": {
            "title": title,
            "buttons": buttons,
        },
    }

    _store_ui_blocks([block])

    labels = ", ".join(f'"{b}"' for b in buttons)
    return f"Action buttons displayed: {labels}. The user can tap any button to send that as a message."
