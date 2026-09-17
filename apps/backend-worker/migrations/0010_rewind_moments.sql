CREATE TABLE rewind_moments (
  account_id TEXT NOT NULL,
  frame_id TEXT NOT NULL,
  captured_at_ms INTEGER NOT NULL
    CHECK(typeof(captured_at_ms)='integer' AND captured_at_ms>=0 AND captured_at_ms<=8640000000000000),
  app_name TEXT NOT NULL CHECK(length(app_name) BETWEEN 1 AND 256),
  window_title TEXT NOT NULL CHECK(length(window_title) <= 1024),
  source TEXT NOT NULL CHECK(source IN ('captured', 'shipping')),
  ocr_preview TEXT NOT NULL CHECK(length(ocr_preview) <= 240),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (account_id, frame_id)
);
CREATE INDEX rewind_moments_account_time ON rewind_moments (account_id, captured_at_ms DESC, frame_id DESC);
