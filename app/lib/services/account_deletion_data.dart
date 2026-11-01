import 'package:omi/backend/http/api/account_deletion.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

Future<ApiResult<AccountDeletionStatus>> readAccountDeletionForSignIn({
  AccountDeletionApi api = const AccountDeletionApi(),
  void Function(ApiFallbackEvent)? fallback,
  bool allowCachedOfflineAccount = false,
}) async {
  final result = await api.status();
  if (result case ApiFailure<AccountDeletionStatus>(:final problem)) {
    if (problem.kind == ApiProblemKind.transport && allowCachedOfflineAccount) {
      (fallback ?? recordFallback)(
          const ApiFallbackEvent(reason: ApiFallbackReason.offline, outcome: ApiFallbackOutcome.degraded));
      return const ApiSuccess(AccountDeletionStatus());
    }
    if (problem.statusCode == 404 || problem.statusCode == 405) {
      (fallback ?? recordFallback)(
          const ApiFallbackEvent(reason: ApiFallbackReason.error, outcome: ApiFallbackOutcome.degraded));
      return const ApiSuccess(AccountDeletionStatus());
    }
  }
  return result;
}

/// Preserve an existing owner's offline startup without admitting another account
/// or overriding a deletion decision the server already confirmed.
bool canUseCachedAccountOffline({
  required String uid,
  required String startupUid,
  required String pendingUid,
  required bool onboardingCompleted,
}) =>
    uid.isNotEmpty && uid == startupUid && uid != pendingUid && onboardingCompleted;

class DeletionPendingData {
  const DeletionPendingData(
      {required this.processingCount, required this.notUploadedCount, required this.gracePeriodDays});
  final int processingCount;
  final int notUploadedCount;
  final int gracePeriodDays;
  bool get hasGrace => gracePeriodDays > 0;
  int get pendingCount => processingCount + notUploadedCount;
}

/// The WAL store already scopes its active inventory to this session; additionally
/// require explicit ownership so retired and unowned legacy audio is never counted.
int countOnPhoneRecordings(Iterable<Wal> wals, String uid) => uid.isEmpty
    ? 0
    : wals
        .where((wal) =>
            wal.ownerUid == uid &&
            (wal.storage == WalStorage.disk || wal.storage == WalStorage.mem) &&
            wal.status != WalStatus.uploaded &&
            wal.status != WalStatus.synced &&
            wal.status != WalStatus.corrupted &&
            wal.status != WalStatus.unsupportedAudio)
        .length;

Future<DeletionPendingData> loadDeletionPendingData() async {
  final uid = SharedPreferencesUtil().uid;
  final phone = ServiceManager.instance().wal.getSyncs().phone as LocalWalSync;
  final wals = await phone.getAllWals();
  final result = await const AccountDeletionApi().status();
  if (SharedPreferencesUtil().uid != uid) throw StateError('Account changed');
  final localCount = countOnPhoneRecordings(wals, uid);
  if (result case ApiSuccess<AccountDeletionStatus>(:final data)) {
    return DeletionPendingData(
      processingCount: data.processingCount + data.heldCount,
      notUploadedCount: localCount,
      gracePeriodDays: data.graceDaysAt(DateTime.now()),
    );
  }
  // An older backend or unavailable policy cannot justify a restoration promise.
  recordFallback(const ApiFallbackEvent(reason: ApiFallbackReason.error, outcome: ApiFallbackOutcome.degraded));
  return DeletionPendingData(
    processingCount: wals.where((wal) => wal.ownerUid == uid && wal.status == WalStatus.uploaded).length,
    notUploadedCount: localCount,
    gracePeriodDays: 0,
  );
}
