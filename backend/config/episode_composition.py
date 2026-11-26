"""Episode wait repairs and opt-in transactional cleanup; read at each call boundary."""

from config.refactor_modes import default_off, default_on

EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED_ENV = 'EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED'
EPISODE_COMPOSE_ANCHORED_WAIT_ENABLED_ENV = 'EPISODE_COMPOSE_ANCHORED_WAIT_ENABLED'
EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED_ENV = 'EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED'
HOME_SETTLED_EMPTY_WIRE_ENABLED_ENV = 'HOME_SETTLED_EMPTY_WIRE_ENABLED'


def settled_terminal_enabled() -> bool:
    return default_on(EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED_ENV)


def anchored_wait_enabled() -> bool:
    return default_on(EPISODE_COMPOSE_ANCHORED_WAIT_ENABLED_ENV)


def empty_member_cleanup_enabled() -> bool:
    return default_off(EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED_ENV)


def legacy_empty_wire_enabled() -> bool:
    return default_on(HOME_SETTLED_EMPTY_WIRE_ENABLED_ENV)
