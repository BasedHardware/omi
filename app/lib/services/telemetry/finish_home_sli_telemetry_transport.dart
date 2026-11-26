// Authenticated transport for content-free Finish cut observations.
// Uses a dedicated local outbox and the fixed beta API authority.
import 'dart:async';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'package:omi/env/env.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/telemetry/client_telemetry_outbox.dart';
import 'package:omi/services/telemetry/finish_home_sli_telemetry.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:path_provider/path_provider.dart';

/// Installs a dedicated authenticated outbox without enabling general telemetry.
void installFinishHomeSliTelemetryTransport() {
  final telemetry = FinishHomeSliTelemetry.instance;
  telemetry.testFlightEnabled = () => Env.isTestFlight && !Env.hasApiBaseUrlOverride;
  telemetry.ownerId = () => FirebaseAuth.instance.currentUser?.uid;
  telemetry.platform = () {
    if (PlatformService.isIOS) return 'ios';
    if (PlatformService.isAndroid) return 'android';
    return null;
  };
  telemetry.outbox.attachStore(
    FileTelemetryStore(
      getApplicationSupportDirectory,
      fileName: 'finish_home_sli_outbox.json',
    ),
  );
  telemetry.outbox.tokenFor = (ownerId, {required bool forceRefresh}) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null || user.uid != ownerId) return null;
    if (forceRefresh) return user.getIdToken(true);
    return AuthService.instance.getIdToken();
  };
  telemetry.outbox.post = _postFinishCuts;
  telemetry.start();
}

Future<TelemetryHttpResult> _postFinishCuts({
  required String ownerId,
  required String token,
  required String body,
  required Duration timeout,
}) async {
  if (ownerId.isEmpty) return const TelemetryHttpResult.network();
  final base = Env.apiBaseUrl;
  if (base == null || base.isEmpty) return const TelemetryHttpResult.network();
  final root = base.endsWith('/') ? base : '$base/';
  try {
    final response = await http
        .post(
          Uri.parse('${root}v1/telemetry/v3-finish-cuts'),
          headers: {
            'Authorization': 'Bearer $token',
            'Content-Type': 'application/json',
            'X-Omi-App-Channel': 'beta',
          },
          body: body,
        )
        .timeout(timeout);
    return TelemetryHttpResult.http(
      statusCode: response.statusCode,
      body: response.body,
      retryAfterHeader: response.headers['retry-after'],
    );
  } on TimeoutException {
    return const TelemetryHttpResult.timeout();
  } on SocketException {
    return const TelemetryHttpResult.network();
  } catch (_) {
    return const TelemetryHttpResult.network();
  }
}
