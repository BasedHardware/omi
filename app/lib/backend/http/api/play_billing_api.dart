// Google Play Billing purchase verification: the app hands the Play purchase token to the server,
// which validates it with Google, binds it to this account, acknowledges it and grants Omi Pro.
import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

/// Server answer for one Google Play purchase token.
class PlayVerifyResult {
  const PlayVerifyResult(this.status, {this.code, this.retryable = false});

  /// active | pending | inactive | error
  final String status;

  /// Server refusal code, e.g. purchase_owned_elsewhere, stripe_subscription_active, legacy_product.
  final String? code;

  /// True when the token must be kept and sent again (network loss, server or Google outage).
  final bool retryable;
}

/// POST /v1/payments/play/purchases: the server verifies the token with Google, binds and acknowledges it.
Future<PlayVerifyResult> verifyPlayPurchase({required String purchaseToken, required String productId}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/payments/play/purchases',
    headers: {},
    method: 'POST',
    body: jsonEncode({'purchase_token': purchaseToken, 'product_id': productId}),
  );
  if (response == null) return const PlayVerifyResult('error', retryable: true);
  Map<String, dynamic>? body;
  try {
    final decoded = jsonDecode(response.body);
    if (decoded is Map<String, dynamic>) body = decoded;
  } catch (_) {}
  if (response.statusCode == 200) {
    final status = body?['status'];
    return PlayVerifyResult(status is String ? status : 'error', retryable: status is! String);
  }
  final code = body?['code'];
  final retryable = response.statusCode >= 500 || response.statusCode == 429 || response.statusCode == 401;
  return PlayVerifyResult('error', code: code is String ? code : null, retryable: retryable);
}
