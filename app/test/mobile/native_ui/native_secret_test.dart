import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_secret.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

import 'native_test_host.dart';

const _key = 'omi_dev_0123456789abcdef';
const _fallback = 'complete flutter surface';
const _config = MethodChannel('com.omi.native_ui/config');

NativeRow _secret(
        {String id = 'secret_value', Object? value = _key, Map<String, String> options = const {'copy': 'Copy'}}) =>
    NativeRow(id, 'API Key', kind: 'secret', value: value, options: options, action: (_) {});

Widget _surface({
  bool sensitive = true,
  List<NativeRow>? rows,
  List<NativeRow> toolbar = const [],
  NativeChat? chat,
  NativeReader? reader,
  NativeRow? navigation,
  bool publicSurface = false,
  NativeSurfaceController? controller,
}) =>
    IosNativeSurface(
      title: 'Key Created',
      sensitive: sensitive,
      fallback: const Text(_fallback),
      toolbar: toolbar,
      chat: chat,
      reader: reader,
      navigation: navigation,
      publicSurface: publicSurface,
      controller: controller,
      sections: navigation != null
          ? const []
          : [
              NativeSection('secret', rows ?? [_secret()])
            ],
    );

/// Mounts [surface] and reports whether the native view, rather than the fallback, rendered.
Future<bool> _rendersNatively(WidgetTester tester, Widget surface) async {
  await tester.pumpWidget(NativeTestHost.app(surface));
  await NativeTestHost.settle(tester);
  expect(tester.takeException(), isNull);
  return find.byType(UiKitView).evaluate().isNotEmpty;
}

/// Opens [page] as a pushed route from a mounted launcher.
Future<void> _push(WidgetTester tester, Widget page) async {
  await tester.pumpWidget(NativeTestHost.app(Builder(
      builder: (context) => TextButton(
          // The sheet supplies a Material, as the production bottom sheet does.
          onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => Material(child: page))),
          child: const Text('open')))));
  await tester.tap(find.text('open'));
  await NativeTestHost.settle(tester);
  await tester.pump(const Duration(seconds: 1));
}

NativeSecretPage _page({bool native = true, VoidCallback? onCopy}) => NativeSecretPage(
      owner: AuthService.instance.captureSessionSnapshot()!,
      native: native,
      title: 'Key Created',
      message: 'Your new key',
      warning: 'Copy it now. You will not see it again.',
      secretLabel: 'API Key',
      secret: _key,
      copyLabel: 'Copy',
      doneLabel: 'Done',
      onCopy: onCopy ?? () {},
    );

Object? _decode(ByteData? reply) => const StandardMethodCodec().decodeEnvelope(reply!);

