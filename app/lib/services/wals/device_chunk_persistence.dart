part of 'local_wal_sync.dart';

/// All device drains use this transaction: admission, identical length-prefixed
/// bytes, flushed file, indexed WAL, then proof of durability before device ACK.
/// Naming callbacks preserve the producer's existing collision sequence.
extension DeviceChunkPersistence on LocalWalSync {
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
        do {
          name = '${stem}_u${nextCollisionSequence()}$ext';
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
