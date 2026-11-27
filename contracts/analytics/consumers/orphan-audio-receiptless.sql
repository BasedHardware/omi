SELECT event, COUNT(*)
FROM events
WHERE app_namespace = :app_namespace
  AND build_number = :build_number
  AND event = 'Orphan Audio Receiptless Custody'
  AND receipt_scan_truncated = 'false'
  AND census_complete = 'true'
GROUP BY event;
