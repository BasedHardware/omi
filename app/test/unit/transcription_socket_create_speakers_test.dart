import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';

void main() {
  setUpAll(() {
    Env.init(_TestEnvFields());
  });

  Uri socketUri() {
    final service = TranscriptSegmentSocketService.create(16000, BleAudioCodec.pcm16, 'en');
    final url = (service.socket as PureSocket).url;
    expect(Env.apiBaseUrl, isNotNull);
    expect(url, isNot(contains('api.omi.me')));
    return Uri.parse(url);
  }

  test('create_speakers stays true with a legacy persisted false', () async {
    SharedPreferences.setMockInitialValues({'autoCreateSpeakersEnabled': false});
    await SharedPreferencesUtil.init();

    expect(socketUri().queryParameters['create_speakers'], 'true');
  });

  test('create_speakers stays true with no persisted override', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    expect(socketUri().queryParameters['create_speakers'], 'true');
  });
}

class _TestEnvFields implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.example.test/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}
