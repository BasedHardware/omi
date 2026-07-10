import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/misc_wire.g.dart' as misc_wire;
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<Map<String, dynamic>?> createCheckoutSession({required String priceId, String? promotionCode}) async {
  final body = <String, dynamic>{'price_id': priceId};
  if (promotionCode != null && promotionCode.trim().isNotEmpty) {
    body['promotion_code'] = promotionCode.trim();
  }
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/checkout-session',
    headers: {},
    method: 'POST',
    body: jsonEncode(body),
  );
  if (response != null && response.statusCode == 200) {
    final jsonResponse = jsonDecode(response.body) as Map<String, dynamic>;
    final generated = wire.GeneratedPaymentCheckoutSessionResponse.fromJson(jsonResponse);
    Logger.debug('createCheckoutSession response: ${response.body}');

    // Check if this is a reactivation response
    if (generated.status == 'reactivated') {
      if (generated.message == null || generated.nextBillingDate == null) {
        return null;
      }
      return {'status': generated.status, 'message': generated.message, 'next_billing_date': generated.nextBillingDate};
    }

    // Otherwise, it's a checkout session
    if (generated.url == null || generated.sessionId == null) {
      return null;
    }
    return {'url': generated.url, 'session_id': generated.sessionId};
  }
  return null;
}

Future<bool> cancelSubscription({String? reason, String? reasonDetails}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/subscription',
    headers: {},
    method: 'DELETE',
    body: reason != null ? jsonEncode({'reason': reason, 'reason_details': reasonDetails}) : '',
  );
  if (response != null && response.statusCode == 200) {
    final generated = wire.GeneratedPaymentStatusMessageResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    return generated.status == 'ok';
  }
  return false;
}

Future<Map<String, dynamic>?> upgradeSubscription({required String priceId, String? promotionCode}) async {
  final body = <String, dynamic>{'price_id': priceId};
  if (promotionCode != null && promotionCode.trim().isNotEmpty) {
    body['promotion_code'] = promotionCode.trim();
  }
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/upgrade-subscription',
    headers: {},
    method: 'POST',
    body: jsonEncode(body),
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    final generated = wire.GeneratedPaymentUpgradeSubscriptionResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    Logger.debug('upgradeSubscription response: ${response.body}');
    return generated.toJson();
  }
  if (response.statusCode == 400) {
    try {
      final errorBody = misc_wire.GeneratedErrorResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      return {'error': true, 'detail': errorBody.detail};
    } catch (_) {
      return {'error': true};
    }
  }
  return null;
}

Future<Map<String, dynamic>?> getAppSubscription(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/subscription',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response != null && response.statusCode == 200) {
    var jsonResponse = wire.GeneratedAppSubscriptionResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).toJson();
    Logger.debug('getAppSubscription response: ${response.body}');
    return jsonResponse;
  }
  return null;
}

Future<Map<String, dynamic>?> getAvailablePlans() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/available-plans',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response != null && response.statusCode == 200) {
    var jsonResponse = wire.GeneratedAvailablePlansResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).toJson();
    Logger.debug('getAvailablePlans response: ${response.body}');
    return jsonResponse;
  }
  return null;
}

Future<Map<String, String>?> createCustomerPortalSession() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/customer-portal',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response != null && response.statusCode == 200) {
    final generated = wire.GeneratedCustomerPortalSessionResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
    Logger.debug('createCustomerPortalSession response: ${response.body}');
    return {'url': generated.url};
  }
  return null;
}

Future<Map<String, dynamic>?> cancelAppSubscription(String appId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/apps/$appId/subscription',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response != null && response.statusCode == 200) {
    var jsonResponse = wire.GeneratedAppSubscriptionCancelResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    ).toJson();
    Logger.debug('cancelAppSubscription response: ${response.body}');
    return jsonResponse;
  }
  return null;
}
