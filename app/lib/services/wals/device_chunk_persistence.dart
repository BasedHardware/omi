part of 'local_wal_sync.dart';

/// All device drains use this transaction: admission, identical length-prefixed
/// bytes, flushed file, indexed WAL, then proof of durability before device ACK.
/// Naming callbacks preserve the producer's existing collision sequence.
/// New default collision names keep the capture timestamp as the last token,
/// which is the server's filename wire contract. Existing files are untouched.
extension DeviceChunkPersistence on LocalWalSync {
  Future<Wal> persistEmptyRingRecords(
      {required Wal source,
      required int ringId,
      required int start,
      required int end,
      required int admittedGeneration}) async {
    if (end <= start) throw StateError('empty marker interval');
    final owner = SharedPreferencesUtil().uid;
    if (owner.isEmpty || sessionGeneration != admittedGeneration) {
      throw StateError('empty marker has no current owner');
    }
    final data = utf8.encode(jsonEncode({
      'kind': 'empty_ring_records_v1',
      'device': source.device,
      'ring': ringId,
      'start': start,
      'end': end,
      'owner': owner
    }));
    if (!await ensureStorageAdmission(bytes: data.length, admittedGeneration: admittedGeneration)) {
      throw StateError('empty marker storage refused');
    }
    final dir = await getApplicationDocumentsDirectory();
    final name = 'custody_empty_${const Uuid().v4()}.ring-empty';
    try {
      await File('${dir.path}/$name').writeAsBytes(data, flush: true);
      final marker = Wal(
          codec: source.codec,
          timerStart: source.timerStart,
          seconds: 0,
          totalFrames: 0,
          filePath: name,
          storage: WalStorage.disk,
          status: WalStatus.synced,
          ownerUid: owner,
          device: source.device,
          downloadRingId: ringId,
          downloadSeqStart: start,
          downloadSeqEnd: end,
          downloadFileBytes: data.length,
          fileSha256: sha256.convert(data).toString());
      await addExternalWal(marker, admittedGeneration: admittedGeneration);
      if (!await hasDurableWal(marker, admittedGeneration: admittedGeneration)) {
        throw StateError('empty marker index not durable');
      }
      return marker;
    } catch (_) {
      releaseStorageAdmission(data.length);
      rethrow;
    }
  }

  Future<Wal> persistDeviceChunk({
    required Wal source,
    required List<List<int>> frames,
    required int timerStart,
    required int admittedGeneration,
    required int Function() nextCollisionSequence,
    String? clockRun,
    String Function()? fileName,
    BleAudioCodec? codec,
    int? seconds,
    int? channel,
    int? sampleRate,
    String? deviceModel,
    WalStorage originalStorage = WalStorage.sdcard,
    int? downloadRingId,
    int? downloadSeqStart,
    int? downloadSeqEnd,
  }) async {
    if (frames.isEmpty) throw StateError('refusing to persist an empty chunk');
    final data = encodeWalFrames(frames);
    if (!await ensureStorageAdmission(bytes: data.length, admittedGeneration: admittedGeneration)) {
      throw StateError('storage admission refused (cap/disk reserve)');
    }
    try {
      final dir = await getApplicationDocumentsDirectory();
      var name = fileName?.call() ?? source.getFileNameByTimeStarts(timerStart, clockRun: clockRun) as String;
      if (fileName != null) {
        while (await File('${dir.path}/$name').exists()) {
          name = fileName();
        }
      } else if (await File('${dir.path}/$name').exists()) {
        final dot = name.lastIndexOf('.');
        final stem = dot > 0 ? name.substring(0, dot) : name;
        final ext = dot > 0 ? name.substring(dot) : '';
        final timestampSeparator = stem.lastIndexOf('_');
        final prefix = stem.substring(0, timestampSeparator);
        final timestamp = stem.substring(timestampSeparator + 1);
        do {
          final nonce = nextCollisionSequence();
          name = const bool.fromEnvironment('OMI_DEVICE_COLLISION_TIMESTAMP_LAST_OFF')
              ? '${stem}_u$nonce$ext'
              : '${deviceClockCollisionPrefix(prefix, nonce)}_$timestamp$ext';
        } while (await File('${dir.path}/$name').exists());
      }
      await File('${dir.path}/$name').writeAsBytes(data, flush: true);
      final fps = source.codec.getFramesPerSecond();
      final wal = Wal(
          codec: codec ?? source.codec,
          channel: channel ?? source.channel,
          sampleRate: sampleRate ?? source.sampleRate,
          timerStart: timerStart,
          filePath: name,
          storage: WalStorage.disk,
          status: WalStatus.miss,
          device: source.device,
          deviceModel: deviceModel ?? source.deviceModel,
          seconds: seconds ?? (fps > 0 ? frames.length ~/ fps : 0),
          totalFrames: frames.length,
          originalStorage: originalStorage,
          downloadRingId: downloadRingId,
          downloadSeqStart: downloadSeqStart,
          downloadSeqEnd: downloadSeqEnd,
          downloadFileBytes: downloadRingId != null ? data.length : null,
          fileSha256: downloadRingId != null ? sha256.convert(data).toString() : null,
          clockRun: clockRun);
      await addExternalWal(wal, admittedGeneration: admittedGeneration);
      if (!await hasDurableWal(wal, admittedGeneration: admittedGeneration)) {
        throw StateError('WAL not durable after registration');
      }
      return wal;
    } catch (_) {
      releaseStorageAdmission(data.length);
      rethrow;
    }
  }
}
