import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_phone_projection.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/pages/phone_calls/phone_calls_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/usage_provider.dart';

class FakeNativeCallOwner extends PhoneCallProvider {
  FakeNativeCallOwner() : super.forTesting();
  PhoneCallState state = PhoneCallState.idle;
  final commands = <String>[];
  @override
  PhoneCallState get callState => state;
  @override
  bool get numbersLoaded => true;
  @override
  List<VerifiedPhoneNumber> get verifiedNumbers => [
        const VerifiedPhoneNumber(id: 'caller', isPrimary: true, phoneNumber: '+3725142537', verifiedAt: '2026-01-01'),
      ];
  @override
  Future<void> loadVerifiedNumbers() async {}
  @override
  Future<bool> startCall(String number) async {
    commands.add('dial:$number');
    return false;
  }

  @override
  String? get remoteNumber => '+14155550100';
  @override
  String? get contactName => 'Avery';
  @override
  Duration get callDuration => const Duration(seconds: 125);
  @override
  TranscriptionStatus get transcriptionStatus => TranscriptionStatus.noAudio;
  @override
  List<TranscriptSegment> get transcriptSegments => [
        TranscriptSegment(
            id: 'segment',
            text: 'Say **two stars**',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0,
            end: 2,
            translations: [const Translation(lang: 'es', text: 'Dos estrellas')])
      ];
  @override
  String getSpeakerLabel(TranscriptSegment segment) => 'You';
  @override
  void toggleMute() => commands.add('mute');
  @override
  void toggleSpeaker() => commands.add('speaker');
  @override
  Future<void> endCall() async => commands.add('end');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const contacts = MethodChannel('flutter_contacts');
  const events = 'com.omi/phone_calls/events';
  var denied = false;
  setUp(() {
    denied = false;
    messenger.setMockMessageHandler(events, (_) async => const StandardMethodCodec().encodeSuccessEnvelope(null));
    messenger.setMockMethodCallHandler(contacts, (call) async {
      if (call.method == 'permissions.request') return denied ? 'denied' : 'granted';
      if (call.method == 'crud.getAll') {
        return [
          const Contact(id: 'b', displayName: 'Bea', phones: [Phone(number: '514 2537')]).toJson(),
          const Contact(id: 'a', displayName: 'Avery', phones: [Phone(number: '+1 (415) 555-0100')]).toJson(),
        ];
      }
      return null;
    });
  });
  tearDown(() {
    messenger.setMockMessageHandler(events, null);
    messenger.setMockMethodCallHandler(contacts, null);
  });

  Future<FakeNativeCallOwner> host(WidgetTester tester, Widget page,
      {PhoneCallState state = PhoneCallState.idle}) async {
    final owner = FakeNativeCallOwner()..state = state;
    addTearDown(owner.dispose);
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<PhoneCallProvider>.value(value: owner),
          ChangeNotifierProvider(create: (_) => UsageProvider()),
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: page)));
    await tester.pumpAndSettle();
    return owner;
  }

  IosNativeSurface surface(WidgetTester tester) => tester.widget(find.byType(IosNativeSurface).first);
  NativeRow row(WidgetTester tester, String id) => [
        ...surface(tester).toolbar,
        ...surface(tester).sections.expand((s) => s.rows),
        ...?surface(tester).chat?.actions,
      ].singleWhere((row) => row.id == id);

  testWidgets('active call projects plain transcript, translations and original controls without making a call',
      (tester) async {
    final owner = await host(tester, const ActiveCallPage(), state: PhoneCallState.active);
    expect(owner.commands, isEmpty);
    expect(row(tester, 'call_segment_0').title, 'Say **two stars**');
    expect(row(tester, 'call_segment_0').plainText, true);
    expect(row(tester, 'call_segment_0').subtitle, 'You\nDos estrellas');
    expect(row(tester, 'call_transcription_status').title, isNotEmpty);
    expect(row(tester, 'call_state').title, '2:05');
    await row(tester, 'call_mute').action!(null);
    await row(tester, 'call_speaker').action!(null);
    await row(tester, 'call_end').action!(null);
    expect(owner.commands, ['mute', 'speaker', 'end']);
  });

  testWidgets('connecting call keeps minimize and hang-up reachable while audio controls wait', (tester) async {
    await host(tester, const ActiveCallPage(), state: PhoneCallState.connecting);
    expect(row(tester, 'call_back').enabled, true);
    expect(row(tester, 'call_end').enabled, true);
    for (final id in ['call_mute', 'call_speaker', 'call_audio_route', 'call_keypad']) {
      expect(row(tester, id).enabled, false);
    }
  });

  testWidgets('contacts keep sorting/filtering and dial the original formatted international number only on selection',
      (tester) async {
    final owner = await host(tester, const PhoneCallsPage());
    final contactRows =
        surface(tester).sections.expand((s) => s.rows).where((row) => row.id.startsWith('phone_contact_'));
    expect(contactRows.map((row) => row.title), ['Avery', 'Bea']);
    expect(owner.commands, isEmpty);
    await surface(tester).search!('avery');
    await tester.pump();
    expect(surface(tester).sections.expand((s) => s.rows).any((row) => row.id == 'phone_contact_b'), false);
    await row(tester, 'phone_contact_a').action!(null);
    await tester.pump();
    expect(owner.commands, ['dial:+14155550100']);
  });

  testWidgets('native keypad edits never dial until Call and use the original verified-country prefix', (tester) async {
    final owner = await host(tester, const PhoneCallsPage());
    await row(tester, 'phone_tab').action!('1');
    await tester.pumpAndSettle();
    expect(row(tester, 'phone_call').enabled, false);
    for (final key in ['5', '1', '4', '2', '5', '3', '7']) {
      await row(tester, 'phone_keypad').action!(key);
      await tester.pump();
    }
    expect(owner.commands, isEmpty);
    expect(row(tester, 'phone_keypad').value, '5142537');
    await row(tester, 'phone_call').action!(null);
    await tester.pump();
    expect(owner.commands, ['dial:+3725142537']);
    await row(tester, 'phone_keypad').action!('erase');
    await tester.pump();
    expect(row(tester, 'phone_keypad').value, '514253');
    await row(tester, 'phone_keypad').action!('clear');
    await tester.pump();
    expect(row(tester, 'phone_keypad').value, '');
    expect(row(tester, 'phone_call').enabled, false);
  });

  testWidgets('denied contacts stay behind the original permission action and keypad remains accessible',
      (tester) async {
    denied = true;
    await host(tester, const PhoneCallsPage());
    expect(row(tester, 'phone_permission_allow').enabled, true);
    expect(surface(tester).search, isNull);
    await row(tester, 'phone_tab').action!('1');
    await tester.pumpAndSettle();
    expect(row(tester, 'phone_keypad').valid, true);
  });

  test('keypad contracts reject arbitrary DTMF and dialer metadata on unrelated controls', () {
    final dtmf = nativePhoneKeypad(id: 'dtmf', title: 'Keypad', digits: '', action: (_) {}, dtmf: true);
    expect(dtmf.valid, true);
    expect(dtmf.accepts('#'), true);
    for (final value in ['+', 'erase', 'clear', '12', null, true]) {
      expect(dtmf.accepts(value), false);
    }
    expect(const NativeRow('button', 'Button', keypadMode: 'dialer').valid, false);
    expect(const NativeRow('button', 'Button', plainText: true).valid, false);
    expect(const NativeRow('keypad', 'Keypad', kind: 'keypad', value: '', keypadMode: 'dialer').valid, false);
  });
}
