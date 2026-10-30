"""An operator repair silences derived effects only for the revision it wrote."""


def is_silent_redrive(row):
    revision = row.get('sync_content_revision')
    return (
        type(revision) is int
        and revision > 0
        and type(row.get('sync_silent_redrive_revision')) is int
        and row['sync_silent_redrive_revision'] == revision
    )
