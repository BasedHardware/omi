import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/on_device/on_device_overflow_intake.dart';
import 'on_device_segment_upload.dart';
import 'on_device_segment_snapshot.dart';
import 'package:omi/services/experiments/client_refactor_flags.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/on_device/on_device_engine.dart';
import 'package:omi/services/on_device/on_device_projection.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/on_device/on_device_tuning.dart';
import 'package:omi/services/sockets/on_device_whisper_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';

/// Read only complete frames. Malformed custody is an error, never a partial success.
Stream<List<Uint8List>> readOnDeviceChunks(File file, int framesPerSecond) async* {
  if (framesPerSecond <= 0) throw const FormatException('Invalid frame rate');
  final handle = await file.open();
  final frames = <Uint8List>[];
  try {
    while (true) {
      final header = await handle.read(4);
      if (header.isEmpty) break;
      if (header.length != 4) throw const FormatException('Truncated WAL header');
      final length = ByteData.sublistView(header).getUint32(0, Endian.little);
      if (length == 0 || length > 1024 * 1024) throw const FormatException('Invalid WAL frame');
      final payload = await handle.read(length);
      if (payload.length != length) throw const FormatException('Truncated WAL payload');
      frames.add(payload);
      if (frames.length == framesPerSecond * OnDeviceTuning.decodeChunkSeconds) {
        yield List.of(frames);
        frames.clear();
      }
    }
    if (frames.isNotEmpty) yield List.of(frames);
  } finally {
    await handle.close();
  }
}

class PreparedContinuationDisabled implements Exception {}

/// Owns only finalized phone-only WALs. The WAL generation fences every asynchronous publish.
class OnDeviceRunner with WidgetsBindingObserver {
  OnDeviceRunner(
      {required this.sync,
      required this.controller,
      required this.publish,
      this.transcribeChunk,
      this.send,
      this.cloudBaseUrl});
  final LocalWalSyncImpl sync;
  final OnDeviceTranscriptionController controller;
  final void Function(ServerConversation) publish;
  final Future<OnDeviceBatchResult> Function(Uint8List, String)? transcribeChunk;
  final ApiSend? send;
  final String? cloudBaseUrl;
  Timer? _timer;
  bool _busy = false;
  Completer<void>? _runDone;
  bool _cancelled = false;
  final _published = <String>{};
  int? _publishedGeneration;
  String? lastError;
  int pendingSeconds = 0;
  static const channel = MethodChannel('com.omi/on_device');

