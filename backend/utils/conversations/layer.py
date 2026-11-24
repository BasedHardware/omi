"""Product by-id guard shared by readers outside the conversations router.

The supplied reader stays the owning database API, including injected test and
transaction clients. Recordings remain available to explicitly raw pipelines.
"""

from database.recording_transcript_publication import RESOLVED_RECORDING_ID


def read_product(reader, *args, include_published_recording=False, **kwargs):
    if kwargs.get('field_paths') is not None:
        fields = list(kwargs['field_paths'])
        kwargs['field_paths'] = fields if 'recording' in fields else [*fields, 'recording']
    row = reader(*args, **kwargs)
    if row and row.get('recording') and not (include_published_recording and row.get(RESOLVED_RECORDING_ID)):
        return None
    return row
