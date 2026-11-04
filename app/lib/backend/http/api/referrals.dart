import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:omi/services/auth/auth_token_result.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

const mobileReferralCampaignEnabled = bool.fromEnvironment('OMI_MOBILE_REFERRAL_CAMPAIGN', defaultValue: false);

Future<String> getReferralLink({required AuthSessionSnapshot session}) async {
  if (!mobileReferralCampaignEnabled) throw StateError('Referral campaign is disabled');
  final response = await makeRawApiCall(
    url: '${Env.apiBaseUrl}v1/users/me/referral',
    method: 'GET',
    sessionSnapshot: session,
    timeout: const Duration(seconds: 20),
  );
  final materialized = await http.Response.fromStream(response);
  if (materialized.statusCode != 200) throw StateError('Referral link unavailable');
  final value = (jsonDecode(materialized.body) as Map<String, dynamic>)['referral_url'];
  return validateReferralLink(value);
}

String validateReferralLink(Object? value) {
  final uri = value is String ? Uri.tryParse(value) : null;
  if (uri == null ||
      uri.scheme != 'https' ||
      !const {'omi.me', 'api.omiapi.com'}.contains(uri.host) ||
      uri.hasPort ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      !RegExp(r'^/r/ref1\.[A-Za-z0-9_-]{2,171}\.[A-Za-z0-9_-]{43}$').hasMatch(uri.path) ||
      uri.toString() != value) {
    throw const FormatException('Invalid referral URL');
  }
  return value as String;
}
