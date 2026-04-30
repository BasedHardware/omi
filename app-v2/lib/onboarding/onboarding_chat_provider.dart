import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:nooto_v2/onboarding/chat_step_registry.dart';
import 'package:nooto_v2/companion/companion_signals.dart';
import 'package:nooto_v2/companion/companion_turn.dart';
import 'package:nooto_v2/onboarding/widgets/chip_widget_turn.dart' show kLanguageLabelById;
import 'package:nooto_v2/providers/locale_provider.dart';

const String _kStateKey = 'onboarding.chat.state.v1';

/// Drives the onboarding chat. Mirrors the desktop-v2 store at
/// `desktop-v2/src/stores/onboardingStore.ts` + the companion store's signal
/// tracking, simplified for Phase 1 (no LLM streaming yet — `streamOpener` is
/// a synthetic delay over the canned `fallbackOpener`).
class OnboardingChatProvider extends ChangeNotifier {
  OnboardingChatProvider();

  final List<ChatStepDef> _steps = registryForCurrentPlatform();
  final List<CompanionTurn> _messages = [];
  CompanionSignals _signals = const CompanionSignals();
  int _currentStepIndex = 0;
  bool _isStreaming = false;
  int _turnCounter = 0;
  bool _bootstrapped = false;
  bool _completed = false;
  // Captured at bootstrap so async work survives per-widget unmount races
  // (e.g. the chip widget that triggered an advance is gone by the time we
  // reach the next opener).
  BuildContext? _screenContext;
  LocaleProvider? _localeProvider;

  List<CompanionTurn> get messages => List.unmodifiable(_messages);
  CompanionSignals get signals => _signals;
  int get currentStepIndex => _currentStepIndex;
  bool get isStreaming => _isStreaming;
  bool get completed => _completed;
  ChatStepDef? get activeStep =>
      (_currentStepIndex >= 0 && _currentStepIndex < _steps.length) ? _steps[_currentStepIndex] : null;
  bool get acceptsTypedAnswer => activeStep?.acceptsTypedAnswer ?? false;
  bool get canSkip => activeStep?.skippable ?? false;

  String _nextTurnId() => 't${++_turnCounter}';

  Future<void> bootstrap(BuildContext context) async {
    if (_bootstrapped) return;
    _bootstrapped = true;
    _screenContext = context;
    _localeProvider = Provider.of<LocaleProvider>(context, listen: false);
    final prefs = await SharedPreferences.getInstance();
    if (!context.mounted) return;
    final raw = prefs.getString(_kStateKey);
    if (raw != null) {
      try {
        final json = jsonDecode(raw) as Map<String, dynamic>;
        _signals = CompanionSignals.fromJson(json['signals'] as Map<String, dynamic>? ?? {});
        final savedIndex = (json['currentStepIndex'] as int?) ?? 0;
        _currentStepIndex = savedIndex.clamp(0, _steps.length - 1);
        _completed = (json['completed'] as bool?) ?? false;
        _replayHistory(context);
      } catch (_) {
        _currentStepIndex = 0;
      }
    }
    if (_messages.isEmpty) {
      _postCurrentStepOpener(context);
    }
    notifyListeners();
  }

  void _replayHistory(BuildContext context) {
    for (int i = 0; i < _currentStepIndex; i++) {
      final step = _steps[i];
      _messages.add(AssistantTextTurn(id: _nextTurnId(), text: step.fallbackOpener(context, _signals)));
      final summary = _summaryForReplay(context, step);
      if (summary != null) {
        _messages.add(UserTextTurn(id: _nextTurnId(), text: summary));
      }
    }
    if (!_completed) _postCurrentStepOpener(context);
  }

  String? _summaryForReplay(BuildContext context, ChatStepDef step) {
    switch (step.id) {
      case OnboardingStepId.name:
        return _signals.preferredName;
      case OnboardingStepId.language:
        final id = _signals.language;
        if (id == null) return null;
        return kLanguageLabelById[id] ?? id;
      case OnboardingStepId.microphone:
      case OnboardingStepId.notifications:
      case OnboardingStepId.backgroundActivity:
      case OnboardingStepId.location:
        return step.summarize(context, 'granted');
      case OnboardingStepId.device:
        return _signals.hasDevice == true ? 'connect later' : 'skip for now';
      case OnboardingStepId.speechProfile:
        return step.summarize(context, _signals.speechProfileCaptured == true);
      case OnboardingStepId.acknowledge:
        return null;
    }
  }