void main() {
  group('secret row', () {
    test('only 1 to 4096 printable ASCII characters without whitespace are valid', () {
      for (final secret in ['', 'a' * 4097, 'omi key', 'omi\nkey', 'omi\tkey', 'omi\x7Fkey', 'omi_kéy', 'omi_🔑']) {
        expect(nativeSecretValid(secret), false, reason: jsonEncode(secret));
        expect(_secret(value: secret).valid, false, reason: jsonEncode(secret));
      }
      for (final secret in ['!', _key, '~' * 4096]) {
        expect(nativeSecretValid(secret), true);
        expect(_secret(value: secret).valid, true);
      }
      expect(_secret(value: 42).valid, false);
      expect(_secret(value: null).valid, false);
    });

    test('a secret carries exactly one labelled copy command and no other fields', () {
      for (final options in [
        <String, String>{},
        {'copy': ''},
        {'reveal': 'Reveal'},
        {'copy': 'Copy', 'share': 'Share'},
      ]) {
        expect(_secret(options: options).valid, false, reason: '$options');
      }
      for (final row in [
        const NativeRow('secret_value', 'API Key',
            kind: 'secret', value: _key, options: {'copy': 'Copy'}, imageUri: 'https://example.com/key.png'),
        const NativeRow('secret_value', 'API Key', kind: 'secret', value: _key, options: {'copy': 'Copy'}, level: 1),
        const NativeRow('secret_value', 'API Key',
            kind: 'secret', value: _key, options: {'copy': 'Copy'}, maximumValue: 1),
        const NativeRow('secret_value', 'API Key',
            kind: 'secret', value: _key, options: {'copy': 'Copy'}, keyboard: 'password'),
        const NativeRow('secret_value', 'API Key',
            kind: 'secret', value: _key, options: {'copy': 'Copy'}, maximumLength: 64),
        const NativeRow('secret_value', 'API Key', kind: 'secret', value: _key, options: {
          'copy': 'Copy'
        }, points: [
          {'x': 0, 'y': 0, 'label': ''}
        ]),
        const NativeRow('secret_value', 'API Key', kind: 'secret', value: _key, options: {
          'copy': 'Copy'
        }, blocks: [
          {'kind': 'text', 'text': '', 'indent': 0, 'prefix': ''}
        ]),
      ]) {
        expect(row.valid, false);
      }
    });

    test('a secret accepts only the copy command, never its value', () async {
      final row = _secret();
      expect(row.accepts('copy'), true);
      for (final input in [null, 'Copy', _key, true, 1]) {
        expect(row.accepts(input), false, reason: '$input');
      }
      var copies = 0;
      final copy = NativeRow('secret_value', 'API Key',
          kind: 'secret', value: _key, options: const {'copy': 'Copy'}, action: (_) => copies++);
      await dispatchNativeAction(const MethodCall('action', {'id': 'secret_value', 'value': 'copy'}),
          isActive: () => true, rows: [copy]);
      expect(copies, 1);
      for (final value in [null, _key]) {
        await expectLater(
            dispatchNativeAction(MethodCall('action', {'id': 'secret_value', 'value': value}),
                isActive: () => true, rows: [copy]),
            throwsA(isA<PlatformException>()));
      }
      expect(copies, 1);
    });
  });

  group('sensitive surface', () {
    testWidgets('renders a single section secret natively and publishes sensitive', (tester) async {
      final host = NativeTestHost.install();
      expect(await _rendersNatively(tester, _surface()), true);
      final update = host.calls.lastWhere((call) => call.$2.method == 'update').$2;
      expect((update.arguments as Map)['sensitive'], true);
      expect(
          await _rendersNatively(tester, _surface(sensitive: false, rows: [const NativeRow('label', 'Label')])), true);
      final routine = host.calls.lastWhere((call) => call.$2.method == 'update').$2;
      expect((routine.arguments as Map)['sensitive'], false);
    });

    testWidgets('every unsupported secret placement keeps the complete Flutter surface', (tester) async {
      final host = NativeTestHost.install();
      final cases = <String, Widget>{
        'not sensitive': _surface(sensitive: false),
        'in the toolbar': _surface(rows: const [], toolbar: [_secret()]),
        'doubled': _surface(rows: [_secret(), _secret(id: 'secret_again')]),
        'with chat': _surface(chat: const NativeChat(draft: '', placeholder: 'Ask Omi', actions: [])),
        'in chat actions': _surface(
            sensitive: false,
            rows: const [],
            chat: NativeChat(draft: '', placeholder: 'Ask Omi', actions: [_secret()])),
        'with a reader': _surface(reader: const NativeReader()),
        'public': _surface(publicSurface: true),
        'with navigation': _surface(
            navigation: NativeRow('main_destination', '',
                kind: 'segmented',
                value: 'home',
                options: const {'home': 'Home', 'tasks': 'Tasks', 'memories': 'M', 'apps': 'A', 'settings': 'S'},
                action: (_) {})),
      };
      for (final entry in cases.entries) {
        expect(await _rendersNatively(tester, entry.value), false, reason: entry.key);
        expect(find.text(_fallback), findsOneWidget, reason: entry.key);
      }
      expect(host.created, isEmpty, reason: 'No snapshot carrying a misplaced secret reaches Swift');
    });

    testWidgets('captureImage returns null on a sensitive surface without asking the host', (tester) async {
      final host = NativeTestHost.install(
          answer: (_, call) async => call.method == 'captureImage' ? Uint8List.fromList([1, 2, 3]) : null);
      final controller = NativeSurfaceController();
      expect(await _rendersNatively(tester, _surface(controller: controller)), true);
      expect(await controller.captureImage(), isNull);
      expect(host.calls.map((call) => call.$2.method), isNot(contains('captureImage')));

      // The same controller on a routine surface still reaches the host.
      expect(
          await _rendersNatively(
              tester, _surface(sensitive: false, rows: const [NativeRow('label', 'Label')], controller: controller)),
          true);
      expect(await controller.captureImage(), [1, 2, 3]);
    });

    testWidgets('a native modal never presents a secret', (tester) async {
      NativeTestHost.install();
      final presents = <MethodCall>[];
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(_config, (call) async {
        presents.add(call);
        return {'action': 'save', 'values': <String, Object?>{}};
      });
      addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
      await tester.pumpWidget(NativeTestHost.app(const SizedBox(key: ValueKey('caller'))));
      final context = tester.element(find.byKey(const ValueKey('caller')));
      const actions = [NativeRow('cancel', 'Cancel'), NativeRow('save', 'Save')];
      expect(
          await showIosNativeModal(context, title: 'Key', actions: actions, sections: [
            NativeSection('secret', [_secret()])
          ]),
          isNull);
      expect(presents, isEmpty);
      expect((await showIosNativeModal(context, title: 'Key', actions: actions))!.action, 'save',
          reason: 'The same presenter still serves other requests');
    });
  });

  group('secret sheet', () {
    testWidgets('the routine snapshot carries the key only as the secret row value', (tester) async {
      final host = NativeTestHost.install();
      await _push(tester, _page());
      expect(find.byType(UiKitView), findsOneWidget);
      final snapshots = [
        tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map,
        for (final call in host.calls)
          if (call.$2.method == 'update') call.$2.arguments as Map,
      ];
      expect(snapshots, hasLength(greaterThan(1)));
      for (final snapshot in snapshots) {
        expect(snapshot['sensitive'], true);
        expect(_key.allMatches(jsonEncode(snapshot)).length, 1);
        final rows = [
          for (final section in snapshot['sections'] as List) ...(section as Map)['rows'] as List,
          ...snapshot['toolbar'] as List,
        ].cast<Map>();
        final secret = rows.singleWhere((row) => row['kind'] == 'secret');
        expect(secret['value'], _key);
        expect(secret['id'], 'secret_value');
        secret['value'] = null;
        expect(jsonEncode(snapshot), isNot(contains(_key)));
      }
      expect(find.text(_key), findsNothing, reason: 'Flutter draws no second copy of the key');
    });

    testWidgets('copy and Done come back through the bridge; Done pops and withdraws the key', (tester) async {
      final host = NativeTestHost.install();
      var copies = 0;
      await _push(tester, _page(onCopy: () => copies++));
      final view = host.created.single;
      expect(
          _decode(await host.sendFromNative(view, const MethodCall('action', {'id': 'secret_value', 'value': 'copy'}))),
          isNull);
      expect(copies, 1);
      final refused =
          await host.sendFromNative(view, const MethodCall('action', {'id': 'secret_value', 'value': _key}));
      expect(() => _decode(refused), throwsA(isA<PlatformException>()));
      expect(copies, 1);
      _decode(await host.sendFromNative(view, const MethodCall('action', {'id': 'secret_done'})));
      await tester.pumpAndSettle();
      expect(find.byType(NativeSecretPage), findsNothing);
      expect(find.text('open'), findsOneWidget);
      expect(host.disposed, [view], reason: 'The native view, and the key it held, is torn down');
    });

    testWidgets('a refused snapshot falls back to the Flutter body, which keeps the key', (tester) async {
      NativeTestHost.install(answer: (_, call) async {
        if (call.method == 'update') throw PlatformException(code: 'invalid_native_snapshot');
        return null;
      });
      var copies = 0;
      await _push(tester, _page(onCopy: () => copies++));
      expect(find.byType(UiKitView), findsNothing);
      expect(find.text(_key), findsOneWidget);
      await tester.tap(find.text('Copy'));
      expect(copies, 1);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(find.text(_key), findsNothing);
      expect(find.text('open'), findsOneWidget);
    });

    testWidgets('a session change pops an open sheet and invalidates its native view', (tester) async {
      final host = NativeTestHost.install();
      await _push(tester, _page());
      final view = host.created.single;
      AuthService.instance.handleAuthUserChanged('another-owner');
      await tester.pumpAndSettle();
      expect(find.byType(NativeSecretPage), findsNothing);
      expect(host.methodsOf(view), contains('invalidate'));
      expect(tester.takeException(), isNull);
    });

    testWidgets('a page whose session already changed never shows the key', (tester) async {
      final host = NativeTestHost.install();
      final stale = _page();
      AuthService.instance.handleAuthUserChanged('another-owner');
      await _push(tester, stale);
      await tester.pumpAndSettle();
      expect(find.byType(NativeSecretPage), findsNothing);
      expect(find.text(_key), findsNothing);
      expect(host.created, isEmpty);
    });
  });

  group('showIosNativeSecretSheet', () {
    /// Taps a launcher that calls [showIosNativeSecretSheet]; the record holds the call's own future.
    Future<({Future<void> shown})> reveal(WidgetTester tester,
        {String secret = _key, required VoidCallback onClassic, VoidCallback? onCopy, VoidCallback? after}) async {
      late Future<void> shown;
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () {
                shown = showIosNativeSecretSheet(context,
                    title: 'Key Created',
                    message: 'Your new key',
                    warning: 'Copy it now. You will not see it again.',
                    secretLabel: 'API Key',
                    secret: secret,
                    copyLabel: 'Copy',
                    doneLabel: 'Done',
                    onCopy: onCopy ?? () {},
                    showClassic: () async => onClassic());
                after?.call();
              },
              child: const Text('reveal')))));
      await tester.tap(find.text('reveal'));
      await tester.pumpAndSettle();
      return (shown: shown);
    }

    testWidgets('runs the classic dialog when the native presentation is unavailable', (tester) async {
      var classic = 0;
      await (await reveal(tester, onClassic: () => classic++)).shown;
      expect(classic, 1);
      expect(find.text(_key), findsNothing);
    });

    testWidgets('runs the classic dialog for a secret that cannot cross the bridge', (tester) async {
      final host = NativeTestHost.install();
      var classic = 0;
      await (await reveal(tester, secret: 'omi key\n', onClassic: () => classic++)).shown;
      expect(classic, 1);
      expect(host.created, isEmpty);
    });

    testWidgets('runs the classic dialog when no account owns the sheet', (tester) async {
      IosNativeSurface.debugNativeHostForTest = true;
      final previous = AuthService.installLocalHarnessTokenGateway(const _SignedOut());
      addTearDown(() {
        IosNativeSurface.debugNativeHostForTest = false;
        AuthService.installLocalHarnessTokenGateway(previous);
      });
      expect(AuthService.instance.captureSessionSnapshot(), isNull);
      var classic = 0;
      await (await reveal(tester, onClassic: () => classic++)).shown;
      expect(classic, 1);
      expect(find.text(_key), findsNothing);
    });

    testWidgets('never presents after a session change', (tester) async {
      final host = NativeTestHost.install();
      var classic = 0;
      await (await reveal(tester,
              onClassic: () => classic++, after: () => AuthService.instance.handleAuthUserChanged('another-owner')))
          .shown;
      expect(classic, 0, reason: 'The next owner gets no Flutter dialog with the previous owner\'s key either');
      expect(find.text(_key), findsNothing);
      expect(host.created, isEmpty);
    });

    testWidgets('shows the key with only the given labels, copies through the owner and pops on Done', (tester) async {
      NativeTestHost.install();
      var classic = 0;
      var copies = 0;
      final shown = (await reveal(tester, onClassic: () => classic++, onCopy: () => copies++)).shown;
      expect(classic, 0);
      expect(find.text(_key), findsOneWidget);
      expect(find.text('Key Created'), findsOneWidget);
      await tester.tap(find.text('Copy'));
      expect(copies, 1);
      var closed = false;
      unawaited(shown.then((_) => closed = true));
      await tester.pump();
      expect(closed, false, reason: 'Only Done closes the one-time sheet');
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(closed, true);
      expect(find.text(_key), findsNothing);
    });
  });
}

final class _SignedOut implements AuthTokenGateway {
  const _SignedOut();

  @override
  AuthUserSnapshot? get currentUser => null;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}
