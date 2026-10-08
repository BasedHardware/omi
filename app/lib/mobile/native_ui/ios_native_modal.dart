import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'ios_native_home.dart';
import 'ios_native_surface.dart';

/// A native presentation returns input to the existing Dart owner; it never saves it itself.
///
/// [showIosNativeModal] answers null when the native presentation was not used: the host is
/// unsupported, a row cannot be represented, the host refused it, or the caller's context unmounted
/// while it waited. The caller then runs its Flutter path. A cancellation, an invalidation, an
/// account-session change (even before presenting, so no unfenced Flutter dialog opens for the next
/// owner) or a forged reply is a result whose [action] is null and carries no values.
///
/// [reason] says how a presentation that was used ended; [action] is null and [values] empty for
/// every reason but 'action':
/// - 'action': the person chose an enabled action other than the cancel action, named by [action];
/// - 'cancel': the person chose the cancel action, or an older host replied nil;
/// - 'dismissed': it left the screen without a choice (a swipe or scrim tap, UIKit failing to show
///   it, another owner removing it), or the reply was one this request cannot accept;
/// - 'programmatic': the caller's dismissSignal withdrew it;
/// - 'invalidated': the account session changed before or while it was presented;
/// - 'unmounted': the caller's context unmounted while it was presented. A request whose context
///   unmounts before it presents answers null instead, like any request that did not present.
///
/// Swift reports 'action', 'cancel' and 'dismissed' in its completion, and 'programmatic' whenever
/// it closes a presentation for 'dismissPresentation'. Dart alone decides why it asked: the
/// dismissSignal ('programmatic'), a session change ('invalidated') or an unmounted caller
/// ('unmounted'). That reason replaces Swift's confirmation and any native reply after it.
class NativeModalResult {
  const NativeModalResult(this.action, this.values, {String? reason})
      : assert(action == null || reason == null || reason == 'action'),
        reason = reason ?? (action == null ? 'cancel' : 'action');
  final String? action;
  final Map<String, Object?> values;
  final String reason;
}

const _presentationChannel = MethodChannel('com.omi.native_ui/config');
int _nextPresentationId = 0;

/// When [dismissSignal] completes before a result, the owner withdraws the request: a waiting request
/// never presents, and a presented one is dismissed through 'dismissPresentation'. Either way the
/// answer is a 'programmatic' result, and a native reply that arrives afterwards is discarded. A
/// signal that completes after the result is ignored.
Future<NativeModalResult?> showIosNativeModal(
  BuildContext context, {
  required String title,
  required List<NativeRow> actions,
  List<NativeSection> sections = const [],
  String cancelId = 'cancel',
  bool alert = false,
  bool dismissible = true,
  bool guardEdits = false,
  Future<void>? dismissSignal,
}) async {
  if (!iosSwiftUiEnabled && !IosNativeSurface.debugNativeHostForTest || !await supportsNativePresentation()) {
    return null;
  }
  if (!context.mounted) return null;
  final rows = [...actions, ...sections.expand((section) => section.rows)];
  // An unrepresentable request keeps the caller's complete Flutter dialog.
  if (rows.any((row) => !row.valid) || rows.map((row) => row.id).toSet().length != rows.length) return null;
  final ticket = _PresentationTicket();
  final owner = AuthService.instance.captureSessionSnapshot();
  var sessionValid = true;
  bool current() => sessionValid && (owner == null || AuthService.instance.isSessionSnapshotCurrent(owner));
  final subscription = AuthService.instance.sessionGenerationEvents.listen((_) {
    sessionValid = false;
    ticket.leave('invalidated');
  });
  void withdraw(Object? _) => ticket.leave('programmatic');
  unawaited(dismissSignal?.then(withdraw, onError: withdraw));
  // The request did not reach a native result: the owner's own withdrawal, or a session change so no
  // Flutter dialog built for the previous owner opens for the next. Otherwise null, the Flutter path.
  NativeModalResult? withdrawn() {
    if (ticket._cause == 'programmatic') return const NativeModalResult(null, {}, reason: 'programmatic');
    if (!context.mounted) return null;
    if (ticket._cause != null || !current()) return const NativeModalResult(null, {}, reason: 'invalidated');
    return null;
  }

  try {
    final result = await _inPresentationOrder(ticket, () => context.mounted && current(), () async {
      final id = _nextPresentationId++;
      final l10n = context.l10n;
      final response = await _presentWatched(context, ticket, current, id, {
        'requestId': id,
        'cancelId': cancelId,
        'alert': alert,
        'dismissible': dismissible,
        'guardEdits': guardEdits,
        'discard': {
          'title': l10n.discardChangesTitle,
          'message': l10n.discardChangesMessage,
          'confirm': l10n.discard,
          'cancel': l10n.keepEditing,
        },
        'snapshot': {
          'version': 1,
          'revision': 0,
          'title': title,
          'appearance': context.read<AppearanceProvider>().mode.name,
          'locale': Localizations.localeOf(context).toLanguageTag(),
          'direction': Directionality.of(context).name,
          'loading': false,
          'failed': false,
          'empty': '',
          'sections': [
            for (final section in sections)
              {
                ...section.projection,
                'rows': [
                  for (final row in section.rows) {...row.projection, 'enabled': row.enabled}
                ],
              },
          ],
          'toolbar': actions.map((row) => {...row.projection, 'enabled': row.enabled}).toList(),
          'searchEnabled': false,
          'searchValue': '',
          'searchPlaceholder': '',
          'refreshEnabled': false,
          'error': l10n.failedToSaveCheckConnection,
          'retry': l10n.retry,
          'loadingLabel': l10n.loading,
        },
      });
      // Dart's own reason replaces whatever Swift answers after it.
      final cause = ticket._cause;
      if (cause != null) return NativeModalResult(null, const {}, reason: cause);
      if (!context.mounted) return const NativeModalResult(null, {}, reason: 'unmounted');
      if (!current()) return const NativeModalResult(null, {}, reason: 'invalidated');
      // An older host answers a cancellation with nil.
      if (response == null) return const NativeModalResult(null, {});
      return _nativeOutcome(response, actions, sections, cancelId);
    });
    // It never presented. An unmounted caller runs nothing; a mounted one was withdrawn or lost its
    // session, so it is not sent to a Flutter dialog built for the previous owner.
    return result ?? withdrawn();
  } on PlatformException catch (error) {
    // The presenter refused this request; the caller keeps its complete Flutter dialog.
    if (error.code == 'invalid_native_presentation') return withdrawn();
    rethrow;
  } on MissingPluginException {
    // An older installed host retains its complete existing dialog.
    return withdrawn();
  } finally {
    // Cancelling completes at once; awaiting its shared null future would stall fake-async tests.
    unawaited(subscription.cancel());
  }
}

