import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
const _fallback = 'complete flutter surface';
const _link = NativeRow('siri_shortcuts_link', 'Ask Omi', kind: 'shortcuts_link');

TestDefaultBinaryMessenger get _messenger => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

/// Answers the config channel's 'capabilities' with [reply] (a thrown [Exception] is rethrown) and
/// records every call; a null [reply] leaves the channel without a handler.
List<MethodCall> _answerCapabilities(Object? Function()? reply) {
  final calls = <MethodCall>[];
  _messenger.setMockMethodCallHandler(
    _config,
    reply == null
        ? null
        : (call) async {
            calls.add(call);
            final answer = reply();
            if (answer is Exception) throw answer;
            return answer;
          },
  );
  addTearDown(() => _messenger.setMockMethodCallHandler(_config, null));
  return calls;
}

void _enableHost() {
  IosNativeSurface.debugNativeHostForTest = true;
  addTearDown(() => IosNativeSurface.debugNativeHostForTest = false);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(debugResetNativeUiCapabilities);

  group('nativeUiCapabilities', () {
    test('flag-off and non-iOS builds answer nothing without a channel call', () async {
      final calls = _answerCapabilities(() => ['shortcuts_link']);
      expect(await nativeUiCapabilities(), isEmpty);
      expect(calls, isEmpty);
    });

    test('keeps only the allowlisted kinds the host reports', () async {
      _enableHost();
      final calls = _answerCapabilities(() => ['maps', 'shortcuts_link', 42, null]);
      expect(await nativeUiCapabilities(), {'shortcuts_link'});
      expect(calls.single.method, 'capabilities');
    });

    test('a host without the handler, a null or a malformed answer gives nothing', () async {
      _enableHost();
      _answerCapabilities(null);
      expect(await nativeUiCapabilities(), isEmpty);
      for (final answer in <Object? Function()>[
        () => null,
        () => {'shortcuts_link': true}
      ]) {
        debugResetNativeUiCapabilities();
        _answerCapabilities(answer);
        expect(await nativeUiCapabilities(), isEmpty);
      }
    });

    test('a host error gives nothing instead of throwing', () async {
      _enableHost();
      _answerCapabilities(() => PlatformException(code: 'unavailable'));
      expect(await nativeUiCapabilities(), isEmpty);
    });

    test('the answer is resolved once per process', () async {
      _enableHost();
      var answer = <Object?>['shortcuts_link'];
      final calls = _answerCapabilities(() => answer);
      final concurrent = await Future.wait([nativeUiCapabilities(), nativeUiCapabilities()]);
      answer = [];
      expect(await nativeUiCapabilities(), {'shortcuts_link'});
      expect(concurrent, [
        {'shortcuts_link'},
        {'shortcuts_link'}
      ]);
      expect(calls, hasLength(1));
    });
  });

  group('shortcuts_link rows', () {
    test('carry no value, options, symbol, action or media', () {
      expect(_link.valid, isTrue);
      expect(_link.projection['enabled'], isFalse);
      expect(_link.projection['value'], isNull);
      for (final forged in [
        const NativeRow('siri_shortcuts_link', 'Ask Omi', kind: 'shortcuts_link', value: 'open'),
        const NativeRow('siri_shortcuts_link', 'Ask Omi', kind: 'shortcuts_link', options: {'open': 'Open'}),
        const NativeRow('siri_shortcuts_link', 'Ask Omi', kind: 'shortcuts_link', symbol: 'link'),
        NativeRow('siri_shortcuts_link', 'Ask Omi', kind: 'shortcuts_link', action: (_) {}),
        const NativeRow('siri_shortcuts_link', 'Ask Omi',
            kind: 'shortcuts_link', imageUri: 'https://example.com/a.jpg'),
        const NativeRow('siri_shortcuts_link', 'Ask Omi', kind: 'shortcuts_link', points: [
          {'x': 0, 'y': 0, 'label': ''}
        ]),
        const NativeRow('siri_shortcuts_link', 'Ask Omi', kind: 'shortcuts_link', blocks: [
          {'kind': 'text', 'text': 'a', 'indent': 0, 'prefix': ''}
        ]),
      ]) {
        expect(forged.valid, isFalse, reason: '${forged.projection}');
      }
    });

    test('never dispatch a command', () async {
      await expectLater(
        dispatchNativeAction(const MethodCall('action', {'id': 'siri_shortcuts_link'}),
            isActive: () => true, rows: const [_link]),
        throwsA(isA<PlatformException>().having((error) => error.code, 'code', 'invalid_native_action')),
      );
    });

    testWidgets('render natively inside a section', (tester) async {
      final host = NativeTestHost.install();
      await tester
          .pumpWidget(NativeTestHost.app(const IosNativeSurface(title: 'Siri', fallback: Text(_fallback), sections: [
        NativeSection('siri_shortcuts', [_link])
      ])));
      await NativeTestHost.settle(tester);
      expect(find.text(_fallback), findsNothing);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(host.created, hasLength(1));
      expect(tester.takeException(), isNull);
    });

    testWidgets('outside sections fall back to the complete Flutter surface', (tester) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(const IosNativeSurface(
          title: 'Siri', fallback: Text(_fallback), toolbar: [_link], sections: [NativeSection('siri', [])])));
      await NativeTestHost.settle(tester);
      expect(find.text(_fallback), findsOneWidget);
      expect(host.created, isEmpty);
      expect(tester.takeException(), isNull);
    });

    testWidgets('in a modal keep the Flutter dialog', (tester) async {
      NativeTestHost.install();
      final presented = _answerCapabilities(() => null);
      late BuildContext context;
      await tester.pumpWidget(NativeTestHost.app(Builder(builder: (inner) {
        context = inner;
        return const SizedBox();
      })));
      final inActions = await showIosNativeModal(context, title: 'Siri', actions: const [
        NativeRow('cancel', 'Cancel'),
        _link,
      ]);
      final inSections = await showIosNativeModal(context, title: 'Siri', actions: const [
        NativeRow('cancel', 'Cancel')
      ], sections: const [
        NativeSection('siri', [_link])
      ]);
      expect(inActions, isNull);
      expect(inSections, isNull);
      expect(presented, isEmpty);
    });
  });
}
