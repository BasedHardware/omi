import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/on_device/on_device_engine.dart';
import 'package:omi/services/on_device/on_device_projection.dart';
import 'package:omi/backend/schema/conversation.dart';

import 'package:omi/services/experiments/on_device_overflow_gate.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_provenance.dart';
import 'package:omi/services/on_device/on_device_schedule_policy.dart';
import 'package:omi/services/on_device/on_device_settings.dart';
import 'package:omi/services/on_device/phone_power_source.dart';

/// State every on-device transcription surface reads: whether the feature is on for this reader,
/// their settings, the speech model, the latest scheduling decision and per-conversation
/// provenance.
///
/// [isActive] is false until [ensureLoaded] reads [OnDeviceOverflowGate]; while it is false every
/// surface renders nothing, so with the flag off nothing changes for anyone.
///
/// The WAL runner owns processing; this controller shares scheduling and persisted provenance.
class OnDeviceTranscriptionController extends ChangeNotifier {
  OnDeviceTranscriptionController({
    OnDeviceSettingsStore? store,
    OnDeviceModel? model,
    PhonePowerSource power = const NativePhonePowerSource(),
    OnDeviceSchedulePolicy policy = const OnDeviceSchedulePolicy(),
    Future<bool> Function()? readGate,
    this.canSummarizeOnPhone = false,
    this.manageNativeCustody = true,
    DateTime Function()? clock,
  })  : _store = store,
        _model = model,
        _power = power,
        _policy = policy,
        _readGate = readGate ?? OnDeviceOverflowGate.read,
        _clock = clock ?? DateTime.now;

  static OnDeviceTranscriptionController _instance = OnDeviceTranscriptionController();
  static OnDeviceTranscriptionController get instance => _instance;

  @visibleForTesting
  static set instance(OnDeviceTranscriptionController controller) => _instance = controller;

  OnDeviceSettingsStore? _store;
  OnDeviceModel? _model;
  final PhonePowerSource _power;
  final OnDeviceSchedulePolicy _policy;
  final Future<bool> Function() _readGate;
  final DateTime Function() _clock;

  /// Whether this phone can summarize with its built-in model (iPhone 15 Pro or later). False until
  /// the Apple Foundation Models bridge lands; summaries then come from Omi Cloud.
  final bool manageNativeCustody;
  bool canSummarizeOnPhone;
  Future<void> Function(bool now)? runPending;
  Future<bool> Function(String id)? deleteLocalConversation;
  final completedRecordingNames = <String>{};
  int pendingSeconds = 0;
  double progress = 0;
  bool lastRunFailed = false;
  void markRunFailure(bool failed) {
    lastRunFailed = failed;
    notifyListeners();
  }

  void setPendingSeconds(int seconds) {
    if (seconds == pendingSeconds) return;
    pendingSeconds = seconds;
    notifyListeners();
  }

  void setProgress(double value) {
    progress = value;
    notifyListeners();
  }

  Future<void> transcribeNow({int? seconds}) async {
    await evaluate(pendingAudio: Duration(seconds: seconds ?? pendingSeconds), transcribeNow: true);
    await runPending?.call(true);
  }

  Future<void>? _loading;
  bool _active = false;
  OnDeviceSettings _settings = const OnDeviceSettings();
  OnDeviceRunDecision? _decision;
  DateTime? _lastRunAt;
  bool _isTranscribing = false;
  final Map<String, OnDeviceProvenance> _provenance = {};

  bool _atCap = false;
  bool _paid = false;
  void updateEntitlement({required bool atCap, required bool paid}) {
    if (_atCap == atCap && _paid == paid) return;
    _atCap = atCap;
    _paid = paid;
    if (_active) {
      unawaited(_syncNativeCustody());
      notifyListeners();
    }
  }

  Future<void> _syncNativeCustody() async {
    if (!manageNativeCustody) return;
    await SharedPreferencesUtil().saveBool('onDeviceOverflowConfigured', _active && _settings.enabled);
    await SharedPreferencesUtil().saveBool('onDeviceOverflowActive', shouldKeepAudioLocal);
    if (shouldKeepAudioLocal) await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', false);
    if (Platform.isAndroid) {
      try {
        await AppleBatchEngine.channel.invokeMethod<void>('scheduleBackground', {
          'charging': _settings.schedule == OnDeviceSchedule.whileCharging,
          'schedule': _settings.schedule.storageId
        });
      } catch (_) {/* Foreground runner remains available. */}
    }
  }