/// Native presentations run one at a time, in request order: the Swift presenter holds a single
/// active presentation and refuses another. Only requests that passed the flag, platform and
/// support checks queue here, so the default and Android builds never wait.
///
/// A request's slot is released, letting the next request present, when:
/// 1. Swift completes its presentation, with a result or an error;
/// 2. it leaves before presenting: it was dropped (a session change, or a later dismissal
///    request), or its context unmounted or its session changed while it waited. An unmounted
///    caller then receives null; any other receives a cancellation, so nothing runs for a new owner;
/// 3. the watchdog sees the presenting caller's context unmount or its session change. Dart asks
///    Swift to dismiss the presentation and releases the slot on Swift's completion or after
///    [_dismissGrace], whichever comes first; the caller then receives a cancellation;
/// 4. at the latest [_maximumHold] after presenting. A lost Swift completion can therefore delay
///    later presentations but never block them: the next request presents if Swift is free and
///    otherwise takes its Flutter path. Nothing is dismissed on a timer, because a person may keep
///    an editor open for as long as they need.
///
/// Rules 2 and 3 also apply when the owner withdraws a request (a modal's dismissSignal, or
/// [NativeActivity.dismiss]); the cancellation then carries the withdrawal's reason. An activity is
/// the one presentation with a timer: it ends after [_activityLifetime].
const _watchdogInterval = Duration(milliseconds: 500);
const _dismissGrace = Duration(seconds: 2);
const _maximumHold = Duration(minutes: 10);

/// Requests in order; the first one holds the slot.
final _presentationOrder = <_PresentationTicket>[];

/// A request's place in the presentation order.
class _PresentationTicket {
  final _turn = Completer<void>();
  final _dropped = Completer<void>();
  bool _presenting = false;
  bool _released = false;
  VoidCallback? _dismiss;

  /// Set once the outcome no longer depends on Dart: Swift replied, or the request left the queue.
  bool _decided = false;

  /// Why Dart withdrew this request, if it did: 'programmatic', 'invalidated' or 'unmounted'. The
  /// first reason wins.
  String? _cause;

  /// Drops the request while it waits, so it never presents. A presented request is dismissed
  /// instead, and answers once Swift confirms it or the grace period ends. Once the outcome is
  /// decided, leaving changes nothing.
  void leave([String cause = 'invalidated']) {
    if (_decided) return;
    _cause ??= cause;
    if (_presenting) {
      _dismiss?.call();
    } else if (!_dropped.isCompleted) {
      _dropped.complete();
    }
  }

