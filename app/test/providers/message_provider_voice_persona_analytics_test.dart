import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

class _VoiceAnalyticsAdapter implements AnalyticsAdapter {
  final List<MapEntry<String, Map<String, Object?>>> events = [];
  bool _initialized = false;

  @override
  Future<void> init() async {
    _initialized = true;
  }

  @override
  bool get isInitialized => _initialized;

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(MapEntry(eventName, properties ?? const {}));
  }

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}
}

App _personaApp() => App(
      id: 'persona-app',
      name: 'Persona App',
      author: 'Author',
      description: 'persona-only app',
      image: 'https://example.com/a.png',
      capabilities: {'persona'},
      status: 'approved',
      category: 'productivity-and-organization',
      approved: true,
      deleted: false,
      enabled: true,
      isPaid: false,
      isUserPaid: false,
      ratingCount: 0,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('dev.fluttercommunity.plus/package_info'),
      (call) async => {'appName': 'omi', 'packageName': 'com.omi.test', 'version': '0.0.0', 'buildNumber': '1'},
    );
    try {
      Env.init(_TestEnvFields());
    } catch (_) {
      // Env is a late final singleton and may already be initialized in this isolate.
    }
  });

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({'deviceIdHash': 'test-device-hash'});
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('a voice turn with a persona app selected is not reported as persona chat', () async {
    final adapter = _VoiceAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await PlatformManager.initializeServices();
    await AnalyticsManager.init();
    await AnalyticsManager.flushPending(force: true);
    adapter.events.clear();

    final appProvider = AppProvider();
    addTearDown(appProvider.dispose);
    appProvider.apps = [_personaApp()];
    appProvider.setSelectedChatAppId('persona-app');

    final provider = MessageProvider(
      voiceAudioFileSaver: (_, __, ___) async => File('/tmp/unused-voice-question.opus'),
      voiceReplyStreamer: (_, {language}) async* {
        yield ServerMessageChunk(
          'voice-message-id',
          'No speech was detected.',
          MessageChunkType.error,
          errorCode: 'no_speech',
        );
      },
    );
    addTearDown(provider.dispose);
    provider.updateAppProvider(appProvider);

    await provider.sendVoiceMessageStreamToServer(
      [
        <int>[1, 2, 3]
      ],
      codec: BleAudioCodec.opus,
    );

    await AnalyticsManager.flushPending(force: true);
    final voiceEvent = adapter.events.singleWhere((e) => e.key == 'Chat Voice Input Used');
    // The selection is visible in the target id, but the voice endpoint carries no
    // app field and the backend voice pipeline runs without an app persona, so the
    // turn must not be counted as persona chat until that contract changes.
    expect(voiceEvent.value['chat_target_id'], 'persona-app');
    expect(voiceEvent.value['is_persona_chat'], isFalse);
  });
}
