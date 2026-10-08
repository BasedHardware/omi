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
class NativeModalResult {
  const NativeModalResult(this.action, this.values);
  final String? action;
  final Map<String, Object?> values;
}

const _presentationChannel = MethodChannel('com.omi.native_ui/config');
int _nextPresentationId = 0;

Future<NativeModalResult?> showIosNativeModal(
  BuildContext context, {
  required String title,
  required List<NativeRow> actions,
  List<NativeSection> sections = const [],
  String cancelId = 'cancel',
  bool alert = false,
  bool dismissible = true,
  bool guardEdits = false,
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
    ticket.leave();
  });
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
      if (!context.mounted || !current() || response == null) return const NativeModalResult(null, {});
      final action = response['action'];
      final values = response['values'];
      // A reply that names no current action, or carries a value its row would refuse, mutates nothing.
      if (action is! String || !actions.any((row) => row.id == action && row.enabled) || values is! Map) {
        return const NativeModalResult(null, {});
      }
      final accepted = <String, Object?>{};
      for (final row in sections.expand((section) => section.rows)) {
        if (!['text', 'toggle', 'choice', 'color', 'date'].contains(row.kind)) continue;
        if (!values.containsKey(row.id) || !row.accepts(values[row.id])) return const NativeModalResult(null, {});
        accepted[row.id] = values[row.id];
      }
      return NativeModalResult(action == cancelId ? null : action, accepted);
    });
    // It never presented. An unmounted caller runs nothing; a mounted one was dropped or lost its
    // session, so it is cancelled rather than sent to a Flutter dialog built for the previous owner.
    if (result == null && context.mounted) return const NativeModalResult(null, {});
    return result;
  } on PlatformException catch (error) {
    // The presenter refused this request; the caller keeps its complete Flutter dialog.
    if (error.code == 'invalid_native_presentation') return null;
    rethrow;
  } on MissingPluginException {
    // An older installed host retains its complete existing dialog.
    return null;
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

  /// Drops the request while it waits, so it never presents. A presented request is dismissed
  /// instead, and answers once Swift confirms it or the grace period ends.
  void leave() {
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
    ticket._release();
  }
}

/// Invokes 'present' under the watchdog described above.
Future<Map<String, Object?>?> _presentWatched(BuildContext context, _PresentationTicket ticket, bool Function() current,
    int id, Map<String, Object?> arguments) async {
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
    if (!context.mounted || !current()) dismiss();
  });
  final hold = Timer(_maximumHold, ticket._release);
  unawaited(_presentationChannel.invokeMapMethod<String, Object?>('present', arguments).then((value) {
    if (!response.isCompleted) response.complete(value);
  }, onError: (Object error, StackTrace stack) {
    if (!response.isCompleted) response.completeError(error, stack);
  }));
  try {
    return await response.future;
  } finally {
    watchdog.cancel();
    grace?.cancel();
    hold.cancel();
    ticket._dismiss = null;
  }
}

Future<void> _dismiss(int id) async {
  try {
    await _presentationChannel.invokeMethod<void>('dismissPresentation', id);
  } on MissingPluginException {
    // An older host has no temporary native presentation to dismiss.
  }
}
