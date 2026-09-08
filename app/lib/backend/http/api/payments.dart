import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/pages/payments/models/payment_method_config.dart';
import 'package:omi/utils/logger.dart';

Future<Map<String, dynamic>?> getStripeAccountLink(String? country) async {
  try {
    var url = '${Env.apiBaseUrl}v1/stripe/connect-accounts';
    if (country != null) {
      url += '?country=$country';
    }
    var response = await makeApiCall(url: url, headers: {}, body: '', method: 'POST');
    if (response == null || response.statusCode != 200) {
      return null;
    }
    return wire.GeneratedStripeConnectAccountResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).toJson();
  } catch (e) {
    Logger.error(e);
    return null;
  }
}

Future<bool> isStripeOnboardingComplete() async {
  try {
    var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/stripe/onboarded', headers: {}, body: '', method: 'GET');
    if (response == null || response.statusCode != 200) {
      return false;
    }
    return wire.GeneratedStripeOnboardingStatusResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).onboardingComplete;
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
    wire.GeneratedPaymentMutationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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
    return wire.GeneratedPaymentMethodStatusResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).toJson();
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
    final generated = wire.GeneratedPayPalPaymentDetailsResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return PayPalDetails(email: generated.email, link: generated.paypalmeUrl);
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
    wire.GeneratedPaymentMutationResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
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
    final countries = jsonDecode(response.body) as List<dynamic>;
    return countries
        .map((country) => wire.GeneratedStripeSupportedCountryResponse.fromJson(country as Map<String, dynamic>))
        .map((country) => country.toJson())
        .toList();
  } catch (e) {
    Logger.error(e);
    return null;
  }
}
