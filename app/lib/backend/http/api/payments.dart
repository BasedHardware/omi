import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/payments/models/payment_method_config.dart';
import 'package:omi/utils/logger.dart';

Future<Map<String, dynamic>?> getStripeAccountLink(String? country) async {
  try {
    var url = '${Env.apiBaseUrl}v1/stripe/connect-accounts';
    if (country != null) {
      url += '?country=$country';
    }
    var response = await makeApiCall(
      url: url,
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

Future<bool> savePayPalDetails(String email, String link) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/paypal/payment-details',
      headers: {},
      body: jsonEncode({'email': email, 'paypalme_url': link}),
      method: 'POST',
    );
    if (response == null || response.statusCode != 200) {
      return false;
    }
    return true;
  } catch (e) {
    Logger.error(e);
    return false;
  }
}

Future<Map<String, dynamic>?> fetchPaymentMethodsStatus() async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/payment-methods/status',
      headers: {},
      body: '',
      method: 'GET',
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

Future<PayPalDetails?> fetchPayPalDetails() async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/paypal/payment-details',
      headers: {},
      body: '',
      method: 'GET',
    );
    if (response == null || response.statusCode != 200) {
      return null;
    }
    return PayPalDetails.fromJson(jsonDecode(response.body));
  } catch (e) {
    Logger.error(e);
    return null;
  }
}

Future<bool> setDefaultPaymentMethod(String method) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/payment-methods/default',
      headers: {},
      body: jsonEncode({'method': method}),
      method: 'POST',
    );
    if (response == null || response.statusCode != 200) {
      return false;
    }
    return true;
  } catch (e) {
    Logger.error(e);
    return false;
  }
}

Future<List?> getStripeSupportedCountries() async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/stripe/supported-countries',
      headers: {},
      body: '',
      method: 'GET',
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
