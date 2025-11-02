import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:url_launcher/url_launcher.dart';

class TodoistService {
  static const String _authUrl = 'https://todoist.com/oauth/authorize';
  static const String _apiBaseUrl = 'https://api.todoist.com/rest/v2';

  // Todoist OAuth redirect URL (backend handles token exchange)
  static final String _redirectUri = '${Env.apiBaseUrl}v2/integrations/todoist/callback';

  static final TodoistService _instance = TodoistService._internal();
  factory TodoistService() => _instance;
  TodoistService._internal();

  /// Check if user is authenticated with Todoist
  bool get isAuthenticated => SharedPreferencesUtil().todoistAccessToken != null;

  /// Get stored access token
  String? get accessToken => SharedPreferencesUtil().todoistAccessToken;

  /// Start OAuth authentication flow
  Future<bool> authenticate() async {
    try {
      final clientId = Env.todoistClientId;
      if (clientId == null || clientId.isEmpty) {
        debugPrint('Todoist Client ID not configured');
        return false;
      }

      final authUri = Uri.parse(_authUrl).replace(queryParameters: {
        'client_id': clientId,
        'scope': 'data:read_write',
        'state': _generateState(),
        'redirect_uri': _redirectUri,
      });

      debugPrint('Opening Todoist auth URL: $authUri');

      final canLaunch = await canLaunchUrl(authUri);
      if (!canLaunch) {
        debugPrint('Cannot launch auth URL');
        return false;
      }

      await launchUrl(
        authUri,
        mode: LaunchMode.externalApplication,
      );

      return true;
    } catch (e) {
      debugPrint('Error starting Todoist authentication: $e');
      return false;
    }
  }

  /// Handle OAuth callback and receive token from backend
  Future<bool> handleCallback(String accessToken) async {
    try {
      if (accessToken.isEmpty) {
        debugPrint('Todoist: No access token received');
        return false;
      }

      // Save token
      SharedPreferencesUtil().todoistAccessToken = accessToken;
      debugPrint('Todoist authentication successful');
      
      // Save connection to Firebase
      await saveTaskIntegration('todoist', {
        'connected': true,
      });
      debugPrint('✓ Saved Todoist connection to Firebase');
      
      return true;
    } catch (e) {
      debugPrint('Error handling Todoist callback: $e');
      return false;
    }
  }

  /// Create a task in Todoist
  Future<bool> createTask({
    required String content,
    String? description,
    DateTime? dueDate,
    int priority = 1,
  }) async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('Not authenticated with Todoist');
        return false;
      }

      final body = <String, dynamic>{
        'content': content,
        if (description != null) 'description': description,
        if (dueDate != null) 'due_string': _formatDueDate(dueDate),
        'priority': priority,
      };

      final response = await http.post(
        Uri.parse('$_apiBaseUrl/tasks'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode(body),
      );

      if (response.statusCode == 200 || response.statusCode == 201) {
        debugPrint('Task created successfully in Todoist');
        return true;
      } else if (response.statusCode == 401) {
        // Token expired or invalid
        debugPrint('Todoist token invalid, clearing authentication');
        await disconnect();
        return false;
      }

      debugPrint('Failed to create task in Todoist: ${response.statusCode} ${response.body}');
      return false;
    } catch (e) {
      debugPrint('Error creating task in Todoist: $e');
      return false;
    }
  }

  /// Disconnect from Todoist (clear stored token)
  Future<void> disconnect() async {
    SharedPreferencesUtil().todoistAccessToken = null;
    
    // Remove connection from Firebase
    try {
      await deleteTaskIntegration('todoist');
      debugPrint('✓ Removed Todoist connection from Firebase');
    } catch (e) {
      debugPrint('Error removing Todoist connection from Firebase: $e');
    }
  }

  /// Generate random state for OAuth
  String _generateState() {
    return DateTime.now().millisecondsSinceEpoch.toString();
  }

  /// Format due date for Todoist API
  String _formatDueDate(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final tomorrow = today.add(const Duration(days: 1));
    final targetDate = DateTime(date.year, date.month, date.day);

    if (targetDate == today) {
      return 'today';
    } else if (targetDate == tomorrow) {
      return 'tomorrow';
    } else {
      // Format as YYYY-MM-DD
      return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    }
  }

  /// Get user's projects (for future use)
  Future<List<Map<String, dynamic>>> getProjects() async {
    try {
      final token = accessToken;
      if (token == null) return [];

      final response = await http.get(
        Uri.parse('$_apiBaseUrl/projects'),
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.cast<Map<String, dynamic>>();
      }

      return [];
    } catch (e) {
      debugPrint('Error fetching Todoist projects: $e');
      return [];
    }
  }
}
