import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:url_launcher/url_launcher.dart';

class GoogleTasksService {
  static const String _authUrl = 'https://accounts.google.com/o/oauth2/v2/auth';
  static const String _tokenUrl = 'https://oauth2.googleapis.com/token';
  static const String _apiBaseUrl = 'https://tasks.googleapis.com/tasks/v1';

  // Google Tasks OAuth redirect URL
  static final String _redirectUri = '${Env.apiBaseUrl}v2/integrations/google-tasks/callback';

  static final GoogleTasksService _instance = GoogleTasksService._internal();
  factory GoogleTasksService() => _instance;
  GoogleTasksService._internal();

  /// Check if user is authenticated with Google Tasks
  bool get isAuthenticated => SharedPreferencesUtil().googleTasksAccessToken != null;

  /// Get stored access token
  String? get accessToken => SharedPreferencesUtil().googleTasksAccessToken;

  /// Start OAuth authentication flow
  Future<bool> authenticate() async {
    try {
      final clientId = Env.googleTasksClientId;
      if (clientId == null || clientId.isEmpty) {
        debugPrint('Google Tasks Client ID not configured');
        return false;
      }

      // Google Tasks API scope
      const scopes = 'https://www.googleapis.com/auth/tasks';

      final authUri = Uri.parse(_authUrl).replace(queryParameters: {
        'client_id': clientId,
        'redirect_uri': _redirectUri,
        'response_type': 'code',
        'scope': scopes,
        'access_type': 'offline', // Request refresh token
        'prompt': 'consent', // Force consent screen to get refresh token
        'state': _generateState(),
      });

      debugPrint('Opening Google Tasks auth URL');

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
      debugPrint('Error starting Google Tasks authentication: $e');
      return false;
    }
  }

