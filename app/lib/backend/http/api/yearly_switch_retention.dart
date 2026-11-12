import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// Optional admission, not a billing mutation. Lost responses consume admission.
Future<wire.GeneratedYearlySwitchResponse?> claimYearlyRetention(String placement) async {
  try {
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/payments/yearly-switch-retention?placement=$placement',
      headers: {},
      method: 'POST',
      body: '',
    );
    if (response?.statusCode != 200) return null;
    return wire.GeneratedYearlySwitchResponse.fromJson(jsonDecode(response!.body) as Map<String, dynamic>);
  } catch (_) {
    return null;
  }
}

Future<bool> yearlyRetentionEnabled() async {
  try {
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/payments/yearly-switch-retention',
      headers: {},
      method: 'GET',
      body: '',
    );
    if (response?.statusCode != 200) return false;
    return wire.GeneratedYearlySwitchResponse.fromJson(jsonDecode(response!.body) as Map<String, dynamic>).eligible;
  } catch (_) {
    return false;
  }
}