  /// Gives up this request's place; when it held the slot, the next request takes its turn.
  void _release() {
    if (_released) return;
    _released = true;
    final held = _presentationOrder.isNotEmpty && identical(_presentationOrder.first, this);
    _presentationOrder.remove(this);
    if (held) _presentationOrder.firstOrNull?._takeTurn();
  }

  void _takeTurn() {
    if (!_turn.isCompleted) _turn.complete();
  }
}

/// Waits for every earlier presentation, then runs [present] while [wanted] still holds. Answers
/// null when the request left the queue without presenting.
Future<T?> _inPresentationOrder<T>(
    _PresentationTicket ticket, bool Function() wanted, Future<T> Function() present) async {
  _presentationOrder.add(ticket);
  if (identical(_presentationOrder.first, ticket)) ticket._takeTurn();
  try {
    await Future.any([ticket._turn.future, ticket._dropped.future]);
    if (ticket._dropped.isCompleted || !wanted()) return null;
    ticket._presenting = true;
    return await present();
  } finally {
    ticket._decided = true;
    ticket._release();
  }
}

/// Invokes [method] ('present' or 'presentActivity') under the watchdog described above. A [lifetime]
/// withdraws the presentation once it has been up that long.
Future<Map<String, Object?>?> _presentWatched(
    BuildContext context, _PresentationTicket ticket, bool Function() current, int id, Map<String, Object?> arguments,
    {String method = 'present', Duration? lifetime}) async {
  final response = Completer<Map<String, Object?>?>();
  Timer? grace;
  void dismiss() {
    if (grace != null) return;
    unawaited(_dismiss(id));
    grace = Timer(_dismissGrace, () {
      ticket._release();
      if (!response.isCompleted) response.complete(null);
    });
  }

  ticket._dismiss = dismiss;
  final watchdog = Timer.periodic(_watchdogInterval, (_) {
    if (!context.mounted) {
      ticket.leave('unmounted');
    } else if (!current()) {
      ticket.leave('invalidated');
    }
  });
  final hold = Timer(_maximumHold, ticket._release);
  final expiry = lifetime == null ? null : Timer(lifetime, () => ticket.leave('programmatic'));
  unawaited(_presentationChannel.invokeMapMethod<String, Object?>(method, arguments).then((value) {
    ticket._decided = true;
    if (!response.isCompleted) response.complete(value);
  }, onError: (Object error, StackTrace stack) {
    ticket._decided = true;
    if (!response.isCompleted) response.completeError(error, stack);
  }));
  try {
    return await response.future;
  } finally {
    watchdog.cancel();
    grace?.cancel();
    hold.cancel();
    expiry?.cancel();
    ticket._dismiss = null;
  }
}

/// Maps a native reply to its outcome. A reply that names no current action, carries a value its
/// row would refuse, or reports an unknown reason mutates nothing and reads as 'dismissed'.
NativeModalResult _nativeOutcome(
    Map<String, Object?> response, List<NativeRow> actions, List<NativeSection> sections, String cancelId) {
  const unaccepted = NativeModalResult(null, {}, reason: 'dismissed');
  final action = response['action'];
  final reason = response['reason'];
  if (action == null) {
    return switch (reason) {
      null || 'cancel' => const NativeModalResult(null, {}),
      'programmatic' => const NativeModalResult(null, {}, reason: 'programmatic'),
      _ => unaccepted,
    };
  }
  final values = response['values'];
  if (action is! String || !actions.any((row) => row.id == action && row.enabled) || values is! Map) {
    return unaccepted;
  }
  // An older host reports a system alert's cancel button as its action.
  if (action == cancelId) return reason == null || reason == 'cancel' ? const NativeModalResult(null, {}) : unaccepted;
  if (reason != null && reason != 'action') return unaccepted;
  final accepted = <String, Object?>{};
  for (final row in sections.expand((section) => section.rows)) {
    if (!['text', 'toggle', 'choice', 'color', 'date'].contains(row.kind)) continue;
    if (!values.containsKey(row.id) || !row.accepts(values[row.id])) return unaccepted;
    accepted[row.id] = values[row.id];
  }
  return NativeModalResult(action, accepted);
}

Future<void> _dismiss(int id) async {
  try {
    await _presentationChannel.invokeMethod<void>('dismissPresentation', id);
  } on MissingPluginException {
    // An older host has no temporary native presentation to dismiss.
  }
}

