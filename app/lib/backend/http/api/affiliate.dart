import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/affiliate_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

enum AffiliateState { unavailable, notLinked, linked, blocked }

AffiliateState _state(String raw) => switch (raw) {
      'not_linked' => AffiliateState.notLinked,
      'linked' => AffiliateState.linked,
      'blocked' => AffiliateState.blocked,
      _ => AffiliateState.unavailable,
    };

class AffiliateStatus {
  const AffiliateStatus({
    required this.nativeEnabled,
    required this.state,
    this.emailMatchAvailable = false,
    this.profile,
  });

  final bool nativeEnabled;
  final AffiliateState state;
  final bool emailMatchAvailable;
  final wire.GeneratedAffiliateProfile? profile;

  factory AffiliateStatus.fromWire(wire.GeneratedAffiliateStatusResponse generated) => AffiliateStatus(
        nativeEnabled: generated.nativeEnabled,
        state: generated.nativeEnabled ? _state(generated.state) : AffiliateState.unavailable,
        emailMatchAvailable: generated.emailMatchAvailable,
        profile: generated.profile,
      );
}

Map<String, dynamic> _object(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) throw const FormatException('expected an object');
  return decoded;
}

class AffiliateApi {
  const AffiliateApi({this.send});

  final ApiSend? send;

  static String get _base => '${Env.apiBaseUrl}v1/affiliate';

  Future<ApiResult<T>> _call<T>(String path, String method, T Function(Map<String, dynamic>) decode, {Object? body}) =>
      executeApi(
        request: ApiRequest(url: '$_base$path', method: method, body: body == null ? '' : jsonEncode(body)),
        send: send,
        decode: (raw) => decode(_object(raw)),
      );

  Future<ApiResult<AffiliateStatus>> status() =>
      _call('/me', 'GET', (json) => AffiliateStatus.fromWire(wire.GeneratedAffiliateStatusResponse.fromJson(json)));

  Future<ApiResult<AffiliateStatus>> _link(String path, {Object? body}) => _call(
        path,
        'POST',
        (json) => AffiliateStatus.fromWire(wire.GeneratedAffiliateLinkResponse.fromJson(json).status),
        body: body,
      );

  Future<ApiResult<AffiliateStatus>> linkByEmail() => _link('/link/email');

  Future<ApiResult<AffiliateStatus>> linkWithCredentials(String email, String password) =>
      _link('/link/credentials', body: {'email': email, 'password': password});

  Future<ApiResult<AffiliateStatus>> join() => _link('/join');

  Future<ApiResult<wire.GeneratedAffiliateStatsResponse>> stats() =>
      _call('/stats', 'GET', wire.GeneratedAffiliateStatsResponse.fromJson);

  Future<ApiResult<wire.GeneratedAffiliateOrdersResponse>> orders({int limit = 20, int offset = 0}) =>
      _call('/orders?limit=$limit&offset=$offset', 'GET', wire.GeneratedAffiliateOrdersResponse.fromJson);

  Future<ApiResult<wire.GeneratedAffiliateEarningsResponse>> earnings() =>
      _call('/earnings', 'GET', wire.GeneratedAffiliateEarningsResponse.fromJson);

  Future<ApiResult<wire.GeneratedAffiliatePayoutsResponse>> payouts({int limit = 20, int offset = 0}) =>
      _call('/payouts?limit=$limit&offset=$offset', 'GET', wire.GeneratedAffiliatePayoutsResponse.fromJson);

  Future<ApiResult<wire.GeneratedAffiliateRefCodeAvailabilityResponse>> checkRefCode(String code) => _call(
        '/ref-code?code=${Uri.encodeQueryComponent(code)}',
        'GET',
        wire.GeneratedAffiliateRefCodeAvailabilityResponse.fromJson,
      );

  Future<ApiResult<wire.GeneratedAffiliateRefCodeUpdateResponse>> updateRefCode(String code) =>
      _call('/ref-code', 'PATCH', wire.GeneratedAffiliateRefCodeUpdateResponse.fromJson, body: {'ref_code': code});

  Future<ApiResult<wire.GeneratedAffiliatePayoutAccountStatusResponse>> payoutAccount() =>
      _call('/payouts/account', 'GET', wire.GeneratedAffiliatePayoutAccountStatusResponse.fromJson);

  /// Stripe-hosted onboarding link; [country] is needed only before an account exists.
  Future<ApiResult<String>> payoutSetupLink({String? country}) => _call(
        '/payouts/setup',
        'POST',
        (json) => wire.GeneratedAffiliatePayoutLinkResponse.fromJson(json).url,
        body: {'country': country},
      );

  Future<ApiResult<String>> payoutDashboardLink() =>
      _call('/payouts/dashboard', 'POST', (json) => wire.GeneratedAffiliatePayoutLinkResponse.fromJson(json).url);
}
