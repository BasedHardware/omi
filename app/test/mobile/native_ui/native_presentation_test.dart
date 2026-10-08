import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/services/auth_service.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
const _actions = [NativeRow('cancel', 'Cancel', symbol: 'xmark'), NativeRow('save', 'Save')];
const _programmatic = {'values': <String, Object?>{}, 'reason': 'programmatic'};

/// The config channel's presenter. Each presentation stays up until the test answers it, and a
/// dismissal request is confirmed the way Swift confirms it, unless [confirmDismissals] is off.
class _Presenter {
  _Presenter._();

  final calls = <MethodCall>[];
  final _open = <int, Completer<Object?>>{};
  bool confirmDismissals = true;
  bool refuse = false;

  static _Presenter install() {
    final presenter = _Presenter._();
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(_config, (call) async {
      presenter.calls.add(call);
      switch (call.method) {
        case 'present' || 'presentActivity':
          if (presenter.refuse) throw PlatformException(code: 'invalid_native_presentation');
          final completer = Completer<Object?>();
          presenter._open[(call.arguments as Map)['requestId'] as int] = completer;
          return completer.future;
        case 'dismissPresentation':
          if (presenter.confirmDismissals) presenter.answer(call.arguments as int, _programmatic);
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
    return presenter;
  }

  /// Completes presentation [id] as Swift would, with [reply].
  void answer(int id, Object? reply) => _open.remove(id)?.complete(reply);

  Iterable<MethodCall> get _presents => calls.where((call) => ['present', 'presentActivity'].contains(call.method));
  List<String> get methods => [for (final call in _presents) call.method];
  List<int> get ids => [for (final call in _presents) (call.arguments as Map)['requestId'] as int];
  int get last => ids.last;
  List<Object?> get dismissed => [
        for (final call in calls)
          if (call.method == 'dismissPresentation') call.arguments
      ];
}

Widget _callers(List<String> names) => NativeTestHost.app(Scaffold(
        body: Column(children: [
      for (final name in names) SizedBox(key: ValueKey(name), height: 40),
    ])));

BuildContext _caller(WidgetTester tester, String name) => tester.element(find.byKey(ValueKey(name)));

Future<NativeModalResult?> _modal(BuildContext context, {Future<void>? dismissSignal}) =>
    showIosNativeModal(context, title: 'Edit', actions: _actions, dismissSignal: dismissSignal, sections: const [
      NativeSection('person', [NativeRow('name', 'Name', kind: 'text', value: 'Ada', maximumLength: 40)])
    ]);

void main() {
  group('modal outcome reasons', () {
    testWidgets('Swift completions map to action, cancel and dismissed', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final context = _caller(tester, 'caller');
      Future<NativeModalResult> outcome(Object? reply) async {
        final result = _modal(context);
        await tester.pump();
        presenter.answer(presenter.last, reply);
        return (await result)!;
      }

      final saved = await outcome({
        'action': 'save',
        'values': {'name': 'Avery'},
        'reason': 'action'
      });
      expect((saved.action, saved.reason), ('save', 'action'));
      expect(saved.values, {'name': 'Avery'});
      for (final (reply, reason) in [
        ({'values': {}, 'reason': 'cancel'}, 'cancel'),
        // An older host reports a system alert's cancel button as its action, without a reason.
        ({'action': 'cancel', 'values': {}}, 'cancel'),
        // An older host answers any cancellation with nil.
        (null, 'cancel'),
        ({'values': {}, 'reason': 'dismissed'}, 'dismissed'),
        ({'values': {}, 'reason': 'exploded'}, 'dismissed'),
        ({'action': 'delete_everything', 'values': {}, 'reason': 'action'}, 'dismissed'),
        (
          {
            'action': 'save',
            'values': {'name': 'x' * 41},
            'reason': 'action'
          },
          'dismissed'
        ),
        (
          {
            'action': 'save',
            'values': {'name': 'Ada'},
            'reason': 'cancel'
          },
          'dismissed'
        ),
      ]) {
        final result = await outcome(reply);
        expect(result.reason, reason, reason: '$reply');
        expect(result.action, isNull, reason: '$reply');
        expect(result.values, isEmpty, reason: '$reply');
      }
      expect(presenter.dismissed, isEmpty);
    });

    testWidgets('a session change while presented reports invalidated, decided in Dart', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final result = _modal(_caller(tester, 'caller'));
      await tester.pump();
      AuthService.instance.handleAuthUserChanged('another-owner');
      await tester.pump();
      // Swift confirms the dismissal Dart asked for with 'programmatic'; Dart knows why it asked.
      expect(presenter.dismissed, [presenter.last]);
      final invalidated = await result;
      expect((invalidated!.action, invalidated.reason), (null, 'invalidated'));
    });

    testWidgets('a session change while waiting reports invalidated without presenting', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final context = _caller(tester, 'caller');
      final presented = _modal(context);
      await tester.pump();
      final waiting = showIosNativeModal(context, title: 'Waiting', actions: _actions);
      await tester.pump();
      AuthService.instance.handleAuthUserChanged('another-owner');
      final dropped = await waiting;
      expect((dropped!.action, dropped.reason), (null, 'invalidated'));
      expect(dropped.values, isEmpty);
      await tester.pump();
      expect(presenter.methods, ['present'], reason: 'Only the first request reached Swift');
      expect((await presented)!.reason, 'invalidated');
    });

    testWidgets('an unmounted presenting caller reports unmounted', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['leaving', 'staying']));
      final result = _modal(_caller(tester, 'leaving'));
      await tester.pump();
      await tester.pumpWidget(_callers(['staying']));
      await tester.pump(const Duration(milliseconds: 600));
      expect(presenter.dismissed, [presenter.last]);
      final unmounted = await result;
      expect((unmounted!.action, unmounted.reason), (null, 'unmounted'));
      expect(unmounted.values, isEmpty);
    });
  });

  group('dismissSignal', () {
    testWidgets('a signal before the result dismisses once and discards the late reply', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install()..confirmDismissals = false;
      await tester.pumpWidget(_callers(['caller']));
      final signal = Completer<void>();
      final result = _modal(_caller(tester, 'caller'), dismissSignal: signal.future);
      await tester.pump();
      signal.complete();
      await tester.pump();
      expect(presenter.dismissed, [presenter.last]);
      // The person's Save reached Swift first, but its reply arrives after the signal.
      presenter.answer(presenter.last, {
        'action': 'save',
        'values': {'name': 'Avery'},
        'reason': 'action'
      });
      final withdrawn = await result;
      expect((withdrawn!.action, withdrawn.reason), (null, 'programmatic'));
      expect(withdrawn.values, isEmpty);
      expect(presenter.dismissed, hasLength(1));
    });

    testWidgets('Swift never confirming still answers programmatic after the grace period', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install()..confirmDismissals = false;
      await tester.pumpWidget(_callers(['caller']));
      final signal = Completer<void>();
      final result = _modal(_caller(tester, 'caller'), dismissSignal: signal.future);
      await tester.pump();
      signal.complete();
      await tester.pump(const Duration(seconds: 3));
      expect((await result)!.reason, 'programmatic');
      presenter.answer(presenter.last, null);
    });

    testWidgets('a result that arrives first wins and a late signal is ignored', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final signal = Completer<void>();
      final result = _modal(_caller(tester, 'caller'), dismissSignal: signal.future);
      await tester.pump();
      presenter.answer(presenter.last, {
        'action': 'save',
        'values': {'name': 'Avery'},
        'reason': 'action'
      });
      signal.complete();
      final saved = await result;
      await tester.pump();
      expect((saved!.action, saved.reason), ('save', 'action'));
      expect(presenter.dismissed, isEmpty);
    });

    testWidgets('a signal while the request waits drops it without presenting', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final context = _caller(tester, 'caller');
      final first = _modal(context);
      await tester.pump();
      final signal = Completer<void>();
      final waiting = showIosNativeModal(context, title: 'Waiting', actions: _actions, dismissSignal: signal.future);
      await tester.pump();
      signal.complete();
      final dropped = await waiting;
      expect((dropped!.action, dropped.reason), (null, 'programmatic'));
      expect(presenter.ids, hasLength(1));
      expect(presenter.dismissed, isEmpty, reason: 'Nothing was presented for it');
      presenter.answer(presenter.last, {'values': {}, 'reason': 'cancel'});
      expect((await first)!.reason, 'cancel');
      await tester.pump();
      expect(presenter.ids, hasLength(1));
    });

    testWidgets('a signal that already completed never presents', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final result = await _modal(_caller(tester, 'caller'), dismissSignal: Future<void>.value());
      await tester.pump();
      expect(result!.reason, 'programmatic');
      expect(presenter.calls, isEmpty);
    });
  });

  group('activity', () {
    testWidgets('unsupported hosts and out-of-range labels answer null without the channel', (tester) async {
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      expect(await showIosNativeActivity(_caller(tester, 'caller'), label: 'Saving'), isNull);
      expect(presenter.calls, isEmpty);

      NativeTestHost.install();
      final context = _caller(tester, 'caller');
      expect(await showIosNativeActivity(context, label: ''), isNull);
      expect(await showIosNativeActivity(context, label: 'a' * 201), isNull);
      expect(presenter.calls, isEmpty);
      // The limit counts characters as Swift does, not UTF-16 units.
      final family = await showIosNativeActivity(context, label: '👨‍👩‍👧‍👦' * 200);
      expect(family, isNotNull);
      await tester.pump();
      final request = presenter.calls.single;
      expect(request.method, 'presentActivity');
      expect(request.arguments, {
        'requestId': presenter.last,
        'label': '👨‍👩‍👧‍👦' * 200,
        'appearance': 'dark',
        'locale': 'en',
        'direction': 'ltr',
      });
      await family!.dismiss();
      expect(await family.closed, 'programmatic');
    });

    testWidgets('dismiss is idempotent and dismisses once', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install()..confirmDismissals = false;
      await tester.pumpWidget(_callers(['caller']));
      final activity = (await showIosNativeActivity(_caller(tester, 'caller'), label: 'Saving'))!;
      await tester.pump();
      expect(presenter.methods, ['presentActivity']);
      final first = activity.dismiss();
      final second = activity.dismiss();
      expect(identical(first, second), isTrue);
      await tester.pump();
      expect(presenter.dismissed, [presenter.last]);
      var gone = false;
      unawaited(first.then((_) => gone = true));
      await tester.pump();
      expect(gone, isFalse, reason: 'It completes once Swift confirms the overlay is gone');
      presenter.answer(presenter.last, _programmatic);
      await first;
      await activity.dismiss();
      expect(presenter.dismissed, hasLength(1));
      expect(await activity.closed, 'programmatic');
    });

    testWidgets('presenting it closes the keyboard so the field beneath takes no input', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      final focus = FocusNode();
      addTearDown(focus.dispose);
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
          body: Column(children: [
        TextField(focusNode: focus),
        const SizedBox(key: ValueKey('caller'), height: 40),
      ]))));
      focus.requestFocus();
      await tester.pump();
      expect(focus.hasFocus, isTrue);
      final activity = (await showIosNativeActivity(_caller(tester, 'caller'), label: 'Saving'))!;
      await tester.pump();
      expect(presenter.methods, ['presentActivity']);
      expect(focus.hasFocus, isFalse);
      await activity.dismiss();
    });

    testWidgets('a session-generation event dismisses it', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final activity = (await showIosNativeActivity(_caller(tester, 'caller'), label: 'Saving'))!;
      await tester.pump();
      AuthService.instance.handleAuthUserChanged('another-owner');
      await tester.pump();
      expect(presenter.dismissed, [presenter.last]);
      expect(await activity.closed, 'invalidated');
      await activity.dismiss();
      expect(presenter.dismissed, hasLength(1));
    });

    testWidgets('an unmounted caller dismisses it', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['leaving', 'staying']));
      final activity = (await showIosNativeActivity(_caller(tester, 'leaving'), label: 'Saving'))!;
      await tester.pump();
      await tester.pumpWidget(_callers(['staying']));
      await tester.pump(const Duration(milliseconds: 600));
      expect(presenter.dismissed, [presenter.last]);
      expect(await activity.closed, 'unmounted');
      // The caller's finally still dismisses; nothing else is sent.
      await activity.dismiss();
      expect(presenter.dismissed, hasLength(1));
    });

    testWidgets('an alert requested during an activity waits for it', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final context = _caller(tester, 'caller');
      final activity = (await showIosNativeActivity(context, label: 'Saving'))!;
      await tester.pump();
      final alert = showIosNativeModal(context, title: 'Delete?', actions: _actions, alert: true);
      await tester.pump(const Duration(seconds: 5));
      expect(presenter.methods, ['presentActivity'], reason: 'The alert waits behind the activity');
      await activity.dismiss();
      await tester.pump();
      expect(presenter.methods, ['presentActivity', 'present']);
      presenter.answer(presenter.last, {'action': 'save', 'values': {}, 'reason': 'action'});
      expect((await alert)!.action, 'save');
    });

    testWidgets('an activity requested during a modal waits, and dismissing it first never presents it',
        (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final context = _caller(tester, 'caller');
      final modal = _modal(context);
      await tester.pump();
      final activity = await showIosNativeActivity(context, label: 'Saving');
      expect(activity, isNotNull, reason: 'The handle returns at once; the overlay waits for its turn');
      await tester.pump();
      expect(presenter.methods, ['present']);
      await activity!.dismiss();
      expect(await activity.closed, 'programmatic');
      presenter.answer(presenter.last, {'values': {}, 'reason': 'cancel'});
      expect((await modal)!.reason, 'cancel');
      await tester.pump();
      expect(presenter.methods, ['present']);
      expect(presenter.dismissed, isEmpty);
    });

    testWidgets('an activity left up ends after its maximum lifetime', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install();
      await tester.pumpWidget(_callers(['caller']));
      final activity = (await showIosNativeActivity(_caller(tester, 'caller'), label: 'Saving'))!;
      await tester.pump(const Duration(seconds: 119));
      expect(presenter.dismissed, isEmpty);
      await tester.pump(const Duration(seconds: 2));
      expect(presenter.dismissed, [presenter.last]);
      expect(await activity.closed, 'programmatic');
    });

    testWidgets('a refused or externally removed activity frees the order', (tester) async {
      NativeTestHost.install();
      final presenter = _Presenter.install()..refuse = true;
      await tester.pumpWidget(_callers(['caller']));
      final context = _caller(tester, 'caller');
      final refused = (await showIosNativeActivity(context, label: 'Saving'))!;
      await tester.pump();
      expect(await refused.closed, 'dismissed');
      presenter.refuse = false;
      final removed = (await showIosNativeActivity(context, label: 'Saving'))!;
      await tester.pump();
      // UIKit or another owner removed it; Swift reports it as dismissed.
      presenter.answer(presenter.last, {'values': {}, 'reason': 'dismissed'});
      expect(await removed.closed, 'dismissed');
      final next = _modal(context);
      await tester.pump();
      expect(presenter.methods.last, 'present');
      presenter.answer(presenter.last, {'values': {}, 'reason': 'cancel'});
      expect((await next)!.reason, 'cancel');
    });
  });
}
