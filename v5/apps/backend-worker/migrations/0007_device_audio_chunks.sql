CREATE TABLE device_audio_chunks (
  session_id TEXT NOT NULL REFERENCES device_sessions(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0 AND chunk_index < 65536),
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 1048576),
  uploaded INTEGER NOT NULL DEFAULT 0 CHECK (uploaded IN (0, 1)),
  PRIMARY KEY (session_id, chunk_index)
);
CREATE TRIGGER device_audio_chunk_claimed
AFTER INSERT ON device_audio_chunks
BEGIN
  UPDATE device_sessions
  SET chunk_count = chunk_count + 1, byte_count = byte_count + NEW.size_bytes
  WHERE id = NEW.session_id;
END;
CREATE TRIGGER device_audio_chunk_uploaded
AFTER UPDATE OF uploaded ON device_audio_chunks
WHEN OLD.uploaded = 0 AND NEW.uploaded = 1
BEGIN
  UPDATE device_sessions
  SET uploaded_chunk_count = uploaded_chunk_count + 1
  WHERE id = NEW.session_id;
END;
