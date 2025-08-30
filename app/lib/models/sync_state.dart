import 'package:omi/services/wals.dart';
import 'package:omi/backend/schema/conversation.dart';

enum SyncStatus {
  idle,
  syncing,
  fetchingConversations,
  completed,
  error,
}

class SyncState {
  final SyncStatus status;
  final double progress;
  final String? errorMessage;
  final Wal? failedWal;
  final List<SyncedConversationPointer> syncedConversations;

  const SyncState({
    this.status = SyncStatus.idle,
    this.progress = 0.0,
    this.errorMessage,
    this.failedWal,
    this.syncedConversations = const [],
  });

  SyncState copyWith({
    SyncStatus? status,
    double? progress,
    String? errorMessage,
    Wal? failedWal,
    List<SyncedConversationPointer>? syncedConversations,
  }) {
    return SyncState(
      status: status ?? this.status,
      progress: progress ?? this.progress,
      errorMessage: errorMessage,
      failedWal: failedWal,
      syncedConversations: syncedConversations ?? this.syncedConversations,
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
      );

  SyncState toSyncing({double progress = 0.0}) => copyWith(
        status: SyncStatus.syncing,
        progress: progress,
        errorMessage: null,
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
