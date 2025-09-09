import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/chat_sessions.dart' as api;
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/app_provider.dart';

class ChatSessionProvider extends ChangeNotifier {
  List<ChatSession> _sessions = [];
  String? _currentAppId;
  String? _selectedSessionId; // In-memory only, no persistence for ChatGPT-like behavior
  bool _isLoading = false;
  AppProvider? _appProvider;

  List<ChatSession> get sessions => _sessions;
  bool get isLoading => _isLoading;
  String? get currentAppId => _currentAppId;

  String? get selectedSessionId => _selectedSessionId;

  void updateAppProvider(AppProvider appProvider) {
    _appProvider = appProvider;
  }

  Future<void> selectSession(String sessionId, String? appId, {AppProvider? appProvider}) async {
    // ONLY set selection when user explicitly selects a thread
    _currentAppId = appId;
    _selectedSessionId = sessionId;

    // Switch to the thread's app if different from current app
    final currentSelectedAppId = appProvider?.selectedChatAppId ?? 'omi';
    final targetAppId = appId ?? 'omi';
    if (appProvider != null && currentSelectedAppId != targetAppId) {
      appProvider.setSelectedChatAppId(targetAppId);
    }

    notifyListeners();
  }

  Future<void> switchToApp(String appId) async {
    // ALWAYS show welcome screen when switching apps - no exceptions
    // AppProvider now provides clean state, no conversion needed
    final effectiveAppId = appId.isEmpty ? 'omi' : appId;
    _currentAppId = effectiveAppId;
    _selectedSessionId = null;
    notifyListeners();
  }

  Future<void> loadSessions({bool refresh = false}) async {
    // Load ALL user sessions efficiently in a single request
    if (!refresh && _sessions.isNotEmpty) return;
    _isLoading = true;
    notifyListeners();
    try {
      final uid = SharedPreferencesUtil().uid;

      // 🚀 PERFORMANCE FIX: Use efficient single API call instead of 4000+ requests
      final list = await api.listAllUserChatSessions(uid: uid);
      _sessions = list;
    } catch (e) {
      debugPrint('loadSessions error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<ChatSession?> createSession({required String appId, String? title}) async {
    final uid = SharedPreferencesUtil().uid;
    final session = await api.createChatSession(uid: uid, appId: appId, title: title ?? 'New Chat');
    if (session != null) {
      // Always add new sessions to the list (they're already filtered by current context)
      _sessions = [session, ..._sessions];
      _selectedSessionId = session.id; // Set as selected in-memory
      notifyListeners();
    }
    return session;
  }

  Future<bool> deleteSession({required String sessionId}) async {
    final uid = SharedPreferencesUtil().uid;
    final ok = await api.deleteChatSession(uid: uid, sessionId: sessionId);
    if (ok) {
      _sessions.removeWhere((s) => s.id == sessionId);
      if (_selectedSessionId == sessionId) {
        // Clear selection if we deleted the selected session
        _selectedSessionId = null;
      }
      notifyListeners();
    }
    return ok;
  }

  Future<void> generateTitleForSession({required String sessionId, required String firstMessage}) async {
    final uid = SharedPreferencesUtil().uid;
    try {
      final generatedTitle =
          await api.generateChatSessionTitle(uid: uid, sessionId: sessionId, firstMessage: firstMessage);

      if (generatedTitle != null) {
        // Update the session in our local list
        final sessionIndex = _sessions.indexWhere((s) => s.id == sessionId);
        if (sessionIndex != -1) {
          final updatedSession = ChatSession(
            id: _sessions[sessionIndex].id,
            appId: _sessions[sessionIndex].appId,
            title: generatedTitle,
            createdAt: _sessions[sessionIndex].createdAt,
          );
          _sessions[sessionIndex] = updatedSession;
          notifyListeners();
        }
      }
    } catch (e) {
      debugPrint('Error generating title for session $sessionId: $e');
    }
  }
}
