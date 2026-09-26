/// Whether [fileName] is a framed WAL container the offline sync pipeline
/// understands (length-prefixed opus/PCM frames in a `.bin`).
///
/// Issue #5363: the live path already sends opus; uploading a decoded `.wav`
/// costs ~16× bandwidth. PCM-framed bins are valid for some devices — WAV is not.
bool isFramedWalSyncFileName(String fileName) {
  final base = fileName.split('/').last.toLowerCase();
  if (base.endsWith('.wav')) return false;
  return base.startsWith('audio_') && base.endsWith('.bin');
}

/// Rejects decoded WAV (and any other non-WAL name) before `/v2/sync-local-files`.
void assertWalSyncFilesAreFramedBins(Iterable<String> fileNames) {
  for (final name in fileNames) {
    if (!isFramedWalSyncFileName(name)) {
      throw ArgumentError(
        'WAL sync must upload framed .bin audio (opus/PCM), not decoded WAV: $name',
      );
    }
  }
}
