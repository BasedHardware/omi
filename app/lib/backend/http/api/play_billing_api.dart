// Google Play Billing purchase verification: the app hands the Play purchase token to the server,
// which validates it with Google, binds it to this account, acknowledges it and grants Omi Pro.
import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
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
Future<PlayVerifyResult> verifyPlayPurchase({
  required String purchaseToken,
  required String productId,
  ApiSend? send,
}) async {
  final result = await executeApi<String>(
    request: ApiRequest(
      url: '${Env.apiBaseUrl}v1/payments/play/purchases',
      method: 'POST',
      body: jsonEncode({'purchase_token': purchaseToken, 'product_id': productId}),
    ),
    send: send,
    decode: (body) {
      final decoded = jsonDecode(body);
      final status = decoded is Map ? decoded['status'] : null;
      if (status is! String) throw const FormatException('status');
      return status;
    },
  );
  return switch (result) {
    ApiSuccess(:final data) => PlayVerifyResult(data),
    ApiFailure(:final problem) => PlayVerifyResult(
        'error',
        code: problem.detail,
        // A paid purchase is never dropped on an outage or an unreadable answer: keep it and resend.
        retryable:
            problem.retryable || problem.kind == ApiProblemKind.decode || problem.kind == ApiProblemKind.authTerminal,
      ),
  };
}
