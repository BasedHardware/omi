export interface D1MigrationManifestEntry {
  readonly version: number;
  readonly name: string;
  readonly fileName: string;
  readonly sha256: string;
}

export const D1_MIGRATIONS: readonly D1MigrationManifestEntry[] = Object.freeze(
  [
    Object.freeze({
      version: 1,
      name: "0001_tasks.sql",
      fileName: "0001_tasks.sql",
      sha256:
        "e9b4df967b8becc1406c35b5cfed4f893b4b0640cd0daa58ab37255e93fe12d1",
    }),
    Object.freeze({
      version: 2,
      name: "0002_chat.sql",
      fileName: "0002_chat.sql",
      sha256:
        "f1b3da76a9d949198e066af5320d2b684e32ecc4112896e8cd2ffdad75a824d1",
    }),
    Object.freeze({
      version: 3,
      name: "0003_attachments.sql",
      fileName: "0003_attachments.sql",
      sha256:
        "ee4efd8d61929ba0155753de9b6c5784f657b6264b90964c1c6dd34d9fc98fa3",
    }),
    Object.freeze({
      version: 4,
      name: "0004_device_sessions.sql",
      fileName: "0004_device_sessions.sql",
      sha256:
        "51989ee2f63cfc36614b56cf8ca6433a41441004109ab3aa38ead02f9a2e580e",
    }),
    Object.freeze({
      version: 5,
      name: "0005_device_session_uploads.sql",
      fileName: "0005_device_session_uploads.sql",
      sha256:
        "2652bf96d0183899970167de5527c46300910782cdef3c139ac29e02d6ee78f1",
    }),
    Object.freeze({
      version: 6,
      name: "0006_device_transcriptions.sql",
      fileName: "0006_device_transcriptions.sql",
      sha256:
        "1e64b3a13ff926fa1e50d959625a830a09320d8c40a66ecae9a250675b1060a0",
    }),
    Object.freeze({
      version: 7,
      name: "0007_device_audio_chunks.sql",
      fileName: "0007_device_audio_chunks.sql",
      sha256:
        "57bae0f17f4ee8bdfcbd92dbf4daa713c83ea6850280b06d5cb25cfa8426060c",
    }),
    Object.freeze({
      version: 8,
      name: "0008_device_capture_id.sql",
      fileName: "0008_device_capture_id.sql",
      sha256:
        "4bedaeb4a22ac0a9e08fdc14bce9030135a10ccf4ec8746403a9fa0d748ef918",
    }),
    Object.freeze({
      version: 9,
      name: "0009_device_capture_time.sql",
      fileName: "0009_device_capture_time.sql",
      sha256:
        "d4aa1e8b83636fb5d9b49807b2a21fa511b729fb669e1bc1a1958adc3cd46fd4",
    }),
  ]
);
