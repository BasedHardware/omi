import 'dart:async';

import 'package:flutter/foundation.dart';

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
/// Not yet wired: the batch runner that acts on [decision], a platform [PhonePowerSource], the
/// iOS model and the source of [provenanceFor] (the conversation wire has no provenance field).
class OnDeviceTranscriptionController extends ChangeNotifier {
  OnDeviceTranscriptionController({
    OnDeviceSettingsStore? store,
    OnDeviceModel? model,
    PhonePowerSource power = const UnknownPhonePowerSource(),
    OnDeviceSchedulePolicy policy = const OnDeviceSchedulePolicy(),
    Future<bool> Function()? readGate,
    this.canSummarizeOnPhone = false,
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
  final bool canSummarizeOnPhone;

  Future<void>? _loading;
  bool _active = false;
  OnDeviceSettings _settings = const OnDeviceSettings();
  OnDeviceRunDecision? _decision;
  DateTime? _lastRunAt;
  bool _isTranscribing = false;
  final Map<String, OnDeviceProvenance> _provenance = {};

  bool get isActive => _active;
  OnDeviceSettings get settings => _settings;
  OnDeviceModel get model => _model ??= OnDeviceModel.forPlatform();
  OnDeviceRunDecision? get decision => _decision;
  bool get isTranscribing => _isTranscribing;

  /// Reads the gate once; when on, loads settings and checks the model. Safe to call from every
  /// surface's initState.
  Future<void> ensureLoaded() => _loading ??= _load();

  Future<void> _load() async {
    if (!await _readGate()) return;
    _settings = (_store ??= OnDeviceSettingsStore()).load();
    _active = true;
    model.addListener(notifyListeners);
    notifyListeners();
    unawaited(model.refresh());
  }

  Future<void> updateSettings(OnDeviceSettings settings) async {
    if (settings == _settings) return;
    _settings = settings;
    notifyListeners();
    await (_store ??= OnDeviceSettingsStore()).save(settings);
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
  OnDeviceProvenance? provenanceFor(String conversationId) => _active ? _provenance[conversationId] : null;

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
