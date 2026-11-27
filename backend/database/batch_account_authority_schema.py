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
