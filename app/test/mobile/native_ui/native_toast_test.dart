import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_feedback.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_main_navigation.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

import '../../widgets/ui_feedback/harness.dart';
import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');

/// The config channel's toast presenter. [reply] answers 'toast' at once; without it each toast waits in
/// [pending] until the test ends it, as Swift does when the toast goes away.
class _Presenter {
  _Presenter._();

  final calls = <MethodCall>[];
  final pending = <Completer<Object?>>[];
  Object? Function(MethodCall call)? reply;

  static _Presenter install() {
    final presenter = _Presenter._();
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(_config, (call) async {
      presenter.calls.add(call);
      if (call.method != 'toast') return null;
      final reply = presenter.reply;
      if (reply != null) return reply(call);
      final completer = Completer<Object?>();
      presenter.pending.add(completer);
      return completer.future;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
    return presenter;
  }

  List<Map> get toasts => [
        for (final call in calls)
          if (call.method == 'toast') call.arguments as Map
      ];
  int get dismissals => calls.where((call) => call.method == 'dismissToast').length;

  /// Ends the oldest waiting toast the way Swift reports it.
  void end(String outcome) => pending.removeAt(0).complete(outcome);
}

/// Turns on native feedback for one test, with a signed-in synthetic owner settled first.
_Presenter _activate() {
  NativeTestHost.installOwner();
  NativeFeedbackHost.debugActiveForTest = true;
  addTearDown(() => NativeFeedbackHost.debugActiveForTest = false);
  return _Presenter.install();
}

NativeToastRequest _request(
  NativeToastKind kind, {
  String message = 'Task deleted',
  String? actionLabel,
  String? closeLabel,
  int? durationMs,
  String? symbol,
  double bottomClearance = 0,
  String appearance = 'dark',
  String direction = 'ltr',
}) =>
    NativeToastRequest(
      kind: kind,
      message: message,
      actionLabel: actionLabel,
      closeLabel: closeLabel,
      durationMs: durationMs ?? nativeToastDuration(kind).inMilliseconds,
      symbol: symbol ?? nativeToastSymbol(kind, null),
      bottomClearance: bottomClearance,
      appearance: appearance,
      locale: 'en',
      direction: direction,
    );

Future<BuildContext> _pumpFeedback(WidgetTester tester) async {
  late BuildContext captured;
  await tester.pumpWidget(feedbackHarness((context) => captured = context));
  await tapTrigger(tester);
  return captured;
}

void main() {
  tearDown(() => OmiFeedback.bottomClearance = null);

  group('request validation', () {
    test('each kind has one duration, its OmiFeedbackTiming', () {
      expect(_request(NativeToastKind.confirm).durationMs, 1500);
      expect(_request(NativeToastKind.info).durationMs, 4000);
      expect(_request(NativeToastKind.error, closeLabel: 'Close').durationMs, 8000);
      expect(_request(NativeToastKind.undo, actionLabel: 'Undo').durationMs, 5000);
      expect(_request(NativeToastKind.progress).durationMs, 60000);
      for (final kind in NativeToastKind.values) {
        final action = kind == NativeToastKind.undo ? 'Undo' : null;
        final close = kind == NativeToastKind.error ? 'Close' : null;
        expect(_request(kind, actionLabel: action, closeLabel: close).valid, isTrue, reason: kind.name);
        expect(_request(kind, actionLabel: action, closeLabel: close, durationMs: 4001).valid, isFalse,
            reason: '${kind.name} with another duration');
      }
      expect(_request(NativeToastKind.confirm, durationMs: 4000).valid, isFalse);
    });

    test('actions belong to undo (required) and error (optional) only', () {
      for (final kind in [NativeToastKind.confirm, NativeToastKind.info, NativeToastKind.progress]) {
        expect(_request(kind, actionLabel: 'Undo').valid, isFalse, reason: kind.name);
      }
      expect(_request(NativeToastKind.undo).valid, isFalse, reason: 'an undo needs its label');
      expect(_request(NativeToastKind.undo, actionLabel: '').valid, isFalse);
      expect(_request(NativeToastKind.undo, actionLabel: 'u' * 41).valid, isFalse);
      expect(_request(NativeToastKind.undo, actionLabel: 'u' * 40).valid, isTrue);
      expect(_request(NativeToastKind.error, actionLabel: 'Try Again', closeLabel: 'Close').valid, isTrue);
    });

    test('only an error has a close button, and always does', () {
      expect(_request(NativeToastKind.undo, actionLabel: 'Undo', closeLabel: 'Close').valid, isFalse);
      expect(_request(NativeToastKind.info, closeLabel: 'Close').valid, isFalse);
      expect(_request(NativeToastKind.error).valid, isFalse);
    });

    test('clearance must be finite and within 0..240', () {
      for (final clearance in [double.nan, double.infinity, double.negativeInfinity, -1.0, 240.5]) {
        expect(_request(NativeToastKind.info, bottomClearance: clearance).valid, isFalse, reason: '$clearance');
      }
      expect(_request(NativeToastKind.info, bottomClearance: 240).valid, isTrue);
    });

    test('messages hold 1..1000 graphemes without U+0000', () {
      const family = '👨‍👩‍👧‍👦';
      expect(_request(NativeToastKind.info, message: family * 1000).valid, isTrue);
      expect(_request(NativeToastKind.info, message: family * 1001).valid, isFalse);
      expect(_request(NativeToastKind.info, message: '').valid, isFalse);
      expect(_request(NativeToastKind.info, message: 'a\u0000b').valid, isFalse);
    });

    test('symbols, appearance and direction come from fixed sets', () {
      expect(_request(NativeToastKind.info, symbol: 'star').valid, isFalse);
      expect(_request(NativeToastKind.info, symbol: 'progress').valid, isFalse);
      expect(_request(NativeToastKind.progress, symbol: 'info.circle').valid, isFalse);
      expect(_request(NativeToastKind.info, appearance: 'sepia').valid, isFalse);
      expect(_request(NativeToastKind.info, direction: 'up').valid, isFalse);
    });

    test('request ids strictly increase and the projection carries one session', () {
      final first = _request(NativeToastKind.info);
      final second = _request(NativeToastKind.info);
      expect(second.requestId, greaterThan(first.requestId));
      expect(first.isLatest, isFalse);
      expect(second.isLatest, isTrue);
      expect(first.projection.keys, {
        'requestId',
        'session',
        'kind',
        'message',
        'actionLabel',
        'closeLabel',
        'durationMs',
        'symbol',
        'bottomClearance',
        'appearance',
        'locale',
        'direction',
      });
      expect(first.projection['session'], isNotEmpty);
      expect(first.projection['session'], second.projection['session']);
      expect(first.projection['kind'], 'info');
    });

    test('icons map to their symbols; anything else uses the kind default', () {
      expect(nativeToastSymbol(NativeToastKind.undo, Icons.person_outline), 'person');
      expect(nativeToastSymbol(NativeToastKind.undo, Icons.tv_outlined), 'tv');
      expect(nativeToastSymbol(NativeToastKind.undo, Icons.delete_outline_rounded), 'trash');
      expect(nativeToastSymbol(NativeToastKind.undo, Icons.star), 'trash');
      expect(nativeToastSymbol(NativeToastKind.confirm, null), 'checkmark.circle.fill');
      expect(nativeToastSymbol(NativeToastKind.info, null), 'info.circle');
      expect(nativeToastSymbol(NativeToastKind.error, null), 'exclamationmark.circle.fill');
      expect(nativeToastSymbol(NativeToastKind.progress, null), 'progress');
    });
  });

  group('outcomes', () {
    testWidgets('undo resolves true for action, after onUndo ran', (tester) async {
      final presenter = _activate();
      final context = await _pumpFeedback(tester);
      final order = <String>[];
      final undone = OmiFeedback.undo(context, 'Task deleted', onUndo: () => order.add('restored'))
          .then((value) => order.add('resolved:$value'));
      await tester.pump();
      final toast = presenter.toasts.single;
      expect(toast['kind'], 'undo');
      expect(toast['actionLabel'], 'Undo');
      expect(toast['closeLabel'], isNull);
      expect(toast['durationMs'], 5000);
      expect(toast['symbol'], 'trash');
      presenter.end('action');
      await undone;
      expect(order, ['restored', 'resolved:true']);
      expect(find.byType(SnackBar), findsNothing);
    });

    for (final outcome in ['replaced', 'timeout', 'swiped', 'invalidated', 'closed', 'unexpected']) {
      testWidgets('undo resolves false for $outcome without restoring', (tester) async {
        final presenter = _activate();
        final context = await _pumpFeedback(tester);
        var restored = false;
        final undone = OmiFeedback.undo(context, 'Task deleted', onUndo: () => restored = true);
        await tester.pump();
        presenter.end(outcome);
        expect(await undone, isFalse);
        expect(restored, isFalse);
        expect(find.byType(SnackBar), findsNothing);
      });
    }

    testWidgets('an Undo whose callback throws still resolves true and reports the error', (tester) async {
      final presenter = _activate()..reply = (_) => 'action';
      final context = await _pumpFeedback(tester);
      final undone = OmiFeedback.undo(context, 'Task deleted', onUndo: () => throw StateError('restore failed'));
      await tester.pump();
      expect(await undone, isTrue);
      expect(tester.takeException(), isStateError);
      expect(presenter.toasts, hasLength(1));
    });

    testWidgets('an error runs onAction exactly once for action', (tester) async {
      final presenter = _activate()..reply = (_) => 'action';
      final context = await _pumpFeedback(tester);
      var retried = 0;
      OmiFeedback.error(context, 'Could not save', actionLabel: 'Try Again', onAction: () => retried++);
      await tester.pumpAndSettle();
      expect(retried, 1);
      final toast = presenter.toasts.single;
      expect(toast['kind'], 'error');
      expect(toast['actionLabel'], 'Try Again');
      expect(toast['closeLabel'], 'Close');
      expect(toast['durationMs'], 8000);
      expect(find.byType(SnackBar), findsNothing);

      // A label without a callback is not an action: the toast keeps only its close button.
      OmiFeedback.error(context, 'Could not save', actionLabel: 'Try Again');
      await tester.pumpAndSettle();
      expect(presenter.toasts.last['actionLabel'], isNull);
      expect(retried, 1);
    });

    testWidgets('kinds, icons and the shell clearance reach the request', (tester) async {
      final presenter = _activate()..reply = (_) => 'timeout';
      OmiFeedback.bottomClearance = (_) => 72;
      final context = await _pumpFeedback(tester);
      OmiFeedback.confirm(context, 'Saved');
      OmiFeedback.info(context, 'Reconnecting');
      OmiFeedback.progress(context, 'Exporting');
      await OmiFeedback.undo(context, 'Speaker tagged', onUndo: () {}, icon: Icons.person_outline);
      await OmiFeedback.undo(context, 'Display set', onUndo: () {}, icon: Icons.tv_outlined);
      await tester.pumpAndSettle();
      expect([
        for (final toast in presenter.toasts) (toast['kind'], toast['durationMs'], toast['symbol'])
      ], [
        ('confirm', 1500, 'checkmark.circle.fill'),
        ('info', 4000, 'info.circle'),
        ('progress', 60000, 'progress'),
        ('undo', 5000, 'person'),
        ('undo', 5000, 'tv'),
      ]);
      expect(presenter.toasts.map((toast) => toast['bottomClearance']), everyElement(72.0));
      expect(presenter.toasts.first['appearance'], 'dark');
      expect(presenter.toasts.first['direction'], 'ltr');
      expect(presenter.toasts.first['locale'], 'en');
      final ids = [for (final toast in presenter.toasts) toast['requestId'] as int];
      expect(ids, orderedEquals([...ids]..sort()));
      expect(ids.toSet(), hasLength(ids.length));
    });

    testWidgets('a newer toast completes the previous one as replaced', (tester) async {
      final presenter = _activate();
      final context = await _pumpFeedback(tester);
      var restored = false;
      final undone = OmiFeedback.undo(context, 'Memory deleted', onUndo: () => restored = true);
      await tester.pump();
      OmiFeedback.confirm(context, 'Saved');
      await tester.pump();
      expect(presenter.toasts, hasLength(2));
      presenter.end('replaced');
      expect(await undone, isFalse);
      presenter.end('timeout');
      await tester.pump();
      expect(restored, isFalse);
    });

    testWidgets('an invalid or older request never reaches the channel', (tester) async {
      final presenter = _activate()..reply = (_) => 'timeout';
      final older = _request(NativeToastKind.info);
      final newer = _request(NativeToastKind.info);
      expect(await showIosNativeToast(_request(NativeToastKind.confirm, actionLabel: 'Undo')), isNull);
      expect(await showIosNativeToast(newer), NativeToastOutcome.timeout);
      expect(await showIosNativeToast(older), isNull, reason: 'request ids only increase');
      expect(presenter.toasts.map((toast) => toast['requestId']), [newer.requestId]);
    });

    testWidgets('hide dismisses the native toast', (tester) async {
      final presenter = _activate();
      final context = await _pumpFeedback(tester);
      final undone = OmiFeedback.undo(context, 'Task deleted', onUndo: () {});
      await tester.pump();
      OmiFeedback.hide(context);
      await tester.pump();
      expect(presenter.dismissals, 1);
      presenter.end('invalidated');
      expect(await undone, isFalse);
    });

    testWidgets('a session-generation event dismisses, and a late action does not run', (tester) async {
      final presenter = _activate();
      final context = await _pumpFeedback(tester);
      var restored = false;
      final undone = OmiFeedback.undo(context, 'Task deleted', onUndo: () => restored = true);
      await tester.pump();
      expect(presenter.dismissals, 0);
      AuthService.instance.handleAuthUserChanged('another-owner');
      await tester.pump();
      expect(presenter.dismissals, 1);
      // The reader tapped Undo just before Swift received the dismissal.
      presenter.end('action');
      expect(await undone, isFalse);
      expect(restored, isFalse);
    });

    testWidgets('a lost answer resolves as a timeout and withdraws the toast', (tester) async {
      final presenter = _activate();
      final context = await _pumpFeedback(tester);
      bool? undone;
      unawaited(OmiFeedback.undo(context, 'Task deleted', onUndo: () {}).then((value) => undone = value));
      await tester.pump(OmiFeedbackTiming.undo + const Duration(seconds: 1));
      expect(undone, isNull);
      await tester.pump(const Duration(seconds: 2));
      expect(undone, isFalse);
      expect(presenter.dismissals, 1);
      presenter.end('invalidated');
      await tester.pump();
    });
  });

  group('SnackBar fallback', () {
    testWidgets('a refused toast shows the SnackBar, whose Undo still works', (tester) async {
      final presenter = _activate()..reply = (_) => throw PlatformException(code: 'invalid_native_toast');
      final context = await _pumpFeedback(tester);
      var restored = false;
      final undone = OmiFeedback.undo(context, 'Task deleted', onUndo: () => restored = true);
      await tester.pumpAndSettle();
      expect(presenter.toasts, hasLength(1));
      expect(find.text('Task deleted'), findsOneWidget);
      expect(tester.widget<SnackBar>(find.byType(SnackBar)).duration, OmiFeedbackTiming.undo);
      await tester.tap(find.text('Undo'));
      await tester.pumpAndSettle();
      expect(restored, isTrue);
      expect(await undone, isTrue);
    });

    testWidgets('an older host without the method shows the SnackBar', (tester) async {
      final presenter = _activate()..reply = (_) => throw MissingPluginException();
      final context = await _pumpFeedback(tester);
      OmiFeedback.error(context, 'Could not save');
      await tester.pumpAndSettle();
      expect(presenter.toasts, hasLength(1));
      final snackBar = tester.widget<SnackBar>(find.byType(SnackBar));
      expect(snackBar.duration, OmiFeedbackTiming.error);
      expect(snackBar.showCloseIcon, isTrue);
    });

    testWidgets('an invalid request never reaches the channel and shows the SnackBar', (tester) async {
      final presenter = _activate();
      final context = await _pumpFeedback(tester);
      final message = 'x' * 1001;
      OmiFeedback.info(context, message);
      await tester.pumpAndSettle();
      expect(presenter.toasts, isEmpty);
      expect(find.text(message), findsOneWidget);
      expect(tester.widget<SnackBar>(find.byType(SnackBar)).duration, OmiFeedbackTiming.info);
    });

    testWidgets('a refused toast that a newer one replaced shows nothing', (tester) async {
      final presenter = _activate();
      presenter.reply = (call) => (call.arguments as Map)['message'] == 'First'
          ? throw PlatformException(code: 'invalid_native_toast')
          : 'timeout';
      final context = await _pumpFeedback(tester);
      OmiFeedback.info(context, 'First');
      OmiFeedback.info(context, 'Second');
      await tester.pumpAndSettle();
      expect(presenter.toasts, hasLength(2));
      expect(find.byType(SnackBar), findsNothing);
    });
  });

  group('inactive host (flag off or Android)', () {
    testWidgets('never touches the config channel and keeps the SnackBar', (tester) async {
      final presenter = _Presenter.install();
      expect(NativeFeedbackHost.active, isFalse);
      expect(await supportsIosSwiftUi(), isFalse);
      expect(NativeFeedbackHost.active, isFalse, reason: 'the support check gates the toast host');
      final context = await _pumpFeedback(tester);
      OmiFeedback.confirm(context, 'Saved');
      await tester.pumpAndSettle();
      expect(tester.widget<SnackBar>(find.byType(SnackBar)).duration, OmiFeedbackTiming.confirm);
      OmiFeedback.error(context, 'Failed', actionLabel: 'Try Again', onAction: () {});
      await tester.pumpAndSettle();
      expect(tester.widget<SnackBar>(find.byType(SnackBar)).showCloseIcon, isTrue);
      var restored = false;
      final undone = OmiFeedback.undo(context, 'Task deleted', onUndo: () => restored = true);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Undo'));
      await tester.pumpAndSettle();
      expect(await undone, isTrue);
      expect(restored, isTrue);
      OmiFeedback.hide(context);
      await tester.pumpAndSettle();
      expect(await showIosNativeToast(_request(NativeToastKind.info)), isNull);
      await dismissIosNativeToast();
      expect(presenter.calls, isEmpty);
    });
  });

  group('native shell clearance', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    testWidgets('clears the tab bar, and the Home footer on Home, then restores the previous clearance',
        (tester) async {
      double previous(BuildContext context) => 99;
      OmiFeedback.bottomClearance = previous;
      late BuildContext context;
      Widget shell() => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(
              body: IosNativeMainShell(
                homeIndex: 0,
                navigationRevision: 0,
                onHomeTabSelected: (_) {},
                pages: {
                  for (final id in nativeMainDestinations)
                    id: (pageContext) => Builder(builder: (inner) => (context = inner, Text(id)).$2),
                },
              ),
            ),
          );
      await tester.pumpWidget(shell());
      await tester.pumpAndSettle();
      expect(OmiFeedback.bottomClearance!(context), nativeTabBarReserve + nativeHomeFooterHeight);
      await tester.tap(find.text('Tasks'));
      await tester.pumpAndSettle();
      expect(OmiFeedback.bottomClearance!(context), nativeTabBarReserve);

      await tester.pumpWidget(const SizedBox());
      expect(OmiFeedback.bottomClearance, same(previous));
    });
  });
}
