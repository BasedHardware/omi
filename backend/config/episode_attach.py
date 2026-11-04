"""Ship-on rollback controls for sync episode work; evaluated at each call."""

import os


def content_gate_enabled():
    return os.getenv('EPISODE_ATTACH_CONTENT_GATE_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def noop_schedule_enabled():
    return os.getenv('EPISODE_ATTACH_NOOP_SCHEDULE_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def owner_reuse_enabled():
    return os.getenv('EPISODE_ATTACH_OWNER_REUSE_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def membership_dedupe_enabled():
    return os.getenv('EPISODE_ATTACH_MEMBERSHIP_DEDUPE_ENABLED', 'true').strip().lower() not in {
        'false',
        'off',
        '0',
        'no',
    }


def row_visibility_enabled():
    return os.getenv('EPISODE_ATTACH_ROW_VISIBILITY_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def walk_context_enabled():
    return os.getenv('EPISODE_ATTACH_WALK_CONTEXT_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def duplicates_dedupe_enabled():
    return os.getenv('EPISODE_ATTACH_DUPLICATES_DEDUPE_ENABLED', 'true').strip().lower() not in {
        'false',
        'off',
        '0',
        'no',
    }
