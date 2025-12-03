import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/chat_session.dart';

/// Provider for managing chat sessions (multi-session chat support)
class ChatSessionProvider extends ChangeNotifier {
  List<ChatSession> sessions = [];
  String? currentSessionId;
  String? currentAppId;
  bool isLoadingSessions = false;
  bool _hasLoadedOnce = false;

  /// Load ALL sessions (across all apps) for the sidebar
  /// Set forceReload=true to bypass cache (e.g., when switching apps)
  Future<void> loadSessions(String? appId, {bool forceReload = false}) async {
    // Normalize appId
    if (appId == 'no_selected') appId = null;

    final appChanged = currentAppId != appId;
    currentAppId = appId;

    // If already loaded sessions and not forcing reload
    if (_hasLoadedOnce && sessions.isNotEmpty && !forceReload && !appChanged) {
      // Just pick a session for this app
      _selectSessionForCurrentApp(appId);
      return;
    }

    isLoadingSessions = true;
    notifyListeners();

    try {
      // Always load ALL sessions across all apps
      sessions = await getChatSessions(allApps: true);
      _hasLoadedOnce = true;

      // Set current session to most recent for current app
      _selectSessionForCurrentApp(appId);
    } catch (e) {
      debugPrint('Error loading sessions: $e');
      sessions = [];
    } finally {
      isLoadingSessions = false;
      notifyListeners();
    }
  }

  /// Select a session for the current app, or create one if none exists
  void _selectSessionForCurrentApp(String? appId) {
    // Find sessions for this app
    final appSessions = sessions.where((s) {
      final sessionAppId = s.pluginId ?? s.appId;
      return sessionAppId == appId;
    }).toList();

    if (appSessions.isNotEmpty) {
      // Use most recent session for this app
      currentSessionId = appSessions.first.id;
    } else {
      // No session for this app - set to null so backend creates one
      currentSessionId = null;
    }
    notifyListeners();
  }

  /// Called after backend creates a session (e.g., first message to new app)
  /// Refreshes session list to pick up the new session
  Future<void> syncAfterMessageSent() async {
    // Reload from server to get any auto-created sessions
    await loadSessions(currentAppId, forceReload: true);
  }

  /// Create a new session
  Future<ChatSession?> createNewSession(String? appId, {String? title}) async {
    try {
      final newSession = await createChatSession(appId: appId, title: title);
      if (newSession != null) {
        sessions.insert(0, newSession);
        currentSessionId = newSession.id;
        notifyListeners();
        return newSession;
      }
    } catch (e) {
      debugPrint('Error creating session: $e');
    }
    return null;
  }

  /// Switch to a specific session
  void setCurrentSessionId(String sessionId) {
    currentSessionId = sessionId;
    notifyListeners();
  }

  /// Delete a session
  Future<bool> deleteSession(String sessionId) async {
    try {
      final success = await deleteChatSession(sessionId);
      if (success) {
        sessions.removeWhere((s) => s.id == sessionId);

        // If deleted current session, switch to most recent
        if (currentSessionId == sessionId) {
          currentSessionId = sessions.isNotEmpty ? sessions.first.id : null;
        }

        notifyListeners();
        return true;
      }
    } catch (e) {
      debugPrint('Error deleting session: $e');
    }
    return false;
  }

  /// Update session title
  Future<bool> updateSessionTitle(String sessionId, String title) async {
    try {
      final success = await updateChatSessionTitle(sessionId, title);
      if (success) {
        final index = sessions.indexWhere((s) => s.id == sessionId);
        if (index != -1) {
          sessions[index] = sessions[index].copyWith(title: title);
          notifyListeners();
        }
        return true;
      }
    } catch (e) {
      debugPrint('Error updating session title: $e');
    }
    return false;
  }

  /// Refresh sessions (force reload from server)
  Future<void> refreshSessions() async {
    await loadSessions(currentAppId, forceReload: true);
  }

  /// Called when user switches apps - force reload to get latest sessions
  Future<void> onAppChanged(String? newAppId) async {
    await loadSessions(newAppId, forceReload: true);
  }

  /// Get current session
  ChatSession? get currentSession {
    if (currentSessionId == null) return null;
    try {
      return sessions.firstWhere((s) => s.id == currentSessionId);
    } catch (e) {
      return null;
    }
  }

  /// Check if there are any sessions
  bool get hasSessions => sessions.isNotEmpty;

  /// Get session by ID
  ChatSession? getSessionById(String sessionId) {
    try {
      return sessions.firstWhere((s) => s.id == sessionId);
    } catch (e) {
      return null;
    }
  }
}
