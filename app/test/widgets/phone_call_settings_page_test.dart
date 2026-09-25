import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/phone_calls/phone_setup_intro_page.dart';
import 'package:omi/pages/settings/phone_call_settings_page.dart';
import 'package:omi/providers/phone_call_provider.dart';

/// Drives [PhoneCallSettingsPage] without the network: numbers, load state and delete are faked.
class _FakePhoneCallProvider extends PhoneCallProvider {
  _FakePhoneCallProvider({required List<VerifiedPhoneNumber> numbers, this.loaded = true})
      : _numbers = numbers,
        super.forTesting();

  List<VerifiedPhoneNumber> _numbers;
  bool loaded;
  int loadCalls = 0;
  final List<String> deleted = [];

  @override
  bool get numbersLoaded => loaded;

  @override
  List<VerifiedPhoneNumber> get verifiedNumbers => _numbers;

  @override
  Future<void> loadVerifiedNumbers() async {
    loadCalls++;
  }

  @override
  Future<bool> deleteNumber(String phoneNumberId) async {
    deleted.add(phoneNumberId);
    _numbers = _numbers.where((n) => n.id != phoneNumberId).toList();
    notifyListeners();
    return true;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const eventChannelName = 'com.omi/phone_calls/events';
  const codec = StandardMethodCodec();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() {
    messenger.setMockMessageHandler(eventChannelName, (ByteData? message) async => codec.encodeSuccessEnvelope(null));
  });
  tearDown(() => messenger.setMockMessageHandler(eventChannelName, null));

  Widget host(PhoneCallProvider provider) {
    return ChangeNotifierProvider<PhoneCallProvider>.value(
      value: provider,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: PhoneCallSettingsPage(),
      ),
    );
  }

  testWidgets('reloads numbers on open and shows a spinner until they arrive', (tester) async {
    final provider = _FakePhoneCallProvider(numbers: const [], loaded: false);
    addTearDown(provider.dispose);
    await tester.pumpWidget(host(provider));
    await tester.pump();

    expect(provider.loadCalls, 1);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('with no verified number offers the setup flow', (tester) async {
    final provider = _FakePhoneCallProvider(numbers: const []);
    addTearDown(provider.dispose);
    await tester.pumpWidget(host(provider));
    await tester.pump();

    expect(find.text('No Verified Numbers'), findsOneWidget);
    await tester.tap(find.text('Get Started'));
    await tester.pumpAndSettle();
    expect(find.byType(PhoneSetupIntroPage), findsOneWidget);
  });

  testWidgets('delete asks first with a destructive Delete, then removes the number', (tester) async {
    final provider = _FakePhoneCallProvider(
      numbers: [
        VerifiedPhoneNumber(
          id: 'n1',
          isPrimary: true,
          phoneNumber: '+14155550100',
          verifiedAt: DateTime(2025, 1, 2, 12).toUtc().toIso8601String(), // local noon: "Jan 2" in every zone
        ),
      ],
    );
    addTearDown(provider.dispose);
    await tester.pumpWidget(host(provider));
    await tester.pump();

    expect(find.text('+14155550100'), findsOneWidget);
    expect(find.text('Verified on Jan 2, 2025'), findsOneWidget);

    await tester.tap(find.byTooltip('Delete'));
    await tester.pumpAndSettle();
    expect(find.text('Delete +14155550100?'), findsOneWidget);
    expect(provider.deleted, isEmpty);

    await tester.tap(find.widgetWithText(TextButton, 'Delete'));
    await tester.pumpAndSettle();
    expect(provider.deleted, ['n1']);
    expect(find.text('No Verified Numbers'), findsOneWidget);
  });
}