/// The longest a native activity stays up. A caller must dismiss its activity before it awaits a
/// route, a sheet or another native presentation: the overlay covers every Flutter route, and every
/// later native presentation waits behind it in the presentation order. An activity left up past
/// this ends on its own ('programmatic'), so such a mistake costs time but never deadlocks the app.
const _activityLifetime = Duration(seconds: 120);

/// The rule Swift applies to an activity label: 1 to 200 characters.
bool _validActivityLabel(String label) => label.isNotEmpty && label.characters.length <= 200;

/// A blocking native activity indicator; its caller removes it with [dismiss] when the work ends.
class NativeActivity {
  NativeActivity._(this._ticket);

  final _PresentationTicket _ticket;
  final _closed = Completer<String>();
  Future<void>? _dismissal;

  /// Completes once the activity is gone, with why: 'programmatic' ([dismiss], or its maximum
  /// lifetime), 'invalidated' (the account session changed), 'unmounted' (the caller's context
  /// unmounted) or 'dismissed' (the host refused it, or UIKit or another owner removed it). A
  /// caller whose work is still running when this answers 'dismissed' has no overlay any more and
  /// may show its Flutter spinner instead.
  Future<String> get closed => _closed.future;

  /// Removes the activity, or drops it while it still waits for its turn. Idempotent: every call
  /// answers the same future, which completes once the overlay is gone and the next native
  /// presentation may take its turn.
  Future<void> dismiss() => _dismissal ??= () async {
        _ticket.leave('programmatic');
        await _closed.future;
      }();

  void _finish(String reason) {
    if (!_closed.isCompleted) _closed.complete(reason);
  }
}

/// Shows a blocking native activity indicator with [label] over the whole app.
///
/// Answers null when native presentation is unavailable or [label] is empty or longer than 200
/// characters; the caller then shows its Flutter spinner dialog. Otherwise the handle returns at
/// once and the activity takes its turn in the shared presentation order: it waits for an earlier
/// presentation, and a later one (an alert, say) waits for it. It ends through
/// [NativeActivity.dismiss], an account-session change, the caller's context unmounting, or after
/// [_activityLifetime]. Dismiss it before awaiting any route, sheet or other native presentation.
///
/// ```dart
/// final activity = await showIosNativeActivity(context, label: context.l10n.loading);
/// if (activity == null) showFlutterSpinner();
/// try {
///   await work();
/// } finally {
///   await activity?.dismiss();
/// }
/// ```
Future<NativeActivity?> showIosNativeActivity(BuildContext context, {required String label}) async {
  if (!nativePresentationEnabled || !await supportsNativePresentation()) return null;
  if (!context.mounted || !_validActivityLabel(label)) return null;
  final ticket = _PresentationTicket();
  final activity = NativeActivity._(ticket);
  final owner = AuthService.instance.captureSessionSnapshot();
  var sessionValid = true;
  bool current() => sessionValid && (owner == null || AuthService.instance.isSessionSnapshotCurrent(owner));
  final request = {
    'label': label,
    'appearance': context.read<AppearanceProvider>().mode.name,
    'locale': Localizations.localeOf(context).toLanguageTag(),
    'direction': Directionality.of(context).name,
  };
  final subscription = AuthService.instance.sessionGenerationEvents.listen((_) {
    sessionValid = false;
    ticket.leave('invalidated');
  });
  Future<String> run() async {
    try {
      final reason = await _inPresentationOrder(ticket, () => context.mounted && current(), () async {
        final id = _nextPresentationId++;
        // The keyboard window sits above the overlay; close it so nothing beneath takes input.
        FocusManager.instance.primaryFocus?.unfocus();
        final response = await _presentWatched(context, ticket, current, id, {'requestId': id, ...request},
            method: 'presentActivity', lifetime: _activityLifetime);
        if (ticket._cause case final cause?) return cause;
        if (!context.mounted) return 'unmounted';
        if (!current()) return 'invalidated';
        // Only Dart ends an activity on purpose; otherwise UIKit or another owner removed it.
        return response?['reason'] == 'programmatic' ? 'programmatic' : 'dismissed';
      });
      return reason ?? ticket._cause ?? (context.mounted ? 'invalidated' : 'unmounted');
    } on PlatformException {
      // The presenter refused it; the work goes on without an indicator.
      return ticket._cause ?? 'dismissed';
    } on MissingPluginException {
      return ticket._cause ?? 'dismissed';
    } finally {
      unawaited(subscription.cancel());
    }
  }

  unawaited(run().then(activity._finish, onError: (Object error, StackTrace stack) {
    activity._finish('dismissed');
    FlutterError.reportError(FlutterErrorDetails(exception: error, stack: stack, library: 'native ui'));
  }));
  return activity;
}
