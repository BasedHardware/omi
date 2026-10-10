import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('clearUserDisplayCache clears aiConsentGiven and onboardingCompleted on session expiry', () async {
    final prefs = SharedPreferencesUtil();
    prefs.aiConsentGiven = true;
    prefs.onboardingCompleted = true;
    prefs.uid = 'user-123';
    prefs.email = 'test@example.com';

    expect(prefs.aiConsentGiven, isTrue);
    expect(prefs.onboardingCompleted, isTrue);

    prefs.clearUserDisplayCache();

    expect(prefs.aiConsentGiven, isFalse);
    expect(prefs.onboardingCompleted, isFalse);
    expect(prefs.uid, isEmpty);
    expect(prefs.email, isEmpty);
  });
}
