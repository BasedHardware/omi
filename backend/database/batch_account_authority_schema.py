"""Account authority paths and field roots shared by writers and Commit observers."""

USER_COLLECTION = 'users'
ACCOUNT_DELETION_COLLECTION = 'account_deletions'
PRIVACY_COLLECTION = 'batch_pipeline_privacy'
ACCOUNT_EPOCH = 'account_epoch'
ACCOUNT_STATE_COLLECTION = 'account_authority'
ACCOUNT_HEAD = 'head'
ACCOUNT_OPERATIONS = 'account_operations'
SPEAKER_PRIVACY_VERSION = 'speaker_auto_enroll_privacy_version'

ACCOUNT_FIELD_GROUPS = {
    USER_COLLECTION: {
        'data_protection_level': 'protection',
        'migration_status': 'protection',
        'private_cloud_sync_enabled': 'cloud_sync',
    },
    ACCOUNT_DELETION_COLLECTION: {
        'wipe_status': 'deletion',
        'wipe_auth_deleted_at': 'deletion',
    },
}
USER_POLICY_FIELDS = frozenset(ACCOUNT_FIELD_GROUPS[USER_COLLECTION]) | {
    SPEAKER_PRIVACY_VERSION,
    'store_recording_permission',
}


def data_protection_denies(data: dict) -> bool:
    return (
        data.get('data_protection_level', 'enhanced') not in ('standard', 'enhanced')
        or data.get('migration_status') is not None
    )


def account_recording_policy_denies(data: dict) -> bool:
    return not data.get('private_cloud_sync_enabled', True)


def recording_policy_denies(conversation: dict, user_sync_enabled: bool = True) -> bool:
    return conversation.get('record_lane_owner') == 'batch_live_v1' and (
        bool(conversation.get('uses_custom_stt'))
        or not conversation.get('private_cloud_sync_enabled')
        or not user_sync_enabled
    )
