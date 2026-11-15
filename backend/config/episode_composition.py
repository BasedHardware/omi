"""Default-on bug repairs to closed episode composition; read at each call boundary."""

from config.refactor_modes import default_on


def settled_terminal_enabled() -> bool:
    return default_on('EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED')
