import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals.dart';

enum SyncStatus {
  idle,
  syncing,
  fetchingConversations,
  completed,
  error,
}

extension SyncMethodExtension on SyncMethod {
  String get displayName {
    switch (this) {
      case SyncMethod.ble:
        return 'Bluetooth';
      case SyncMethod.wifi:
        return 'Fast Transfer';
    }
  }

  String get shortName {
    switch (this) {
      case SyncMethod.ble:
        return 'BLE';
      case SyncMethod.wifi:
        return 'WiFi';
    }
  }

  String get description {
    switch (this) {
      case SyncMethod.ble:
        return 'Syncing via Bluetooth';
      case SyncMethod.wifi:
        return 'Syncing via WiFi';
    }
  }
}

class SyncState {
  final SyncStatus status;
  final double progress;
  final String? errorMessage;
  final Wal? failedWal;
  final List<SyncedConversationPointer> syncedConversations;
  final double? speedKBps; // Download speed in KB/s
  final SyncMethod? syncMethod; // Current sync method (BLE or WiFi)

  const SyncState({
    this.status = SyncStatus.idle,
    this.progress = 0.0,
    this.errorMessage,
    this.failedWal,
    this.syncedConversations = const [],
    this.speedKBps,
    this.syncMethod,
  });

  SyncState copyWith({
    SyncStatus? status,
    double? progress,
    String? errorMessage,
    Wal? failedWal,
    List<SyncedConversationPointer>? syncedConversations,
    double? speedKBps,
    SyncMethod? syncMethod,
    bool clearSyncMethod = false,
  }) {
    return SyncState(
      status: status ?? this.status,
      progress: progress ?? this.progress,
      errorMessage: errorMessage,
      failedWal: failedWal,
      syncedConversations: syncedConversations ?? this.syncedConversations,
      speedKBps: speedKBps,
      syncMethod: clearSyncMethod ? null : (syncMethod ?? this.syncMethod),
    );
  }

  bool get isIdle => status == SyncStatus.idle;
  bool get isSyncing => status == SyncStatus.syncing;
  bool get isFetchingConversations => status == SyncStatus.fetchingConversations;
  bool get isCompleted => status == SyncStatus.completed;
  bool get hasError => status == SyncStatus.error;
  bool get isProcessing => isSyncing || isFetchingConversations;

  SyncState toIdle() => copyWith(
        status: SyncStatus.idle,
        progress: 0.0,
        errorMessage: null,
        failedWal: null,
        syncedConversations: [],
        clearSyncMethod: true,
      );

  SyncState toSyncing({double progress = 0.0, double? speedKBps, SyncMethod? syncMethod}) => copyWith(
        status: SyncStatus.syncing,
        progress: progress,
        errorMessage: null,
        speedKBps: speedKBps,
        syncMethod: syncMethod,
      );

  SyncState toFetchingConversations() => copyWith(
        status: SyncStatus.fetchingConversations,
      );

  SyncState toCompleted({required List<SyncedConversationPointer> conversations}) => copyWith(
        status: SyncStatus.completed,
        syncedConversations: conversations,
      );

  SyncState toError({required String message, Wal? failedWal}) => copyWith(
        status: SyncStatus.error,
        errorMessage: message,
        failedWal: failedWal,
        progress: 0.0,
      );
}
