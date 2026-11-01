import 'dart:async';
import 'dart:io';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;
import 'package:omi/env/env.dart';
import 'package:path_provider/path_provider.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/services/telemetry/client_telemetry_outbox.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Wires the process-wide client telemetry transport. Safe to call when the
/// migration flag is off; sending still no-ops until observations are enqueued.
void installClientTelemetryTransport() {
  final telemetry = ClientTelemetry.instance;
  telemetry.ownerId = () => FirebaseAuth.instance.currentUser?.uid;
  telemetry.platform = () {
    if (PlatformService.isIOS) return 'ios';
    if (PlatformService.isAndroid) return 'android';
    return null;
  };
  telemetry.channel = () {
    try {
      if (Env.isTestFlight || Env.profile == AppEnvironmentProfile.mobileBeta) return 'beta';
      if (Env.profile == AppEnvironmentProfile.production) return 'production';
    } catch (_) {}
    return null;
  };
  telemetry.outbox.attachStore(FileTelemetryStore(getApplicationSupportDirectory));
  telemetry.outbox.tokenFor = (ownerId, {required bool forceRefresh}) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null || user.uid != ownerId) return null;
    if (forceRefresh) return user.getIdToken(true);
    return AuthService.instance.getIdToken();
  };
  telemetry.outbox.post = _postBatch;
}

Future<TelemetryHttpResult> _postBatch({
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
          Uri.parse('${root}v1/telemetry/client/batches'),
          headers: {
            'Authorization': 'Bearer $token',
            'Content-Type': 'application/json',
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