  bool get shouldKeepAudioLocal => _active && _settings.enabled && (_atCap || (_paid && _settings.saveLiveHours));
  ServerConversation displayConversation(ServerConversation row) => applyOnDeviceProjection(row, enabled: _active);
  bool get isActive => _active;
  OnDeviceSettings get settings => _settings;
  OnDeviceModel get model => _model ??= OnDeviceModel.forPlatform();
  OnDeviceRunDecision? get decision => _decision;
  bool get isTranscribing => _isTranscribing;

  /// Reads the gate once; when on, loads settings and checks the model. Safe to call from every
  /// surface's initState.
  Future<void> ensureLoaded() => _loading ??= _load();

  Future<void> _load() async {
    if (!await _readGate()) {
      if (manageNativeCustody) {
        await SharedPreferencesUtil().saveBool('onDeviceOverflowConfigured', false);
        await SharedPreferencesUtil().saveBool('onDeviceOverflowActive', false);
      }
      return;
    }
    _settings = (_store ??= OnDeviceSettingsStore()).load();
    _active = true;
    model.addListener(notifyListeners);
    await _syncNativeCustody();
    await model.refresh();
    try {
      canSummarizeOnPhone = await AppleBatchEngine().canSummarize();
    } catch (_) {
      canSummarizeOnPhone = false;
    }
    for (final row in SharedPreferencesUtil().cachedConversations) {
      final provenance = OnDeviceProvenance.fromConversation(row);
      if (provenance != null) _provenance[row.id] = provenance;
    }
    notifyListeners();
  }

  Future<void> updateSettings(OnDeviceSettings settings) async {
    if (settings == _settings) return;
    _settings = settings;
    notifyListeners();
    await (_store ??= OnDeviceSettingsStore()).save(settings);
    await _syncNativeCustody();
  }

  /// Runs the policy for [pendingAudio] now and keeps the decision for the UI.
  Future<OnDeviceRunDecision> evaluate({required Duration pendingAudio, bool transcribeNow = false}) async {
    final power = await _power.read();
    final decision = _policy.decide(OnDeviceRunInputs(
      schedule: _settings.schedule,
      isCharging: power.isCharging,
      batteryPercent: power.batteryPercent,
      pendingAudio: pendingAudio,
      lastRunAt: _lastRunAt,
      now: _clock(),
      transcribeNowRequested: transcribeNow,
    ));
    if (decision != _decision) {
      _decision = decision;
      notifyListeners();
    }
    return decision;
  }

  /// Provenance for a conversation transcribed on this phone, or null.
  OnDeviceProvenance? provenanceFor(String conversationId) {
    if (!_active) return null;
    final known = _provenance[conversationId];
    if (known != null) return known;
    for (final row in SharedPreferencesUtil().cachedConversations) {
      if (row.id == conversationId) return OnDeviceProvenance.fromConversation(row);
    }
    return null;
  }

  /// Called by the on-device pipeline when it finishes a conversation.
  void recordProvenance(String conversationId, OnDeviceProvenance provenance) {
    _provenance[conversationId] = provenance;
    notifyListeners();
  }

  /// Called by the on-device runner around a batch.
  void markRun({required bool running}) {
    if (!running) _lastRunAt = _clock();
    if (_isTranscribing == running) return;
    _isTranscribing = running;
    notifyListeners();
  }

  /// Puts the controller in a known state for widget tests and renders.
  @visibleForTesting
  void debugActivate({OnDeviceSettings settings = const OnDeviceSettings(enabled: true), bool transcribing = false}) {
    _loading = Future.value();
    _active = true;
    _settings = settings;
    _isTranscribing = transcribing;
    model.addListener(notifyListeners);
    notifyListeners();
  }

  @override
  void dispose() {
    _model?.removeListener(notifyListeners);
    super.dispose();
  }
}
