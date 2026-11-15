import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/users_wire.g.dart' as wire;
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
    // Preserve the adapter's conservative legacy defaults before the shared
    // wire decoder. In particular, a numeric string must not grant grace.
    final value = wire.GeneratedAccountDeletionStatusResponse.fromJson({
      'pending_deletion': json['pending_deletion'] == true,
      'wipe_at': json['wipe_at'] is String ? DateTime.tryParse(json['wipe_at'] as String)?.toIso8601String() : null,
      'grace_period_days': _count(json['grace_period_days'] ?? json['grace_days']),
      'loss_summary': {
        'held_recordings': loss is Map ? _count(loss['held_recordings']) : 0,
        'backlog_conversations': loss is Map ? _count(loss['backlog_conversations']) : 0,
      },
    });
    return AccountDeletionStatus.fromGenerated(value);
  }

  factory AccountDeletionStatus.fromGenerated(wire.GeneratedAccountDeletionStatusResponse value) {
    return AccountDeletionStatus(
      pendingDeletion: value.pendingDeletion,
      wipeAt: value.wipeAt,
      gracePeriodDays: _count(value.gracePeriodDays),
      heldCount: _count(value.lossSummary.heldRecordings),
      processingCount: _count(value.lossSummary.backlogConversations),
    );
  }

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
        decode: (body) {
          final data = _object(body);
          return wire.GeneratedAccountDeletionRestoreResponse.fromJson({
            'status': data['status'] is String ? data['status'] : '',
            'restored': data['restored'] == true,
          }).restored;
        },
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
          final value = wire.GeneratedAccountDeletionActionResponse.fromJson({
            'status': data['status'] is String ? data['status'] : '',
            'message': data['message'] is String ? data['message'] : '',
            'pending_deletion': data['pending_deletion'] == true,
          });
          return value.status == 'ok' && !value.pendingDeletion;
        },
      );
}
