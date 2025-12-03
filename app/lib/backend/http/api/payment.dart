import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

Future<Map<String, String>?> createCheckoutSession({required String priceId}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/checkout-session',
    headers: {},
    method: 'POST',
    body: jsonEncode({'price_id': priceId}),
  );
  if (response != null && response.statusCode == 200) {
    var jsonResponse = jsonDecode(response.body);
    debugPrint('createCheckoutSession response: ${response.body}');
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
    debugPrint('upgradeSubscription response: ${response.body}');
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
    debugPrint('getAppSubscription response: ${response.body}');
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
    debugPrint('getAvailablePlans response: ${response.body}');
    return jsonResponse;
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
    debugPrint('cancelAppSubscription response: ${response.body}');
    return jsonResponse;
  }
  return null;
}
