import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

class MetaCaptureQueueItem {
  const MetaCaptureQueueItem({
    required this.id,
    required this.path,
    required this.capturedAt,
    required this.sha256,
    required this.deviceUuid,
    this.deviceName,
  });

  final String id;
  final String path;
  final DateTime capturedAt;
  final String sha256;
  final String deviceUuid;
  final String? deviceName;

  factory MetaCaptureQueueItem.fromJson(Map<String, dynamic> json) {
    return MetaCaptureQueueItem(
      id: json['id'] as String,
      path: json['path'] as String,
      capturedAt: DateTime.parse(json['capturedAt'] as String).toUtc(),
      sha256: json['sha256'] as String,
      deviceUuid: json['deviceUuid'] as String,
      deviceName: json['deviceName'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'path': path,
      'capturedAt': capturedAt.toUtc().toIso8601String(),
      'sha256': sha256,
      'deviceUuid': deviceUuid,
      if (deviceName != null) 'deviceName': deviceName,
    };
  }
}

class MetaCaptureQueue {
  MetaCaptureQueue({required this.rootDirectory});

  static final Random _random = Random.secure();

  final Directory rootDirectory;

  Directory get _framesDirectory => Directory('${rootDirectory.path}/meta_capture_frames');
  File get _queueFile => File('${rootDirectory.path}/meta_capture_queue.jsonl');
  File get _uploadedFile => File('${rootDirectory.path}/meta_capture_uploaded.txt');

  Future<MetaCaptureQueueItem> enqueue({
    required Uint8List bytes,
    required DateTime capturedAt,
    required String deviceUuid,
    String? deviceName,
  }) async {
    await rootDirectory.create(recursive: true);
    await _framesDirectory.create(recursive: true);

    final digest = sha256.convert(bytes).toString();
    final id = '${capturedAt.toUtc().microsecondsSinceEpoch}-${_randomHex(8)}';
    final frameFile = File('${_framesDirectory.path}/$id.jpg');
    await frameFile.writeAsBytes(bytes, flush: true);

    final item = MetaCaptureQueueItem(
      id: id,
      path: frameFile.path,
      capturedAt: capturedAt.toUtc(),
      sha256: digest,
      deviceUuid: deviceUuid,
      deviceName: deviceName,
    );
    await _queueFile.writeAsString('${jsonEncode(item.toJson())}\n', mode: FileMode.append, flush: true);
    return item;
  }

  Future<List<MetaCaptureQueueItem>> pending({required int limit}) async {
    if (limit <= 0 || !await _queueFile.exists()) {
      return [];
    }

    final uploadedIds = await _readUploadedIds();
    final items = <MetaCaptureQueueItem>[];
    final lines = await _queueFile.readAsLines();

    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty) {
        continue;
      }

      try {
        final item = MetaCaptureQueueItem.fromJson(jsonDecode(trimmed) as Map<String, dynamic>);
        if (uploadedIds.contains(item.id) || !await File(item.path).exists()) {
          continue;
        }
        items.add(item);
      } on FormatException {
        continue;
      } on TypeError {
        continue;
      }
    }

    items.sort((a, b) => a.capturedAt.compareTo(b.capturedAt));
    return items.take(limit).toList(growable: false);
  }

  Future<void> markUploaded(String id) async {
    await rootDirectory.create(recursive: true);
    await _uploadedFile.writeAsString('$id\n', mode: FileMode.append, flush: true);
  }

  Future<Set<String>> _readUploadedIds() async {
    if (!await _uploadedFile.exists()) {
      return <String>{};
    }
    final lines = await _uploadedFile.readAsLines();
    return lines.map((line) => line.trim()).where((line) => line.isNotEmpty).toSet();
  }

  static String _randomHex(int byteCount) {
    final buffer = StringBuffer();
    for (var i = 0; i < byteCount; i += 1) {
      buffer.write(_random.nextInt(256).toRadixString(16).padLeft(2, '0'));
    }
    return buffer.toString();
  }
}
