import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/providers/app_provider.dart';

class ChatSessionProvider extends ChangeNotifier {
  AppProvider? appProvider;
  List<ChatSession> sessions = [];
  ChatSession? currentSession;
  bool isLoadingSessions = false;

  void updateAppProvider(AppProvider p) {
    appProvider = p;
  }

  String? get currentSessionId => currentSession?.id;
  String? get currentAppId => appProvider?.selectedChatAppId;

  Future<void> loadSessions() async {
    isLoadingSessions = true;
    notifyListeners();

    try {
      final appId = appProvider?.selectedChatAppId;
      sessions = await getChatSessions(appId: appId);
      
      // If no current session and we have sessions, set the first one as current
      if (currentSession == null && sessions.isNotEmpty) {
        currentSession = sessions.first;
      }
      
      // If no sessions exist, create a new one
      if (sessions.isEmpty) {
        await createNewSession();
      }
    } catch (e) {
      debugPrint('Error loading sessions: $e');
    } finally {
      isLoadingSessions = false;
      notifyListeners();
    }
  }

  Future<void> createNewSession({String? title}) async {
    try {
      final appId = appProvider?.selectedChatAppId;
      final newSession = await createChatSession(appId: appId, title: title);
      
      if (newSession != null) {
        sessions.insert(0, newSession);
        currentSession = newSession;
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error creating new session: $e');
    }
  }

  Future<void> switchToSession(ChatSession session) async {
    if (currentSession?.id != session.id) {
      currentSession = session;
      notifyListeners();
    }
  }

  Future<void> deleteSession(ChatSession session) async {
    try {
      final success = await deleteChatSession(session.id);
      if (success) {
        sessions.removeWhere((s) => s.id == session.id);
        
        // If we deleted the current session, switch to another one
        if (currentSession?.id == session.id) {
          if (sessions.isNotEmpty) {
            currentSession = sessions.first;
          } else {
            await createNewSession();
          }
        }
        
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error deleting session: $e');
    }
  }

  Future<void> updateSessionTitle(ChatSession session, String title) async {
    try {
      final success = await updateChatSessionTitle(session.id, title);
      if (success) {
        final index = sessions.indexWhere((s) => s.id == session.id);
        if (index != -1) {
          sessions[index] = session.copyWith(title: title);
          if (currentSession?.id == session.id) {
            currentSession = sessions[index];
          }
          notifyListeners();
        }
      }
    } catch (e) {
      debugPrint('Error updating session title: $e');
    }
  }

  Future<void> refreshOnAppChange() async {
    // Clear current state
    sessions.clear();
    currentSession = null;
    
    // Load sessions for the new app
    await loadSessions();
  }

  void clear() {
    sessions.clear();
    currentSession = null;
    notifyListeners();
  }
} 