import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

/// The native counterparts of [OmiFeedbackKind].
enum NativeToastKind { confirm, info, error, undo, progress }

/// How a native toast ended. Only [action] means the reader took the toast's action.
enum NativeToastOutcome { action, closed, swiped, timeout, replaced, invalidated }

/// The SF Symbols a toast may show; 'progress' is the system spinner.
const nativeToastSymbols = {
  'checkmark.circle.fill',
  'info.circle',
  'exclamationmark.circle.fill',
  'trash',
  'person',
  'tv',
  'progress',
};

/// Icons OmiFeedback callers pass, with their native symbols. Today only Icons.person_outline and
/// Icons.tv_outlined are passed (speaker_tag_prompt_card.dart); delete glyphs show the trash. Any other icon
/// shows its kind's default symbol.
final _iconSymbols = <IconData, String>{
  Icons.person_outline: 'person',
  Icons.tv_outlined: 'tv',
  Icons.delete: 'trash',
  Icons.delete_outline: 'trash',
  Icons.delete_outline_rounded: 'trash',
  Icons.delete_forever: 'trash',
};

/// The symbol for a toast of [kind] that OmiFeedback would draw with [icon].
String nativeToastSymbol(NativeToastKind kind, IconData? icon) =>
    _iconSymbols[icon] ??
    switch (kind) {
      NativeToastKind.confirm => 'checkmark.circle.fill',
      NativeToastKind.info => 'info.circle',
      NativeToastKind.error => 'exclamationmark.circle.fill',
      NativeToastKind.undo => 'trash',
      NativeToastKind.progress => 'progress',
    };

/// The only duration a toast of [kind] may have: its [OmiFeedbackTiming].
Duration nativeToastDuration(NativeToastKind kind) => switch (kind) {
      NativeToastKind.confirm => OmiFeedbackTiming.confirm,
      NativeToastKind.info => OmiFeedbackTiming.info,
      NativeToastKind.error => OmiFeedbackTiming.error,
      NativeToastKind.undo => OmiFeedbackTiming.undo,
      NativeToastKind.progress => OmiFeedbackTiming.progress,
    };

var _nextToastRequestId = 0;

/// Identifies this Dart process to the presenter, which outlives an engine restart: a new token starts a
/// new request-id sequence there instead of refusing the restarted counter.
final String _toastSession = () {
  final random = Random.secure();
  return [for (var part = 0; part < 4; part++) random.nextInt(1 << 32).toRadixString(16).padLeft(8, '0')].join();
}();

/// One toast, as presentation values only. OmiFeedback keeps the callbacks and learns how the toast ended.
class NativeToastRequest {
  NativeToastRequest({
    required this.kind,
    required this.message,
    this.actionLabel,
    this.closeLabel,
    required this.durationMs,
    required this.symbol,
    required this.bottomClearance,
    required this.appearance,
    required this.locale,
    required this.direction,
  }) : requestId = _nextToastRequestId++;

  /// Strictly increasing within this process.
  final int requestId;
  final NativeToastKind kind;
  final String message;

  /// Required for undo; allowed for error only when it has an action.
  final String? actionLabel;

  /// The accessibility label of the close button, which only an error has.
  final String? closeLabel;
  final int durationMs;
  final String symbol;

  /// Extra space above the safe area that the visible shell needs, as for the SnackBar margin.
  final double bottomClearance;
  final String appearance, locale, direction;

  /// Whether no toast was requested after this one.
  bool get isLatest => requestId == _nextToastRequestId - 1;

  Map<String, Object?> get projection => {
        'requestId': requestId,
        'session': _toastSession,
        'kind': kind.name,
        'message': message,
        'actionLabel': actionLabel,
        'closeLabel': closeLabel,
        'durationMs': durationMs,
        'symbol': symbol,
        'bottomClearance': bottomClearance,
        'appearance': appearance,
        'locale': locale,
        'direction': direction,
      };

