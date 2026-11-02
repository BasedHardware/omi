import 'dart:convert';
import 'dart:io';

/// Only committed native receipts make Watch recovery copies discoverable.
/// This prevents account adoption and a scan between .bin publication and the
/// durable receipt from processing/deleting audio before custody is recorded.
Future<String?> watchRecordingOwner(Directory directory, String fileName) async {
  try {
    final value = jsonDecode(await File('${directory.path}/.watch-receipts/$fileName').readAsString());
    if (value is! Map<String, dynamic>) return null;
    final metadata = value['metadata'];
    final digest = value['digest'];
    if (metadata is! Map<String, dynamic> || digest is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(digest)) {
      return null;
    }
    final session = metadata['sessionID'];
    final segment = metadata['segment'];
    final start = metadata['startedAt'];
    final owner = metadata['ownerUID'];
    if (metadata['version'] != 1 ||
        session is! String ||
        !RegExp(r'^[0-9a-fA-F]{32}$').hasMatch(session) ||
        segment is! int ||
        segment < 0 ||
        start is! int ||
        start <= 0 ||
        owner is! String ||
        owner.isEmpty ||
        utf8.encode(owner).length > 256) {
      return null;
    }
    final expected = 'audio_omibatchwatch${session}s${segment}_pcm16_16000_1_fs160_$start.bin';
    return expected == fileName ? owner : null;
  } on Object {
    // Incomplete/corrupt receipts are recovery work, never unowned recordings.
    return null;
  }
}
