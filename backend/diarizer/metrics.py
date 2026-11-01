from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter('omi_diarization_v2_total', 'Diarization requests', ['outcome'])
AUDIO = Counter('omi_diarization_v2_audio_seconds_total', 'Successfully diarized audio')
RTF = Histogram(
    'omi_diarization_v2_rtf', 'Inference seconds per audio second', buckets=(0.01, 0.05, 0.1, 0.2, 0.5, 1, 2)
)
DEPTH = Gauge('omi_diarization_v2_queue_depth', 'Admitted uploads and inference jobs')
GPU_MEMORY = Gauge('omi_diarization_v2_gpu_memory_bytes', 'Peak CUDA allocated memory per request')
