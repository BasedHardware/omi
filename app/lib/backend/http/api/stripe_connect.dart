import 'dart:convert';

import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/utils/logger.dart';

Future<Map<String, dynamic>?> getStripeAccountLink() async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/stripe/create-connect-account',
      headers: {},
      body: '',
      method: 'POST',
    );
    if (response == null || response.statusCode != 200) {
      return null;
    }
    return jsonDecode(response.body);
  } catch (e) {
    Logger.error(e);
    return null;
  }
}

Future<bool> isStripeOnboardingComplete() async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/stripe/onboarded',
      headers: {},
      body: '',
      method: 'GET',
    );
    if (response == null || response.statusCode != 200) {
      return false;
    }
    return jsonDecode(response.body)['onboarding_complete'];
  } catch (e) {
    Logger.error(e);
    return false;
  }
}
