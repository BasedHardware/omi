import 'dart:async';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/logger.dart';

typedef MergeConversationFetcher = Future<ApiResult<ServerConversation>> Function(String id);

/// Observes server completion; absence is proved only by 404, never by a
/// network, decode, permission or subscription failure. The provider owns all
/// list/cache mutations and supplies the account/backend generation fence.
class ConversationMergeWatch {
  ConversationMergeWatch({
    required this.sourceIds,
    required this.targetId,
    required this.fetch,
    required this.isCurrent,
    required this.onCompleted,
    required this.onRefresh,
    required Duration interval,
    required Duration limit,
  }) {
    _timer = Timer.periodic(interval, (_) => unawaited(probe()));
    _deadline = Timer(limit, () {
      if (!isCurrent()) return cancel();
      cancel();
      unawaited(onRefresh(_sourcesGone).catchError((Object _) {
        Logger.debug('Merge observation refresh failed; pending journal remains retryable');
      }));
    });
  }

  final List<String> sourceIds;
  final String? targetId;
  final MergeConversationFetcher fetch;
  final bool Function() isCurrent;
  final Future<void> Function(ServerConversation) onCompleted;
  final Future<void> Function(bool sourcesGone) onRefresh;
  late final Timer _timer;
  late final Timer _deadline;
  bool _cancelled = false;
  bool _probing = false;
  bool _sourcesGone = false;

  void cancel() {
    _cancelled = true;
    _timer.cancel();
    _deadline.cancel();
  }

  Future<void> probe() async {
    if (_cancelled || _probing || !isCurrent()) return;
    _probing = true;
    _sourcesGone = false;
    try {
      for (final id in sourceIds) {
        final result = await fetch(id);
        if (_cancelled || !isCurrent()) return;
        // Manual merge allocates a NEW ID. A remaining original is never
        // inferred to be the merged result, even if it is completed.
        if (result is! ApiFailure<ServerConversation> || result.problem.kind != ApiProblemKind.notFound) return;
      }
      _sourcesGone = true;
      if (targetId == null) {
        // Compatibility with an older server that does not return a target.
        // All sources are authoritatively gone; reconcile the server list.
        cancel();
        await onRefresh(true);
        return;
      }
      final target = await fetch(targetId!);
      if (_cancelled || !isCurrent()) return;
      if (target case ApiSuccess<ServerConversation>(:final data)
          when data.id == targetId && data.status == ConversationStatus.completed && !data.isLocked) {
        await onCompleted(data);
        cancel();
      }
    } catch (_) {
      // Inconclusive reads retain both the pending journal and visible rows.
      // The next bounded probe or a later refresh can recover.
    } finally {
      _probing = false;
    }
  }
}
