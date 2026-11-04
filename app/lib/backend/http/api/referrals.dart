import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:omi/services/auth/auth_token_result.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/backend/schema/gen/referrals_wire.g.dart' as wire;

// Referral API client: fetches the signed referral link and the campaign snapshot, and validates both.
// The backend snapshot decides whether the campaign shows; anything invalid fails closed to the affiliate page.
const mobileReferralCampaignEnabled = bool.fromEnvironment('OMI_MOBILE_REFERRAL_CAMPAIGN', defaultValue: true);

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
  final value = wire.GeneratedReferralLinkResponse.fromJson(
    jsonDecode(materialized.body) as Map<String, dynamic>,
  ).referralUrl;
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

Map<String, dynamic> _strictCampaignNumbers(Map<String, dynamic> json) {
  const integerFields = {
    'qualified_purchases',
    'milestone_progress',
    'earned_months',
    'claimed_months',
    'claimable_months'
  };
  if (json.entries.any((entry) => integerFields.contains(entry.key) && entry.value is! int)) {
    throw const FormatException('Invalid campaign numbers');
  }
  return json;
}

class ReferralCampaign {
  const ReferralCampaign(
      {required this.enabled,
      required this.referralUrl,
      required this.qualifiedPurchases,
      required this.milestoneProgress,
      required this.earnedMonths,
      required this.claimedMonths,
      required this.claimableMonths,
      required this.rewardStatus});
  final bool enabled;
  final String? referralUrl;
  final int qualifiedPurchases, milestoneProgress, earnedMonths, claimedMonths, claimableMonths;
  final String rewardStatus;

  factory ReferralCampaign.fromJson(Map<String, dynamic> json) {
    _strictCampaignNumbers(json);
    return ReferralCampaign.fromGenerated(
      wire.GeneratedCampaignSnapshotResponse.fromJson(json),
      hasMilestoneProgress: json.containsKey('milestone_progress'),
      hasEarnedMonths: json.containsKey('earned_months'),
    );
  }

  factory ReferralCampaign.fromGenerated(wire.GeneratedCampaignSnapshotResponse value,
      {bool hasMilestoneProgress = true, bool hasEarnedMonths = true}) {
    final enabled = value.enabled;
    final purchases = value.qualifiedPurchases;
    final claimed = value.claimedMonths;
    final claimable = value.claimableMonths;
    final status = value.rewardStatus;
    if (value.campaignId != 'omi_pocket_match_v1' ||
        purchases < 0 ||
        purchases > 5 ||
        !{0, 2, 5}.contains(claimed) ||
        !{0, 2, 3, 5}.contains(claimable) ||
        !{'disabled', 'ready', 'pending_paid_subscription', 'active'}.contains(status)) {
      throw const FormatException('Invalid campaign');
    }
    final progress = hasMilestoneProgress ? value.milestoneProgress : purchases;
    if (progress is! int || progress < purchases || progress > 5) {
      throw const FormatException('Invalid campaign milestone');
    }
    final unlocked = progress >= 5
        ? 5
        : progress >= 2
            ? 2
            : 0;
    final expectedEarned = claimed > unlocked ? claimed : unlocked;
    final earned = hasEarnedMonths ? value.earnedMonths : expectedEarned;
    if (earned is! int || !{0, 2, 5}.contains(earned) || earned != expectedEarned) {
      throw const FormatException('Invalid campaign earnings');
    }
    final expectedClaimable = enabled ? earned - claimed : 0;
    final hasMilestoneFields = hasMilestoneProgress || hasEarnedMonths;
    if (claimable > expectedClaimable ||
        (hasMilestoneFields && claimable != expectedClaimable) ||
        (!enabled && value.referralUrl != null)) {
      throw const FormatException('Invalid campaign progress');
    }
    return ReferralCampaign(
        enabled: enabled,
        referralUrl: enabled ? validateCampaignReferralLink(value.referralUrl) : null,
        qualifiedPurchases: purchases,
        milestoneProgress: progress,
        earnedMonths: earned,
        claimedMonths: claimed,
        claimableMonths: claimable,
        rewardStatus: status);
  }
}

String validateCampaignReferralLink(Object? value) {
  final uri = value is String ? Uri.tryParse(value) : null;
  if (uri == null ||
      uri.scheme != 'https' ||
      !const {'omi.me', 'api.omiapi.com'}.contains(uri.host) ||
      uri.hasPort ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      !RegExp(r'^/r/ref2\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}$').hasMatch(uri.path) ||
      uri.toString() != value) {
    throw const FormatException('Invalid campaign URL');
  }
  return value as String;
}

Future<ReferralCampaign> getReferralCampaign({required AuthSessionSnapshot session, bool claim = false}) async {
  if (!mobileReferralCampaignEnabled) throw StateError('Referral campaign is disabled');
  final response = await makeRawApiCall(
    url: '${Env.apiBaseUrl}v2/users/me/referral/campaign${claim ? '/claim' : ''}',
    method: claim ? 'POST' : 'GET',
    sessionSnapshot: session,
    timeout: const Duration(seconds: 20),
  );
  final body = await http.Response.fromStream(response);
  if (body.statusCode != 200) throw StateError('Referral campaign unavailable');
  final json = _strictCampaignNumbers(jsonDecode(body.body) as Map<String, dynamic>);
  final value = wire.GeneratedCampaignSnapshotResponse.fromJson(json);
  return ReferralCampaign.fromGenerated(value,
      hasMilestoneProgress: json.containsKey('milestone_progress'), hasEarnedMonths: json.containsKey('earned_months'));
}
