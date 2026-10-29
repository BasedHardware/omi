import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/account_deletion_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

Map<String, dynamic> _object(String body) {
  final value = jsonDecode(body);
  if (value is! Map<String, dynamic>) throw const FormatException('Expected deletion object');
  return value;
}

int _count(Object? value) => value is num && value.isFinite && value >= 0 ? value.toInt() : 0;

/// Additive owner-facing contract. Missing policy fields never imply a grace window.
class AccountDeletionStatus {
  const AccountDeletionStatus({
    this.pendingDeletion = false,
    this.wipeAt,
    this.gracePeriodDays = 0,
    this.heldCount = 0,
    this.processingCount = 0,
  });

  final bool pendingDeletion;
  final DateTime? wipeAt;
  final int gracePeriodDays;
  final int heldCount;
  final int processingCount;

  factory AccountDeletionStatus.fromJson(Map<String, dynamic> json) {
    final loss = json['loss_summary'];
    final wipeAt = json['wipe_at'];
    // Preserve the additive endpoint's conservative legacy defaults before
    // decoding the canonical wire shape; malformed deadlines never grant grace.
    return AccountDeletionStatus.fromGenerated(wire.GeneratedAccountDeletionStatusResponse.fromJson({
      'pending_deletion': json['pending_deletion'] == true,
      'wipe_at': wipeAt is String ? DateTime.tryParse(wipeAt)?.toIso8601String() : null,
      'grace_period_days': _count(json['grace_period_days'] ?? json['grace_days']),
      'loss_summary': {
        'held_recordings': loss is Map ? _count(loss['held_recordings']) : 0,
        'backlog_conversations': loss is Map ? _count(loss['backlog_conversations']) : 0,
      },
    }));
  }

  factory AccountDeletionStatus.fromGenerated(wire.GeneratedAccountDeletionStatusResponse generated) =>
      AccountDeletionStatus(
        pendingDeletion: generated.pendingDeletion,
        wipeAt: generated.wipeAt,
        gracePeriodDays: generated.gracePeriodDays,
        heldCount: generated.lossSummary.heldRecordings,
        processingCount: generated.lossSummary.backlogConversations,
      );

  /// Round down: never promise more time than the authoritative deadline allows.
  int graceDaysAt(DateTime now) {
    if (wipeAt != null) {
      final remaining = wipeAt!.difference(now).inDays;
      return remaining > 0 ? remaining : 0;
    }
    return pendingDeletion ? 0 : gracePeriodDays;
  }

  /// Whole days left before the server's deletion deadline. A positive
  /// fraction of a day is 0; unknown or expired deadlines are unavailable.
  ({bool available, int days}) restoreDaysRemainingAt(DateTime now) {
    final deadline = wipeAt;
    if (deadline == null) return (available: false, days: 0);
    final remaining = deadline.difference(now);
    if (remaining <= Duration.zero) return (available: false, days: 0);
    return (available: true, days: remaining.inDays);
  }
}

class AccountDeletionApi {
  const AccountDeletionApi({this.send, this.baseUrl});
  final ApiSend? send;
  final String? baseUrl;

  String _url(String path) => '${(baseUrl ?? Env.apiBaseUrl ?? '').replaceFirst(RegExp(r'/$'), '')}/v1/users/$path';

  Future<ApiResult<AccountDeletionStatus>> status() => executeApi(
        request: ApiRequest(url: _url('deletion-status'), method: 'GET'),
        send: send,
        decode: (body) => AccountDeletionStatus.fromJson(_object(body)),
      );

  Future<ApiResult<bool>> restore() => executeApi(
        request: ApiRequest(url: _url('restore-account'), method: 'POST'),
        send: send,
        decode: (body) => _object(body)['restored'] == true,
      );

  Future<ApiResult<bool>> finishDeleting() => executeApi(
        request: ApiRequest(
          url: _url('delete-account'),
          method: 'DELETE',
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'erase_now': true}),
        ),
        send: send,
        decode: (body) {
          final data = _object(body);
          return data['status'] == 'ok' && data['pending_deletion'] != true;
        },
      );
}