  Future<void> _postCurrentStepOpener(BuildContext context) async {
    final step = activeStep;
    if (step == null) return;
    final assistantId = _nextTurnId();
    _messages.add(AssistantTextTurn(id: assistantId, text: '', streaming: true));
    notifyListeners();

    _isStreaming = true;
    final fullText = step.fallbackOpener(context, _signals);
    final stream = _streamOpener(fullText);
    final buffer = StringBuffer();
    await for (final chunk in stream) {
      buffer.write(chunk);
      final idx = _messages.indexWhere((m) => m.id == assistantId);
      if (idx >= 0) {
        _messages[idx] = AssistantTextTurn(id: assistantId, text: buffer.toString(), streaming: true);
        notifyListeners();
      }
    }
    final idx = _messages.indexWhere((m) => m.id == assistantId);
    if (idx >= 0) {
      _messages[idx] = AssistantTextTurn(id: assistantId, text: fullText, streaming: false);
    }
    _isStreaming = false;
    _messages.add(WidgetTurn(id: _nextTurnId(), stepId: step.id.name));
    notifyListeners();
  }

  /// v1: yields the canned opener in 2-3 chunks over ~500ms.
  /// Later: swap for a real Claude/Gemini stream.
  Stream<String> _streamOpener(String text) async* {
    final words = text.split(' ');
    final chunks = <String>[];
    if (words.length <= 3) {
      chunks.add(text);
    } else {
      final mid = (words.length / 2).floor();
      chunks
        ..add('${words.sublist(0, mid).join(' ')} ')
        ..add(words.sublist(mid).join(' '));
    }
    for (final c in chunks) {
      await Future.delayed(const Duration(milliseconds: 220));
      yield c;
    }
  }

  Future<void> submitTypedAnswer(BuildContext context, String value) async {
    final step = activeStep;
    if (step == null || !step.acceptsTypedAnswer) return;
    final trimmed = value.trim();
    if (trimmed.isEmpty) return;

    _messages.add(UserTextTurn(id: _nextTurnId(), text: trimmed));
    _capture(step, trimmed);
    await _advance(context);
  }

  Future<void> reportWidgetCapture(BuildContext context, String widgetTurnId, dynamic capturedValue) async {
    final step = activeStep;
    if (step == null) return;
    final widgetTurn = _messages.firstWhere(
      (m) => m is WidgetTurn && m.id == widgetTurnId,
      orElse: () => WidgetTurn(id: '', stepId: ''),
    );
    if (widgetTurn is WidgetTurn && widgetTurn.id.isNotEmpty) {
      widgetTurn.captured = true;
      final summary = step.summarize(context, capturedValue);
      widgetTurn.capturedSummary = summary;
      if (summary.isNotEmpty) {
        _messages.add(UserTextTurn(id: _nextTurnId(), text: summary));
      }
    }
    _capture(step, capturedValue);
    await _advance(context);
  }

  Future<void> skipCurrent(BuildContext context) async {
    final step = activeStep;
    if (step == null || !step.skippable) return;
    _messages.add(UserTextTurn(id: _nextTurnId(), text: step.summarize(context, 'skipped')));
    _capture(step, 'skipped');
    await _advance(context);
  }

  void _capture(ChatStepDef step, dynamic value) {
    switch (step.id) {
      case OnboardingStepId.name:
        if (value is String) _signals = _signals.copyWith(preferredName: value);
        break;
      case OnboardingStepId.language:
        if (value is String) {
          _signals = _signals.copyWith(language: value);
          _localeProvider?.setFromLanguageId(value);
        }
        break;
      case OnboardingStepId.device:
        _signals = _signals.copyWith(hasDevice: value == 'connect later');
        break;
      case OnboardingStepId.speechProfile:
        _signals = _signals.copyWith(speechProfileCaptured: value == true);
        break;
      default:
        break;
    }
  }

  Future<void> _advance(BuildContext _) async {
    if (_currentStepIndex >= _steps.length - 1) {
      _completed = true;
      await _persist();
      notifyListeners();
      return;
    }
    _currentStepIndex++;
    await _persist();
    notifyListeners();
    await Future.delayed(const Duration(milliseconds: 320));
    final screen = _screenContext;
    if (screen != null && screen.mounted) {
      await _postCurrentStepOpener(screen);
    }
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _kStateKey,
      jsonEncode({
        'currentStepIndex': _currentStepIndex,
        'signals': _signals.toJson(),
        'completed': _completed,
      }),
    );
  }

  Future<void> reset() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kStateKey);
    _messages.clear();
    _signals = const CompanionSignals();
    _currentStepIndex = 0;
    _completed = false;
    _turnCounter = 0;
    _bootstrapped = false;
    _isStreaming = false;
    await _localeProvider?.reset();
    notifyListeners();
  }
}
