import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// MessageProvider's history and selected server session. Switching never moves an in-flight turn.
mixin ChatHistoryState on ChangeNotifier {
  ChatSessionsApi get chatSessionsApi;
  AppProvider? get appProvider;
  bool get chatMutationInProgress;
  void resetChatDraft();

  List<ServerMessage> messages = [];
  bool isLoadingMessages = false;
  bool hasCachedMessages = false;
  bool isClearingChat = false;
  String firstTimeLoadingText = '';
  String? chatSessionId;
  bool isFreshChat = false;
  bool hasOlderMessages = false;
  bool loadingOlderMessages = false;
  ApiProblem? historyProblem;
  int _historyEpoch = 0;
  int _messageOffset = 0;
  bool _historyDisposed = false;
  final Set<String> _namedSessions = {};
  Future<void>? _creatingSession;

  bool get canSwitchChat => !chatMutationInProgress && !isClearingChat && _creatingSession == null;

  /// Clears only the local projection. A server session is allocated on the first send.
  bool startFreshChat() {
    if (!canSwitchChat) return false;
    _historyEpoch++;
    appProvider?.setSelectedChatAppId(null);
    chatSessionId = null;
    isFreshChat = true;
    messages = [];
    _messageOffset = 0;
    hasCachedMessages = false;
    isLoadingMessages = false;
    loadingOlderMessages = false;
    hasOlderMessages = false;
    historyProblem = null;
    resetChatDraft();
    notifyListeners();
    return true;
  }

  /// Commits a new selection after a successful read; epoch checks discard superseded results.
  Future<bool> openChatSession(ChatSessionSummary session) async {
    if (!canSwitchChat) return false;
    final epoch = ++_historyEpoch;
    isLoadingMessages = true;
    loadingOlderMessages = false;
    historyProblem = null;
    notifyListeners();
    final result = await chatSessionsApi.messages(session.id);
    if (_historyDisposed || epoch != _historyEpoch) return false;
    isLoadingMessages = false;
    if (result is ApiFailure<List<ServerMessage>>) {
      historyProblem = result.problem;
      notifyListeners();
      return false;
    }
    // Replace the visible thread only after a successful read; a failed read retains the draft.
    appProvider?.setSelectedChatAppId(null);
    chatSessionId = session.id;
    isFreshChat = false;
    final loaded = result as ApiSuccess<List<ServerMessage>>;
    messages = loaded.data..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    _messageOffset = messages.length + loaded.rejectedRows;
    hasOlderMessages = _messageOffset == 100;
    historyProblem = loaded.rejectedRows > 0 ? const ApiProblem(ApiProblemKind.decode) : null;
    hasCachedMessages = false;
    if (session.hasTitle) _namedSessions.add(session.id);
    resetChatDraft();
    notifyListeners();
    return true;
  }

  /// Caller owns confirmation. Never replace the active projection on a failed delete.
  Future<bool> deleteChatSession(String id) async {
    if (!canSwitchChat) return false;
    setClearingChat(true);
    try {
      final result = await chatSessionsApi.delete(id);
      if (_historyDisposed || result is! ApiSuccess<void>) return false;
      if (chatSessionId == id) {
        isClearingChat = false;
        startFreshChat();
      }
      return true;
    } finally {
      if (!_historyDisposed) setClearingChat(false);
    }
  }

  /// Prepends older rows without duplicate IDs; the page preserves the reader's scroll anchor.
  Future<void> loadOlderMessages() async {
    final id = chatSessionId;
    if (id == null || loadingOlderMessages || !hasOlderMessages || !canSwitchChat) return;
    final epoch = _historyEpoch;
    loadingOlderMessages = true;
    historyProblem = null;
    notifyListeners();
    final result = await chatSessionsApi.messages(id, offset: _messageOffset);
    if (_historyDisposed || epoch != _historyEpoch) return;
    loadingOlderMessages = false;
    if (result is ApiSuccess<List<ServerMessage>>) {
      final ids = messages.map((m) => m.id).toSet();
      messages = [...messages, ...result.data.where((m) => ids.add(m.id))]
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
      final received = result.data.length + result.rejectedRows;
      _messageOffset += received;
      hasOlderMessages = received == 100;
      historyProblem = result.rejectedRows > 0 ? const ApiProblem(ApiProblemKind.decode) : null;
    } else {
      historyProblem = (result as ApiFailure<List<ServerMessage>>).problem;
    }
    notifyListeners();
  }

  /// Single-flight creation is a send prerequisite. Failure must not target the previous chat.
  Future<void> prepareChatSession() async {
    if (!isFreshChat || (appProvider?.selectedChatAppId ?? '').isNotEmpty) return;
    if (_creatingSession != null) return _creatingSession;
    final epoch = _historyEpoch;
    final future = () async {
      final result = await chatSessionsApi.create();
      if (_historyDisposed || epoch != _historyEpoch) throw StateError('Chat changed during creation');
      if (result is! ApiSuccess<ChatSessionSummary>) throw StateError('Could not create chat');
      chatSessionId = result.data.id;
      isFreshChat = false;
      notifyListeners();
    }();
    _creatingSession = future;
    try {
      await future;
    } finally {
      _creatingSession = null;
    }
  }

  /// Title generation is non-blocking and retryable on a later completed exchange.
  void nameChatSession() {
    final id = chatSessionId;
    if (id == null || !_namedSessions.add(id)) return;
    unawaited(chatSessionsApi.title(id, List.of(messages)).then((result) {
      if (result is ApiFailure<String>) _namedSessions.remove(id);
    }).catchError((Object _) {
      _namedSessions.remove(id);
    }));
  }

  void setHasCachedMessages(bool value) {
    hasCachedMessages = value;
    notifyListeners();
  }

  void setLoadingMessages(bool value) {
    isLoadingMessages = value;
    notifyListeners();
  }

  void setClearingChat(bool value) {
    isClearingChat = value;
    notifyListeners();
  }

  /// Explicit sessions never consume the legacy cache, which has no session/app ownership key.
  Future<void> refreshMessages({bool dropdownSelected = false}) async {
    if (chatMutationInProgress) return;
    if (dropdownSelected || (appProvider?.selectedChatAppId ?? '').isNotEmpty) {
      _historyEpoch++;
      chatSessionId = null;
      isFreshChat = false;
    }
    if (isFreshChat) return;
    final epoch = ++_historyEpoch;
    final appId = appProvider?.selectedChatAppId;
    isLoadingMessages = true;
    loadingOlderMessages = false;
    hasOlderMessages = false;
    notifyListeners();
    if (chatSessionId case final id?) {
      final result = await chatSessionsApi.messages(id);
      if (_historyDisposed || epoch != _historyEpoch) return;
      isLoadingMessages = false;
      if (result is ApiFailure<List<ServerMessage>>) {
        historyProblem = result.problem;
      } else {
        final loaded = result as ApiSuccess<List<ServerMessage>>;
        messages = loaded.data;
        _messageOffset = messages.length + loaded.rejectedRows;
        hasOlderMessages = _messageOffset == 100;
        historyProblem = loaded.rejectedRows > 0 ? const ApiProblem(ApiProblemKind.decode) : null;
      }
    } else {
      final loaded = await getMessagesServer(appId: appId, dropdownSelected: dropdownSelected);
      if (_historyDisposed || epoch != _historyEpoch || appId != appProvider?.selectedChatAppId) return;
      isLoadingMessages = false;
      messages = loaded;
      historyProblem = null;
      // The legacy cache has no session/app key. Never use it in an explicitly selected thread.
      if ((appId ?? '').isEmpty && !dropdownSelected) {
        if (messages.isEmpty) {
          messages = List.of(SharedPreferencesUtil().cachedMessages);
        } else {
          SharedPreferencesUtil().cachedMessages = messages;
        }
        hasCachedMessages = messages.isNotEmpty;
      }
    }
    messages.sort((a, b) => a.createdAt.compareTo(b.createdAt));
    notifyListeners();
  }

  Future<List<ServerMessage>> getMessagesFromServer({bool dropdownSelected = false}) async {
    await refreshMessages(dropdownSelected: dropdownSelected);
    return messages;
  }

  void setMessagesFromCache() {
    if (chatSessionId != null || isFreshChat || (appProvider?.selectedChatAppId ?? '').isNotEmpty) return;
    messages = List.of(SharedPreferencesUtil().cachedMessages)..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    hasCachedMessages = messages.isNotEmpty;
    notifyListeners();
  }

  Future<void> clearChat() async {
    if (!canSwitchChat) return;
    if (isFreshChat) {
      startFreshChat();
      return;
    }
    setClearingChat(true);
    try {
      final loaded = await clearChatServer(appId: appProvider?.selectedChatAppId, chatSessionId: chatSessionId);
      resetChatDraft();
      messages = loaded..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    } catch (e) {
      Logger.debug('Failed to clear chat: $e');
      final l10n = globalNavigatorKey.currentContext?.l10n;
      AppSnackbar.showSnackbarError(l10n?.somethingWentWrong ?? 'Something went wrong! Please try again later.');
    } finally {
      setClearingChat(false);
    }
  }

  @override
  void dispose() {
    _historyDisposed = true;
    _historyEpoch++;
    super.dispose();
  }
}
