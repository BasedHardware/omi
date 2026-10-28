import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
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
    return AccountDeletionStatus(
      pendingDeletion: json['pending_deletion'] == true,
      wipeAt: json['wipe_at'] is String ? DateTime.tryParse(json['wipe_at'] as String) : null,
      gracePeriodDays: _count(json['grace_period_days'] ?? json['grace_days']),
      heldCount: loss is Map ? _count(loss['held_recordings']) : 0,
      processingCount: loss is Map ? _count(loss['backlog_conversations']) : 0,
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
