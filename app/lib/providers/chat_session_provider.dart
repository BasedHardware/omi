import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/chat_sessions.dart' as api;
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/preferences.dart';

class ChatSessionProvider extends ChangeNotifier {
  List<ChatSession> _sessions = [];
  String? _currentAppId;
  bool _isLoading = false;

  List<ChatSession> get sessions => _sessions;
  bool get isLoading => _isLoading;
  String? get currentAppId => _currentAppId;

  String? get selectedSessionId => _currentAppId == null ? null : getSelectedSessionIdForApp(_currentAppId!);

  String? getSelectedSessionIdForApp(String appId) {
    return SharedPreferencesUtil().getString('selectedSessionId:$appId');
  }

  Future<void> setSelectedSessionIdForApp(String appId, String? sessionId) async {
    if (sessionId == null || sessionId.isEmpty) {
      await SharedPreferencesUtil().remove('selectedSessionId:$appId');
    } else {
      await SharedPreferencesUtil().saveString('selectedSessionId:$appId', sessionId);
    }
    notifyListeners();
  }

  Future<void> loadSessions({required String appId, bool refresh = false}) async {
    if (!refresh && _currentAppId == appId && _sessions.isNotEmpty) return;
    _currentAppId = appId;
    _isLoading = true;
    notifyListeners();
    try {
      final uid = SharedPreferencesUtil().uid;
      final list = await api.listChatSessions(uid: uid, appId: appId);
      _sessions = list;

      // Clear any selected session when switching apps to show blank chat
      await setSelectedSessionIdForApp(appId, null);
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
      await setSelectedSessionIdForApp(appId, session.id);
    }
    return session;
  }

  Future<bool> deleteSession({required String sessionId}) async {
    final uid = SharedPreferencesUtil().uid;
    final ok = await api.deleteChatSession(uid: uid, sessionId: sessionId);
    if (ok) {
      _sessions.removeWhere((s) => s.id == sessionId);
      if (_currentAppId != null && getSelectedSessionIdForApp(_currentAppId!) == sessionId) {
        // Clear selection if we deleted the selected session
        await setSelectedSessionIdForApp(_currentAppId!, null);
      }
      notifyListeners();
    }
    return ok;
  }
}
