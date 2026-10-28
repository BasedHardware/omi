import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/account_deletion.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/services/account_deletion_data.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';

void main() {
  test('missing, invalid and expired policy cannot promise grace', () {
    final now = DateTime.utc(2026, 10, 28);
    for (final json in <Map<String, dynamic>>[
      {},
      {'grace_days': -1},
      {'wipe_at': 'invalid'},
      {'wipe_at': now.toIso8601String()},
      {'pending_deletion': true, 'grace_days': 14}
    ]) {
      expect(AccountDeletionStatus.fromJson(json).graceDaysAt(now), 0);
    }
    expect(AccountDeletionStatus.fromJson({'grace_period_days': 7}).graceDaysAt(now), 7);
    expect(
        AccountDeletionStatus.fromJson({'wipe_at': now.add(const Duration(days: 5, hours: 3)).toIso8601String()})
            .graceDaysAt(now),
        5);
  });

  test('counts exclude uploaded/synced, retired/unowned and non-phone recordings', () {
    Wal wal(WalStatus status, {String? uid = 'current', WalStorage storage = WalStorage.disk}) => Wal(
        timerStart: 1,
        codec: BleAudioCodec.opus,
        seconds: 10,
        channel: 1,
        sampleRate: 16000,
        status: status,
        ownerUid: uid,
        storage: storage);
    final wals = [
      wal(WalStatus.miss),
      wal(WalStatus.inProgress),
      wal(WalStatus.uploadRejected),
      wal(WalStatus.uploaded),
      wal(WalStatus.synced),
      wal(WalStatus.miss, uid: 'other'),
      wal(WalStatus.miss, uid: null),
      wal(WalStatus.miss, storage: WalStorage.sdcard)
    ];
    expect(countOnPhoneRecordings(wals, 'current'), 3);
    expect(countOnPhoneRecordings(wals, ''), 0);
  });

  test('only absent endpoints allow legacy sign-in; unavailable status stays retryable', () async {
    for (final status in [404, 405, 503]) {
      var fallbacks = 0;
      final result = await readAccountDeletionForSignIn(
        api: AccountDeletionApi(baseUrl: 'http://fixture/', send: (_) async => http.Response('{}', status)),
        fallback: (_) => fallbacks++,
      );
      if (status == 503) {
        expect(result, isA<ApiFailure<AccountDeletionStatus>>());
        expect(fallbacks, 0);
      } else {
        expect((result as ApiSuccess<AccountDeletionStatus>).data.pendingDeletion, isFalse);
        expect(fallbacks, 1);
      }
    }
  });

  test('status uses loss_summary; restore and erase-now retain typed failures', () async {
    final requests = <ApiRequest>[];
    final api = AccountDeletionApi(
        baseUrl: 'http://fixture/',
        send: (request) async {
          requests.add(request);
          if (request.method == 'GET') {
            return http.Response(
                '{"pending_deletion":true,"wipe_at":"2026-11-11T00:00:00Z","loss_summary":{"held_recordings":3,"backlog_conversations":14}}',
                200);
          }
          if (request.method == 'POST') return http.Response('{"restored":true}', 200);
          return http.Response('{"status":"ok"}', 200);
        });
    final status = await api.status() as ApiSuccess<AccountDeletionStatus>;
    expect(status.data.heldCount, 3);
    expect(status.data.processingCount, 14);
    expect(status.data.pendingDeletion, isTrue);
    expect(await api.restore(), isA<ApiSuccess<bool>>());
    expect(await api.finishDeleting(), isA<ApiSuccess<bool>>());
    expect(requests.map((r) => r.url), [
      'http://fixture/v1/users/deletion-status',
      'http://fixture/v1/users/restore-account',
      'http://fixture/v1/users/delete-account'
    ]);
    expect(requests.last.body, '{"erase_now":true}');
    final older = AccountDeletionApi(baseUrl: 'http://fixture/', send: (_) async => http.Response('{}', 404));
    expect(await older.status(), isA<ApiFailure<AccountDeletionStatus>>());
    expect(await older.restore(), isA<ApiFailure<bool>>());
  });
}
