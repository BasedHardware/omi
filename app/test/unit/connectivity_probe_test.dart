import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/services/capture/capture_coordinator.dart';
import 'package:omi/services/connectivity_service.dart';

CaptureEnvironment captureEnvironment(bool connected) => CaptureEnvironment(
      policyMuted: false,
      paused: false,
      batchModeEnabled: false,
      batchModeSuspendedForOnboarding: false,
      deviceSupportsTranscribeLater: true,
      networkConnected: connected,
      signedIn: () => true,
      phoneMicSupportsBatch: true,
      transcriptReady: false,
      socketConnected: false,
      deviceServiceReady: false,
      callActive: false,
      deviceRecording: false,
      micCapturing: false,
    );

void main() {
  test('production has independent China-oriented alternatives and never probes Omi', () {
    final options = connectivityProbeOptions(
      physicalQualification: false,
      profile: AppEnvironmentProfile.production,
      apiBaseUrl: 'https://api.omi.me/',
    );
    expect(options.map((o) => o.uri.host).toSet(), {'one.one.one.one', 'www.baidu.com', 'www.taobao.com'});
    for (final option in options) {
      expect(option.timeout, const Duration(seconds: 3));
      expect(option.responseStatusFn(http.Response('', 200)), isTrue);
      for (final status in [204, 301, 403, 429, 500]) {
        expect(option.responseStatusFn(http.Response('', status)), isFalse);
      }
    }
  });

  test('local/non-prod and qualification use only their configured API fixture', () {
    for (final profile in AppEnvironmentProfile.values.where((p) => p != AppEnvironmentProfile.production)) {
      final options = connectivityProbeOptions(
        physicalQualification: false,
        profile: profile,
        apiBaseUrl: 'http://192.168.1.2:8080/private/',
      );
      expect(options.single.uri, Uri.parse('http://192.168.1.2:8080/private/v1/health'));
    }
    final options = connectivityProbeOptions(
      physicalQualification: true,
      profile: AppEnvironmentProfile.production,
      apiBaseUrl: 'http://127.0.0.1:8080/',
    );
    expect(options.single.uri, Uri.parse('http://127.0.0.1:8080/v1/health'));
    final accidentalProdOverride = connectivityProbeOptions(
      physicalQualification: false,
      profile: AppEnvironmentProfile.localProd,
      apiBaseUrl: 'https://api.omi.me/',
    );
    expect(accidentalProdOverride.any((o) => o.uri.host == 'api.omi.me'), isFalse);
  });

  for (final successfulHost in ['www.baidu.com', 'www.taobao.com']) {
    test('real package uses HEAD and any $successfulHost success keeps capture live', () async {
      final seen = <String>[];
      final connected = await http.runWithClient(
        () => createConnectivityChecker(
          physicalQualification: false,
          profile: AppEnvironmentProfile.production,
          apiBaseUrl: 'https://api.omi.me/',
        ).hasInternetAccess,
        () => MockClient((request) async {
          expect(request.method, 'HEAD');
          seen.add(request.url.host);
          if (request.url.host == 'one.one.one.one') throw const SocketException('blocked');
          return http.Response('', request.url.host == successfulHost ? 200 : 503);
        }),
      );
      expect(seen.toSet(), {'one.one.one.one', 'www.baidu.com', 'www.taobao.com'});
      expect(connected, isTrue);
      final transition = transitionCapture(
        CaptureCoordinatorState.idle(),
        const PhoneStartRequested(),
        captureEnvironment(connected),
      );
      expect(transition.state.phase, CapturePhase.phoneLive);
      expect(transition.state.active!.mode, CaptureTransport.live);
    });
  }

  test('actual failed HEAD probes select automatic batch transport in the production reducer', () async {
    final connected = await http.runWithClient(
      () => createConnectivityChecker(
        physicalQualification: false,
        profile: AppEnvironmentProfile.production,
        apiBaseUrl: 'https://api.omi.me/',
      ).hasInternetAccess,
      () => MockClient((request) async {
        if (request.url.host == 'one.one.one.one') throw const SocketException('blocked');
        return http.Response('', 503);
      }),
    );
    expect(connected, isFalse);
    final transition = transitionCapture(
      CaptureCoordinatorState.idle(),
      const PhoneStartRequested(),
      captureEnvironment(connected),
    );
    expect(transition.state.phase, CapturePhase.phoneBatchLive);
    expect(transition.state.active!.mode, CaptureTransport.batch);
    final start =
        transition.effects.whereType<RunStage>().map((e) => e.stage).whereType<StartPhoneSessionStage>().single;
    expect(start.mode, CaptureTransport.batch);
  });

  test('a failed private fixture cannot be masked by healthy public internet', () async {
    final seen = <Uri>[];
    final connected = await http.runWithClient(
      () => createConnectivityChecker(
        physicalQualification: false,
        profile: AppEnvironmentProfile.localDev,
        apiBaseUrl: 'http://127.0.0.1:8000/',
      ).hasInternetAccess,
      () => MockClient((request) async {
        seen.add(request.url);
        return http.Response('', 503);
      }),
    );
    expect(connected, isFalse);
    expect(seen, [Uri.parse('http://127.0.0.1:8000/v1/health')]);
  });
}
