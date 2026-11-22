SELECT route,
       COUNT(*) AS sessions,
       SUM(audio_ms) AS audio_ms,
       SUM(segment_count) AS segment_count
FROM events
WHERE app_namespace = :app_namespace AND build_number = :build_number
  AND event = 'On Device Transcription Used'
GROUP BY route;
