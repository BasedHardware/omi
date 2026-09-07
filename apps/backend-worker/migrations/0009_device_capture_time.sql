ALTER TABLE device_sessions ADD COLUMN captured_at_ms INTEGER
CHECK(captured_at_ms IS NULL OR (typeof(captured_at_ms)='integer' AND captured_at_ms>=0 AND captured_at_ms<=8640000000000000));