  /// The same rules as Swift's NativeToastRequest.validate().
  bool get valid {
    bool label(String? value) => value == null || value.characters.isNotEmpty && value.characters.length <= 40;
    final length = message.characters.length;
    return requestId >= 0 &&
        _toastSession.isNotEmpty &&
        _toastSession.length <= 64 &&
        length >= 1 &&
        length <= 1000 &&
        !message.contains('\u0000') &&
        durationMs == nativeToastDuration(kind).inMilliseconds &&
        nativeToastSymbols.contains(symbol) &&
        (symbol == 'progress') == (kind == NativeToastKind.progress) &&
        (kind == NativeToastKind.undo ? actionLabel != null : kind == NativeToastKind.error || actionLabel == null) &&
        (closeLabel != null) == (kind == NativeToastKind.error) &&
        label(actionLabel) &&
        label(closeLabel) &&
        bottomClearance.isFinite &&
        bottomClearance >= 0 &&
        bottomClearance <= 240 &&
        const ['system', 'light', 'dark'].contains(appearance) &&
        locale.isNotEmpty &&
        const ['ltr', 'rtl'].contains(direction);
  }
}

/// Whether OmiFeedback presents native toasts. It turns on only after [supportsIosSwiftUi] confirmed the
/// SwiftUI renderer, which already requires the preview flag on iOS, so the default and Android builds
/// never touch the config channel for feedback.
abstract final class NativeFeedbackHost {
  static bool _supported = false;
  static bool _debugActive = false;

  static bool get active => _supported || kDebugMode && _debugActive;

  /// Called by [supportsIosSwiftUi] once the host confirmed the renderer.
  static void confirmSupported() {
    _supported = true;
    _watchSession();
  }

  /// Debug-only: hermetic tests present toasts through a mocked config channel.
  @visibleForTesting
  static set debugActiveForTest(bool value) {
    assert(kDebugMode, 'debugActiveForTest is a debug-only seam');
    _debugActive = value;
  }
}

const _config = MethodChannel('com.omi.native_ui/config');

/// Swift answers once the toast ends; a lost answer resolves as a timeout this long after the toast's own.
const _outcomeGrace = Duration(seconds: 2);

var _lastSentRequestId = -1;
var _sessionEpoch = 0;
StreamSubscription<int>? _sessionChanges;

/// Watches the account session for the rest of the process, from the support check or the first toast: a
/// change dismisses the toast.
void _watchSession() {
  _sessionChanges ??= AuthService.instance.sessionGenerationEvents.listen((_) {
    _sessionEpoch++;
    unawaited(dismissIosNativeToast());
  });
}

/// Presents [request] natively and completes when the toast ends. Null means it was not presented: the
/// host is inactive or older, or [request] is invalid or older than one already sent, so the caller shows
/// its Flutter toast. An account-session change dismisses the toast; an answer after one is
/// [NativeToastOutcome.invalidated], so no action runs for the next owner.
Future<NativeToastOutcome?> showIosNativeToast(NativeToastRequest request) async {
  if (!NativeFeedbackHost.active || !request.valid || request.requestId <= _lastSentRequestId) return null;
  _lastSentRequestId = request.requestId;
  _watchSession();
  final epoch = _sessionEpoch;
  final answer = Completer<Object?>();
  final watchdog = Timer(Duration(milliseconds: request.durationMs) + _outcomeGrace, () {
    if (answer.isCompleted) return;
    answer.complete(NativeToastOutcome.timeout.name);
    if (request.requestId == _lastSentRequestId) unawaited(dismissIosNativeToast());
  });
  unawaited(_config.invokeMethod<Object?>('toast', request.projection).then((reply) {
    if (!answer.isCompleted) answer.complete(reply);
  }, onError: (Object error, StackTrace stack) {
    if (!answer.isCompleted) answer.completeError(error, stack);
  }));
  try {
    final reply = await answer.future;
    if (epoch != _sessionEpoch) return NativeToastOutcome.invalidated;
    // An unknown answer never counts as the reader's action.
    return NativeToastOutcome.values.asNameMap()[reply] ?? NativeToastOutcome.invalidated;
  } on PlatformException catch (error) {
    // The presenter refused the request; the caller keeps its Flutter toast.
    if (error.code == 'invalid_native_toast') return null;
    rethrow;
  } on MissingPluginException {
    // An older host has no native toast.
    return null;
  } finally {
    watchdog.cancel();
  }
}

/// Dismisses the native toast, which then ends as [NativeToastOutcome.invalidated].
Future<void> dismissIosNativeToast() async {
  if (!NativeFeedbackHost.active) return;
  try {
    await _config.invokeMethod<void>('dismissToast');
  } on MissingPluginException {
    // An older host has no native toast to dismiss.
  } on PlatformException {
    // Nothing is left to withdraw; callers run this unawaited.
  }
}
