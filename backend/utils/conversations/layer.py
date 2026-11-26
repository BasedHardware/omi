"""Product by-id guard shared by readers outside the conversations router.

The supplied reader stays the owning database API, including injected test and
transaction clients. Recordings remain available to explicitly raw pipelines.
"""


def read_product(reader, *args, **kwargs):
    if kwargs.get('field_paths') is not None:
        fields = list(kwargs['field_paths'])
        kwargs['field_paths'] = fields if 'recording' in fields else [*fields, 'recording']
    row = reader(*args, **kwargs)
    return None if row and row.get('recording') else row
