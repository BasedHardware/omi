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

  Future<void> selectSession(String sessionId, String appId, {AppProvider? appProvider}) async {
    // ONLY set selection when user explicitly selects a thread
    _currentAppId = appId;
    _selectedSessionId = sessionId;

    // Switch to the thread's app if different from current app
    if (appProvider != null && appProvider.selectedChatAppId != appId) {
      appProvider.setSelectedChatAppId(appId);
    }

    notifyListeners();
  }

  Future<void> switchToApp(String appId) async {
    // ALWAYS show welcome screen when switching apps - no exceptions
    _currentAppId = appId;
    _selectedSessionId = null;
    notifyListeners();
  }

  Future<void> loadSessions({bool refresh = false}) async {
    // Load ALL sessions across all apps
    if (!refresh && _sessions.isNotEmpty) return;
    _isLoading = true;
    notifyListeners();
    try {
      final uid = SharedPreferencesUtil().uid;

      // Get all app IDs to fetch sessions from all apps
      final allAppIds = _appProvider?.apps.map((app) => app.id).toList() ?? [];
      if (allAppIds.isEmpty) {
        _sessions = [];
        return;
      }

      final list = await api.listChatSessions(uid: uid, appIds: allAppIds);
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
    final session = await api.createChatSession(uid: uid, appId: appId, title: title);
    if (session != null) {
      if (_currentAppId == appId) {
        _sessions = [session, ..._sessions];
      }
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
}
