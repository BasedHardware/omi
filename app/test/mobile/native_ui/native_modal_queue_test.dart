import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart' show PeopleListResponse;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/settings/person_name_dialog.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
const _actions = [NativeRow('cancel', 'Cancel', symbol: 'xmark'), NativeRow('save', 'Save')];

/// The config channel's presenter. [reply] answers 'present' at once; without it, each presentation
/// waits in [pending] until the test completes it.
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
      if (call.method != 'present') return null;
      final reply = presenter.reply;
      if (reply != null) return reply(call);
      final completer = Completer<Object?>();
      presenter.pending.add(completer);
      return completer.future;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
    return presenter;
  }

  Iterable<Map> get _presents => calls.where((call) => call.method == 'present').map((call) => call.arguments as Map);
  List<String> get titles => [for (final present in _presents) (present['snapshot'] as Map)['title'] as String];
  List<int> get requestIds => [for (final present in _presents) present['requestId'] as int];
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

/// A different signed-in account, installed without a generation event.
final class _AnotherOwner implements AuthTokenGateway {
  const _AnotherOwner();

  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'another-owner');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}

void main() {
  testWidgets('concurrent presentations reach present strictly in sequence', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    final context = _caller(tester, 'caller');
    final first = showIosNativeModal(context, title: 'First', actions: _actions);
    final second = showIosNativeModal(context, title: 'Second', actions: _actions);
    await tester.pump();
    expect(presenter.titles, ['First']);
    await tester.pump(const Duration(seconds: 5));
    expect(presenter.titles, ['First'], reason: 'The second waits for as long as the first stays open');

    presenter.pending.single.complete({'action': 'save', 'values': {}});
    expect((await first)!.action, 'save');
    await tester.pump();
    expect(presenter.titles, ['First', 'Second']);
    expect(presenter.requestIds.last, greaterThan(presenter.requestIds.first));
    presenter.pending.last.complete(null);
    final dismissed = await second;
    expect(dismissed, isNotNull);
    expect(dismissed!.action, isNull);
  });

  testWidgets('unrepresentable rows return null instead of throwing, without presenting', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    final context = _caller(tester, 'caller');
    expect(await showIosNativeModal(context, title: 'Edit', actions: [..._actions, const NativeRow('save', 'Again')]),
        isNull);
    expect(
        await showIosNativeModal(context, title: 'Edit Person', actions: _actions, sections: [
          NativeSection('person', [NativeRow('name', 'Name', kind: 'text', value: 'x' * 41, maximumLength: 40)])
        ]),
        isNull);
    expect(presenter.calls, isEmpty);
  });

  testWidgets('a person name longer than its limit opens the Flutter editor instead of throwing', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    NativeTestHost.install();
    final presenter = _Presenter.install();
    final people = PeopleProvider(loadPeople: () async => const PeopleListResponse(people: []));
    addTearDown(people.dispose);
    final person = Person(id: 'avery', name: 'A' * 41, createdAt: DateTime(2026), updatedAt: DateTime(2026));
    await tester.pumpWidget(NativeTestHost.app(ChangeNotifierProvider(
        create: (_) => ConnectivityProvider(),
        child: Builder(
            builder: (context) => TextButton(
                onPressed: () => showPersonNameDialog(context, people, person: person),
                child: const Text('Rename'))))));
    await tester.tap(find.text('Rename'));
    await tester.pumpAndSettle();
    expect(presenter.calls, isEmpty);
    expect(find.byType(OmiAlertDialog), findsOneWidget);
    expect(find.text('A' * 41), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a forged action or value returns a cancellation that carries no values', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    final context = _caller(tester, 'caller');
    const sections = [
      NativeSection('person', [
        NativeRow('name', 'Name', kind: 'text', value: 'Ada', maximumLength: 40),
        NativeRow('opt_out', 'Do not ask again', kind: 'toggle', value: false),
      ])
    ];
    Future<NativeModalResult?> present(Object? reply, {List<NativeRow> actions = _actions}) {
      presenter.reply = (_) => reply;
      return showIosNativeModal(context, title: 'Edit Person', actions: actions, sections: sections);
    }

    for (final forged in [
      {
        'action': 'delete_everything',
        'values': {'name': 'Ada', 'opt_out': false}
      },
      {
        'action': 'save',
        'values': {'name': 'x' * 41, 'opt_out': false}
      },
      {
        'action': 'save',
        'values': {'name': 'Ada', 'opt_out': 'yes'}
      },
      {
        'action': 'save',
        'values': {'opt_out': false}
      },
      {'action': 'save'},
      {'action': 7, 'values': {}},
    ]) {
      final result = await present(forged);
      expect(result, isNotNull, reason: '$forged');
      expect(result!.action, isNull, reason: '$forged');
      expect(result.values, isEmpty, reason: '$forged');
    }
    final disabled = await present({
      'action': 'save',
      'values': {'name': 'Ada', 'opt_out': false}
    }, actions: const [
      NativeRow('cancel', 'Cancel'),
      NativeRow('save', 'Save', enabled: false)
    ]);
    expect(disabled!.action, isNull);
    final saved = await present({
      'action': 'save',
      'values': {'name': 'Avery', 'opt_out': true}
    });
    expect(saved!.action, 'save');
    expect(saved.values, {'name': 'Avery', 'opt_out': true});
  });

  testWidgets('a presentation the host refuses returns null and frees the queue', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    final context = _caller(tester, 'caller');
    presenter.reply = (_) => throw PlatformException(code: 'invalid_native_presentation');
    expect(await showIosNativeModal(context, title: 'Refused', actions: _actions), isNull);
    presenter.reply = (_) => {'action': 'save', 'values': {}};
    expect((await showIosNativeModal(context, title: 'Next', actions: _actions))!.action, 'save');
    expect(presenter.titles, ['Refused', 'Next']);
  });

  testWidgets('a waiting request whose context unmounts never presents', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['open', 'leaving']));
    final open = showIosNativeModal(_caller(tester, 'open'), title: 'Open', actions: _actions);
    await tester.pump();
    final leaving = showIosNativeModal(_caller(tester, 'leaving'), title: 'Leaving', actions: _actions);
    await tester.pump();
    await tester.pumpWidget(_callers(['open']));
    presenter.pending.single.complete({'action': 'cancel', 'values': {}});
    expect((await open)!.action, isNull);
    expect(await leaving, isNull);
    expect(presenter.titles, ['Open']);
  });

  testWidgets('a session change drops a waiting request and dismisses the presented one', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    final context = _caller(tester, 'caller');
    final presented = showIosNativeModal(context, title: 'Presented', actions: _actions);
    await tester.pump();
    final waiting = showIosNativeModal(context, title: 'Waiting', actions: _actions);
    await tester.pump();
    AuthService.instance.handleAuthUserChanged('another-owner');
    await tester.pump();
    final dropped = await waiting;
    expect(dropped, isNotNull, reason: 'No Flutter dialog built for the previous owner opens for the next');
    expect(dropped!.action, isNull);
    expect(dropped.values, isEmpty);
    expect(presenter.dismissed, [presenter.requestIds.single]);
    // Swift confirms the dismissal; the presented request reports a cancellation.
    presenter.pending.single.complete(null);
    final dismissed = await presented;
    expect(dismissed!.action, isNull);
    expect(presenter.titles, ['Presented']);
  });

  testWidgets('the watchdog frees the queue when a presenting caller unmounts and Swift never answers', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['lost', 'next']));
    final lost = showIosNativeModal(_caller(tester, 'lost'), title: 'Lost', actions: _actions);
    await tester.pump();
    final next = showIosNativeModal(_caller(tester, 'next'), title: 'Next', actions: _actions);
    await tester.pump();
    await tester.pumpWidget(_callers(['next']));
    await tester.pump(const Duration(milliseconds: 600));
    expect(presenter.dismissed, [presenter.requestIds.single], reason: 'Dart asks Swift to dismiss it');
    await tester.pump(const Duration(seconds: 1));
    expect(presenter.titles, ['Lost'], reason: 'Swift has a grace period to confirm');
    await tester.pump(const Duration(seconds: 1));
    final released = await lost;
    expect(released!.action, isNull);
    await tester.pump();
    expect(presenter.titles, ['Lost', 'Next']);
    presenter.pending.last.complete({'action': 'save', 'values': {}});
    expect((await next)!.action, 'save');
  });

  testWidgets('a presentation Swift never completes frees the queue after the maximum hold', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    final context = _caller(tester, 'caller');
    final stuck = showIosNativeModal(context, title: 'Stuck', actions: _actions);
    await tester.pump();
    final next = showIosNativeModal(context, title: 'Next', actions: _actions);
    await tester.pump(const Duration(minutes: 9));
    expect(presenter.titles, ['Stuck']);
    expect(presenter.dismissed, isEmpty, reason: 'Nothing is dismissed on a timer');
    await tester.pump(const Duration(minutes: 1, seconds: 1));
    expect(presenter.titles, ['Stuck', 'Next']);
    presenter.pending.last.complete(null);
    expect((await next)!.action, isNull);
    // A late completion still answers its own caller.
    presenter.pending.first.complete({'action': 'save', 'values': {}});
    expect((await stuck)!.action, 'save');
  });

  testWidgets('non-iOS or flag-off builds never queue or touch the presenter', (tester) async {
    // With the flag (Android), the support check answers false off iOS before anything queues.
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    expect(await showIosNativeModal(_caller(tester, 'caller'), title: 'Default', actions: _actions), isNull);
    expect(presenter.calls, isEmpty);
  });

  testWidgets('a waiting request whose session changed is cancelled, not sent to its Flutter path', (tester) async {
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(_callers(['caller']));
    final context = _caller(tester, 'caller');
    final presented = showIosNativeModal(context, title: 'Presented', actions: _actions);
    await tester.pump();
    final waiting = showIosNativeModal(context, title: 'Waiting', actions: _actions);
    await tester.pump();
    // The account changes without a generation event reaching the waiting request first.
    AuthService.installLocalHarnessTokenGateway(const _AnotherOwner());
    presenter.pending.single.complete({'action': 'save', 'values': {}});
    final stale = await presented;
    expect(stale!.action, isNull, reason: 'A reply for the previous owner mutates nothing');
    final dropped = await waiting;
    expect(dropped, isNotNull);
    expect(dropped!.action, isNull);
    expect(dropped.values, isEmpty);
    expect(presenter.titles, ['Presented']);
  });

  testWidgets('showOmiConfirmMenu keeps its anchored Flutter menu off iOS', (tester) async {
    // Native presentations are available here; only the platform is not iOS (Android with the flag).
    NativeTestHost.install();
    final presenter = _Presenter.install();
    await tester.pumpWidget(NativeTestHost.app(Scaffold(
        body: Builder(
            builder: (context) => TextButton(
                onPressed: () => showOmiConfirmMenu(context,
                    anchor: const Rect.fromLTWH(300, 100, 44, 44),
                    title: 'Delete Conversation?',
                    message: 'This also deletes its memories, tasks, and audio files.',
                    confirmLabel: 'Delete Conversation'),
                child: const Text('Delete'))))));
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('omi_confirm_menu_confirm')), findsOneWidget);
    expect(find.byType(OmiAlertDialog), findsNothing);
    expect(presenter.calls, isEmpty);
  });
}
