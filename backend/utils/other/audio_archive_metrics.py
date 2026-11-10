from prometheus_client import Counter

ARCHIVE_OBJECTS = Counter(
    'omi_audio_archive_objects_total', 'New immutable canonical audio objects', ['source', 'codec']
)
ARCHIVE_BYTES = Counter('omi_audio_archive_bytes_total', 'Canonical plaintext capture bytes', ['source', 'codec'])
PCM_WRITES_AVOIDED = Counter(
    'omi_audio_archive_pcm_writes_avoided_total', 'PCM batches covered by verified canonical raw'
)
REBUILDS_COALESCED = Counter(
    'omi_audio_archive_rebuilds_coalesced_total', 'Concurrent rebuild calls sharing one result'
)