  /// Handle OAuth callback and exchange code for access token
  Future<bool> handleCallback(String code) async {
    try {
      final clientId = Env.googleTasksClientId;
      final clientSecret = Env.googleTasksClientSecret;

      if (clientId == null || clientSecret == null) {
        debugPrint('Google Tasks credentials not configured');
        return false;
      }

      final response = await http.post(
        Uri.parse(_tokenUrl),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'code': code,
          'client_id': clientId,
          'client_secret': clientSecret,
          'redirect_uri': _redirectUri,
          'grant_type': 'authorization_code',
        },
      );

      debugPrint('Google Tasks token response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final accessToken = data['access_token'] as String?;
        final refreshToken = data['refresh_token'] as String?;

        if (accessToken != null) {
          await SharedPreferencesUtil().saveString('googleTasksAccessToken', accessToken);
          if (refreshToken != null) {
            await SharedPreferencesUtil().saveString('googleTasksRefreshToken', refreshToken);
          }

          debugPrint('✓ Google Tasks tokens saved');

          // Fetch and store default task list
          await _fetchAndStoreDefaultTaskList();

          debugPrint('✓ Google Tasks authentication successful');
          return true;
        }
      }

      debugPrint('❌ Failed to exchange code for token: ${response.statusCode} ${response.body}');
      return false;
    } catch (e) {
      debugPrint('❌ Error handling Google Tasks callback: $e');
      return false;
    }
  }

  /// Fetch and store the default task list
  Future<void> _fetchAndStoreDefaultTaskList() async {
    try {
      final token = accessToken;
      if (token == null) return;

      debugPrint('Fetching Google Tasks lists...');
      final response = await http.get(
        Uri.parse('$_apiBaseUrl/users/@me/lists'),
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      debugPrint('Task lists response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> items = data['items'] ?? [];

        debugPrint('Found ${items.length} task lists');

        if (items.isNotEmpty) {
          // Use the first list (usually "My Tasks")
          final defaultList = items.first;
          final listId = defaultList['id'] as String;
          final listTitle = defaultList['title'] as String;

          SharedPreferencesUtil().googleTasksDefaultListId = listId;
          SharedPreferencesUtil().googleTasksDefaultListTitle = listTitle;

          debugPrint('✓ Default task list: $listTitle ($listId)');
        }
      }
    } catch (e) {
      debugPrint('❌ Error fetching Google Tasks lists: $e');
    }
  }

  /// Get all task lists
  Future<List<Map<String, dynamic>>> getTaskLists() async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('No access token for fetching task lists');
        return [];
      }

      final response = await http.get(
        Uri.parse('$_apiBaseUrl/users/@me/lists'),
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> items = data['items'] ?? [];
        return items.cast<Map<String, dynamic>>();
      } else if (response.statusCode == 401) {
        // Token expired, try to refresh
        final refreshed = await _refreshAccessToken();
        if (refreshed) {
          return getTaskLists(); // Retry
        }
      }

      debugPrint('❌ Failed to fetch task lists: ${response.statusCode}');
      return [];
    } catch (e) {
      debugPrint('❌ Error fetching Google Tasks lists: $e');
      return [];
    }
  }

  /// Create a task in Google Tasks
  Future<bool> createTask({
    required String title,
    String? notes,
    DateTime? dueDate,
  }) async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('Not authenticated with Google Tasks');
        return false;
      }

      // Get the default task list
      String? taskListId = SharedPreferencesUtil().googleTasksDefaultListId;
      if (taskListId == null) {
        // Fetch lists and use the first one
        final lists = await getTaskLists();
        if (lists.isEmpty) {
          debugPrint('No Google Tasks lists available');
          return false;
        }
        taskListId = lists.first['id'] as String;
      }

      final body = <String, dynamic>{
        'title': title,
        if (notes != null) 'notes': notes,
        if (dueDate != null) 'due': _formatDueDate(dueDate),
      };

      debugPrint('Creating Google Task: $title');

      final response = await http.post(
        Uri.parse('$_apiBaseUrl/lists/$taskListId/tasks'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode(body),
      );

      if (response.statusCode == 200 || response.statusCode == 201) {
        final responseData = jsonDecode(response.body);
        debugPrint('✓ Task created successfully in Google Tasks: ${responseData['id']}');
        return true;
      } else if (response.statusCode == 401) {
        // Token expired, try to refresh
        final refreshed = await _refreshAccessToken();
        if (refreshed) {
          return createTask(title: title, notes: notes, dueDate: dueDate); // Retry
        }
        debugPrint('❌ Google Tasks token invalid, clearing authentication');
        await disconnect();
        return false;
      }

      debugPrint('❌ Failed to create task in Google Tasks: ${response.statusCode} ${response.body}');
      return false;
    } catch (e) {
      debugPrint('❌ Error creating task in Google Tasks: $e');
      return false;
    }
  }

  /// Refresh the access token using refresh token
  Future<bool> _refreshAccessToken() async {
    try {
      final refreshToken = SharedPreferencesUtil().googleTasksRefreshToken;
      final clientId = Env.googleTasksClientId;
      final clientSecret = Env.googleTasksClientSecret;

      if (refreshToken == null || clientId == null || clientSecret == null) {
        debugPrint('Cannot refresh token: missing credentials');
        return false;
      }

      final response = await http.post(
        Uri.parse(_tokenUrl),
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'client_id': clientId,
          'client_secret': clientSecret,
          'refresh_token': refreshToken,
          'grant_type': 'refresh_token',
        },
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final newAccessToken = data['access_token'] as String?;

        if (newAccessToken != null) {
          await SharedPreferencesUtil().saveString('googleTasksAccessToken', newAccessToken);
          debugPrint('✓ Access token refreshed');
          return true;
        }
      }

      debugPrint('❌ Failed to refresh access token: ${response.statusCode}');
      return false;
    } catch (e) {
      debugPrint('❌ Error refreshing access token: $e');
      return false;
    }
  }

  /// Disconnect from Google Tasks (clear stored tokens and settings)
  Future<void> disconnect() async {
    SharedPreferencesUtil().googleTasksAccessToken = null;
    SharedPreferencesUtil().googleTasksRefreshToken = null;
    SharedPreferencesUtil().googleTasksDefaultListId = null;
    SharedPreferencesUtil().googleTasksDefaultListTitle = null;
  }

  /// Generate random state for OAuth
  String _generateState() {
    return DateTime.now().millisecondsSinceEpoch.toString();
  }

  /// Format due date for Google Tasks API (RFC 3339 timestamp)
  String _formatDueDate(DateTime date) {
    // Google Tasks uses RFC 3339 format (YYYY-MM-DDTHH:MM:SS.sssZ)
    // For due dates, we use midnight UTC
    final utcDate = DateTime.utc(date.year, date.month, date.day, 0, 0, 0);
    return utcDate.toIso8601String();
  }
}