  Future<void> start() async {
    await controller.ensureLoaded();
    if (!controller.isActive) return;
    WidgetsBinding.instance.addObserver(this);
    controller.runPending = (now) => run(transcribeNow: now);
    controller.deleteLocalConversation = deleteLocal;
    channel.setMethodCallHandler((call) async {
      if (call.method == 'backgroundRun') {
        try {
          await run();
        } finally {
          await channel.invokeMethod<void>('backgroundComplete', {'success': lastError == null});
        }
      } else if (call.method == 'backgroundExpired') {
        await cancel();
      }
    });
    if (Platform.isAndroid) {
      await channel.invokeMethod<void>('scheduleBackground', {
        'charging': controller.settings.schedule.storageId == 'while_charging',
        'schedule': controller.settings.schedule.storageId
      });
    }
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => unawaited(run()));
    if (Platform.isIOS && await channel.invokeMethod<bool>('backgroundReady') == true) return;
    await run();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(run());
    if (state == AppLifecycleState.paused) {
      unawaited(channel.invokeMethod<void>('scheduleBackground', {
        'charging': controller.settings.schedule.storageId == 'while_charging',
        'schedule': controller.settings.schedule.storageId
      }).catchError((_) {}));
    }
  }

  Future<void> run({bool transcribeNow = false}) async {
    if (!controller.isActive) return;
    if (_busy) {
      await _runDone?.future;
      return;
    }
    _runDone = Completer<void>();
    _busy = true;
    _cancelled = false;
    final generation = sync.sessionGeneration;
    try {
      if (_publishedGeneration != generation) {
        _published.clear();
        controller.completedRecordingNames.clear();
        _publishedGeneration = generation;
      }
      await intakeOnDeviceOverflow(sync);
      final all = await sync.getAllWals();
      for (final wal in all.where((w) => w.onDeviceConversation != null)) {
        if (generation != sync.sessionGeneration || _cancelled) return;
        if (wal.filePath != null) controller.completedRecordingNames.add(wal.filePath!);
        final row = ServerConversation.fromJson(wal.onDeviceConversation!);
        controller.recordProvenance(row.id, OnDeviceProvenance.fromConversation(row)!);
        if (_published.add(row.id)) publish(row);
      }
      final pending = all
          .where((w) =>
              w.onDeviceOnly &&
              w.storage == WalStorage.disk &&
              w.status == WalStatus.miss &&
              w.onDeviceConversation == null)
          .toList();
      pendingSeconds = pending.fold(0, (sum, w) => sum + w.seconds);
      controller.setPendingSeconds(pendingSeconds);
      if (!controller.settings.enabled) return;
      if (pending.any((w) => w.onDevicePreparedUpload != null) && !await ClientRefactorFlags.chunkUploads()) {
        for (final wal in pending.where((w) => w.onDevicePreparedUpload != null)) {
          await sync.rejectDisabledPreparedUpload(wal, generation);
        }
        throw PreparedContinuationDisabled();
      }
      final hasModel = controller.model.status.isInstalled;
      final resumePrepared = !hasModel && await ClientRefactorFlags.chunkUploads();
      if (!hasModel && !(resumePrepared && pending.any((w) => w.onDevicePreparedUpload != null))) return;
      final decision =
          await controller.evaluate(pendingAudio: Duration(seconds: pendingSeconds), transcribeNow: transcribeNow);
      if (!decision.shouldRun) return;
      controller.markRunFailure(false);
      controller.markRun(running: true);
      for (final wal in pending) {
        if (!hasModel && (!resumePrepared || wal.onDevicePreparedUpload == null)) continue;
        if (_cancelled || generation != sync.sessionGeneration) return;
        await _process(wal, generation);
      }
      lastError = null;
    } catch (error) {
      // Keep original bytes and retry from them. No transcript content in error logs.
      if (_cancelled || (error is PlatformException && error.code == 'CANCELLED')) {
        lastError = null;
        controller.markRunFailure(false);
      } else {
        lastError = error is PreparedContinuationDisabled ? 'continuation_disabled' : error.runtimeType.toString();
        controller.markRunFailure(true);
      }
    } finally {
      if (controller.isTranscribing) controller.markRun(running: false);
      _busy = false;
      _runDone?.complete();
      _runDone = null;
    }
  }

  Future<void> _process(Wal wal, int generation) async {
    final path = await Wal.getFilePath(wal.filePath);
    if (path == null) throw StateError('Missing WAL path');
    final chunked = await ClientRefactorFlags.chunkUploads();
    if (_cancelled || generation != sync.sessionGeneration) return;
    if (!chunked && wal.onDevicePreparedUpload != null) {
      await sync.rejectDisabledPreparedUpload(wal, generation);
      throw PreparedContinuationDisabled();
    }
    final prepared = chunked && wal.onDevicePreparedUpload != null
        ? OnDeviceSegmentSnapshot.fromJson(wal.onDevicePreparedUpload!)
        : null;
    final source = wal.device.contains('phone')
        ? ConversationSource.phone
        : wal.device.contains('limitless')
            ? ConversationSource.limitless
            : ConversationSource.omi;
    final language = prepared?.language ?? SharedPreferencesUtil().userPrimaryLanguage;
    final apple = AppleBatchEngine();
    OnDeviceWhisperProvider? whisper;
    if (prepared == null && !Platform.isIOS && transcribeChunk == null) {
      final service = FreemiumTranscriptionService();
      await service.checkReadiness();
      final model = service.cachedModelPath;
      if (model == null) throw StateError('Whisper model unavailable');
      whisper = OnDeviceWhisperProvider(modelPath: model, language: language, onDeviceOverflowEnabled: true);
    }
    final transcoder = wal.codec.isOpusSupported()
        ? OpusToWavTranscoder(sampleRate: wal.sampleRate, channels: wal.channel)
        : PcmToWavTranscoder(sampleRate: wal.sampleRate, channels: wal.channel);
    final segments = prepared?.segments ?? <TranscriptSegment>[];
    var offset = prepared?.duration ?? 0.0;
    var engine = prepared?.engine ?? 'whisper_tiny';
    if (prepared == null) {
      try {
        await for (final frames in readOnDeviceChunks(File(path), wal.codec.getFramesPerSecond())) {
          if (_cancelled || generation != sync.sessionGeneration) return;
          final wav = transcoder.transcodeFrames(frames);
          final duration = frames.length / wal.codec.getFramesPerSecond();
          List<OnDeviceWord> words;
          if (Platform.isIOS || transcribeChunk != null) {
            final result = transcribeChunk != null
                ? await transcribeChunk!(wav, language)
                : await apple.transcribe(wav, language: language.isEmpty ? 'en' : language);
            engine = result.engine;
            words = result.words.isNotEmpty ? result.words : [OnDeviceWord(result.text, 0, duration)];
          } else {
            final result = await whisper!.transcribe(wav);
            if (result == null) throw StateError('Whisper returned no transcript');
            words = result.segments.map((s) => OnDeviceWord(s.text, s.start, s.end)).toList();
          }
          // Phrase groups bound endpoint segment count. Every native word's times are retained
          // within the chunk and group ends always come from recognized audio, not invented speakers.
          for (var i = 0; i < words.length; i += 30) {
            final group = words.skip(i).take(30).where((w) => w.text.trim().isNotEmpty).toList();
            if (group.isEmpty) continue;
            segments.add(TranscriptSegment(
                id: '${segments.length}',
                text: group.map((w) => w.text.trim()).join(' '),
                speaker: 'SPEAKER_00',
                isUser: false,
                personId: null,
                start: offset + group.first.start,
                end: offset + group.last.end,
                translations: const [],
                sttProvider: 'on_device:$engine'));
          }
          offset += duration;
          controller.setProgress(wal.seconds > 0 ? (offset / wal.seconds).clamp(0, 1) : 0);
        }
      } finally {
        whisper?.dispose();
      }
    }
    if (segments.isEmpty) throw StateError('No speech recognized; audio retained');
    // refactor: superseded by on_device_segment_upload when clients_from_segments_chunks=serve
    if (!chunked && segments.length > 500) throw StateError('Transcript exceeds ingestion limit; audio retained');
    if (_cancelled || generation != sync.sessionGeneration) return;
    final started = DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000, isUtc: true);
    final finished = started.add(Duration(milliseconds: (offset * 1000).round()));
    final text = segments.map((s) => s.text).join(' ');
    var summary = OnDeviceSummaryOrigin.none;
    Map<String, dynamic>? projection = controller.settings.keepEverythingOnDevice ? null : prepared?.projection;
    final title = String.fromCharCodes(text.split(' ').take(8).join(' ').runes.take(100));
    var structure = projection == null ? Structured(title, '') : Structured.fromJson(projection['structure']);
    if (projection != null) summary = OnDeviceSummaryOrigin.phone;
    // "Keep everything" explicitly means transcripts only, even on AFM devices.
    if (prepared == null &&
        !controller.settings.keepEverythingOnDevice &&
        Platform.isIOS &&
        await apple.canSummarize()) {
      try {
        final generated = await apple.summarize(text);
        generated['title'] = structure.title;
        structure = Structured.fromJson(generated);
        summary = OnDeviceSummaryOrigin.phone;
        projection = {
          'schema_version': 1,
          'transcript_sha256': onDeviceTranscriptHash(segments),
          'structure': generated,
          'action_items': [],
          'provenance': {
            'model_id': 'apple-foundation-models',
            'runtime': 'local',
            'device_class': 'iphone',
            'generated_at': DateTime.now().toUtc().toIso8601String()
          }
        };
      } on PlatformException {
        recordFallback(const ApiFallbackEvent(reason: ApiFallbackReason.error, outcome: ApiFallbackOutcome.degraded));
      }
    }
    if (chunked && prepared == null && !controller.settings.keepEverythingOnDevice) {
      final frozen = OnDeviceSegmentSnapshot(
          segments: segments, duration: offset, language: language, engine: engine, projection: projection);
      if (!await sync.persistPreparedSegmentUpload(wal, frozen.toJson(), generation)) return;
    }
    if (_cancelled || generation != sync.sessionGeneration) return;
    var id = 'ondevice-${wal.id}';
    ServerConversation? server;
    if (!controller.settings.keepEverythingOnDevice) {
      final baseUrl = cloudBaseUrl ?? Env.apiBaseUrl;
      if (baseUrl == null || baseUrl.isEmpty) throw StateError('Cloud endpoint unavailable');
      id = await uploadOnDeviceSegments(
          baseUrl: baseUrl,
          sessionId: id,
          segments: segments,
          metadata: {
            'source': source.name,
            'language': language.isEmpty ? 'en' : language,
            'started_at': started.toIso8601String(),
            'finished_at': finished.toIso8601String()
          },
          chunked: chunked,
          send: send,
          projection: projection,
          canSend: () => !_cancelled && generation == sync.sessionGeneration);
      if (_cancelled || generation != sync.sessionGeneration) return;
      final detail = await ConversationApi(baseUrl: baseUrl, send: send).byId(id);
      switch (detail) {
        case ApiSuccess<ServerConversation>():
          server = detail.data;
        case ApiFailure<ServerConversation>():
          throw StateError('Conversation fetch ${detail.problem.kind.name}');
      }
      if (projection == null) summary = OnDeviceSummaryOrigin.cloud;
    }
    if (_cancelled || generation != sync.sessionGeneration) return;
    if (server != null && projection != null) {
      if (server.clientProcessing?['transcript_sha256'] == onDeviceTranscriptHash(segments)) {
        final serverJson = server.toJson();
        serverJson['structured'] = projection['structure'];
        server = ServerConversation.fromJson(serverJson);
      } else {
        summary = OnDeviceSummaryOrigin.cloud;
        recordFallback(const ApiFallbackEvent(reason: ApiFallbackReason.error, outcome: ApiFallbackOutcome.degraded));
      }
    }
    final row = server ??
        ServerConversation(
            id: id,
            createdAt: started,
            startedAt: started,
            finishedAt: finished,
            structured: structure,
            transcriptSegments: segments,
            source: source);
    final json = row.toJson();
    json['on_device_provenance'] = {
      'engine': engine,
      'summary': summary.name,
      'reason':
          controller.settings.saveLiveHours ? OnDeviceReason.savingLiveHours.name : OnDeviceReason.liveHoursUsed.name
    };
    if (!await sync.persistOnDeviceConversation(wal, json, generation)) return;
    final stored = ServerConversation.fromJson(json);
    controller.recordProvenance(id, OnDeviceProvenance.fromConversation(stored)!);
    if (wal.filePath != null) controller.completedRecordingNames.add(wal.filePath!);
    controller.setPendingSeconds((controller.pendingSeconds - wal.seconds).clamp(0, controller.pendingSeconds));
    _published.add(id);
    publish(stored);
  }

  Future<bool> deleteLocal(String id) async {
    final generation = sync.sessionGeneration;
    final wals = await sync.getAllWals();
    final matches = wals.where((w) => w.onDeviceConversation?['id'] == id).toList();
    for (final wal in matches) {
      if (generation != sync.sessionGeneration) return false;
      await sync.deleteWal(wal);
    }
    return matches.isNotEmpty;
  }

  Future<void> cancel() async {
    _cancelled = true;
    if (Platform.isIOS) await AppleBatchEngine().cancel();
  }

  void dispose() {
    _cancelled = true;
    _timer?.cancel();
    controller.runPending = null;
    controller.deleteLocalConversation = null;
    WidgetsBinding.instance.removeObserver(this);
  }
}
