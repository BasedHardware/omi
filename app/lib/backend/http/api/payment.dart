import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<Map<String, dynamic>?> createCheckoutSession({required String priceId}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/checkout-session',
    headers: {},
    method: 'POST',
    body: jsonEncode({'price_id': priceId}),
  );
  if (response != null && response.statusCode == 200) {
    var jsonResponse = jsonDecode(response.body);
    Logger.debug('createCheckoutSession response: ${response.body}');

    // Check if this is a reactivation response
    if (jsonResponse.containsKey('status') && jsonResponse['status'] == 'reactivated') {
      return {
        'status': jsonResponse['status'] as String,
        'message': jsonResponse['message'] as String?,
        'next_billing_date': jsonResponse['next_billing_date'],
      };
    }

    // Otherwise, it's a checkout session
    return {
      'url': jsonResponse['url'] as String,
      'session_id': jsonResponse['session_id'] as String,
    };
  }
  return null;
}

Future<bool> cancelSubscription() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/subscription',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response != null && response.statusCode == 200) {
    return true;
  }
  return false;
}

Future<Map<String, dynamic>?> upgradeSubscription({required String priceId}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/upgrade-subscription',
    headers: {},
    method: 'POST',
    body: jsonEncode({'price_id': priceId}),
  );
  if (response != null && response.statusCode == 200) {
    var jsonResponse = jsonDecode(response.body);
    Logger.debug('upgradeSubscription response: ${response.body}');
    return jsonResponse;
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
    var jsonResponse = jsonDecode(response.body);
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
    var jsonResponse = jsonDecode(response.body);
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
    var jsonResponse = jsonDecode(response.body);
    Logger.debug('createCustomerPortalSession response: ${response.body}');
    return {
      'url': jsonResponse['url'] as String,
    };
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
    var jsonResponse = jsonDecode(response.body);
    Logger.debug('cancelAppSubscription response: ${response.body}');
    return jsonResponse;
  }
  return null;
}
