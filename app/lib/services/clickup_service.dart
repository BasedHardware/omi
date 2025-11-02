import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:url_launcher/url_launcher.dart';

class ClickUpService {
  // ClickUp OAuth URLs - note that authorization happens via query params on the main URL
  static const String _authBaseUrl = 'https://app.clickup.com/api';
  static const String _tokenUrl = 'https://api.clickup.com/api/v2/oauth/token';
  static const String _apiBaseUrl = 'https://api.clickup.com/api/v2';

  // ClickUp OAuth redirect URL
  static final String _redirectUri = '${Env.apiBaseUrl}v2/integrations/clickup/callback';

  static final ClickUpService _instance = ClickUpService._internal();
  factory ClickUpService() => _instance;
  ClickUpService._internal();

  /// Check if user is authenticated with ClickUp
  bool get isAuthenticated => SharedPreferencesUtil().clickupAccessToken != null;

  /// Get stored access token
  String? get accessToken => SharedPreferencesUtil().clickupAccessToken;

  /// Get current user's ID
  String? get currentUserId => SharedPreferencesUtil().clickupUserId;

  /// Start OAuth authentication flow
  Future<bool> authenticate() async {
    try {
      final clientId = Env.clickupClientId;
      if (clientId == null || clientId.isEmpty) {
        debugPrint('ClickUp Client ID not configured');
        return false;
      }

      // ClickUp uses query parameters directly in the URL
      final authUrl = '$_authBaseUrl?client_id=$clientId&redirect_uri=${Uri.encodeComponent(_redirectUri)}';
      final authUri = Uri.parse(authUrl);

      debugPrint('Opening ClickUp auth URL: $authUrl');

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
      debugPrint('Error starting ClickUp authentication: $e');
      return false;
    }
  }

  /// Handle OAuth callback and receive token from backend
  Future<bool> handleCallback(String accessToken) async {
    try {
      if (accessToken.isEmpty) {
        debugPrint('ClickUp: No access token received');
        return false;
      }

      // Save token
      await SharedPreferencesUtil().saveString('clickupAccessToken', accessToken);

      debugPrint('✓ ClickUp tokens saved');

      // Fetch and store current user info
      await _fetchAndStoreCurrentUser();

      debugPrint('✓ ClickUp authentication successful');
      return true;
    } catch (e) {
      debugPrint('❌ Error handling ClickUp callback: $e');
      return false;
    }
  }

  /// Fetch and store current user info
  Future<void> _fetchAndStoreCurrentUser() async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('No access token for fetching user info');
        return;
      }

      debugPrint('Fetching ClickUp user info...');
      final response = await http.get(
        Uri.parse('$_apiBaseUrl/user'),
        headers: {
          'Authorization': token,
        },
      );

      debugPrint('User info response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        debugPrint('User data: $data');
        final userId = data['user']['id'].toString();
        if (userId.isNotEmpty) {
          await SharedPreferencesUtil().saveString('clickupUserId', userId);
          debugPrint('✓ Stored ClickUp user ID: $userId');

          // Save connection to Firebase
          await saveTaskIntegration('clickup', {
            'connected': true,
            'user_id': userId,
          });
          debugPrint('✓ Saved ClickUp connection to Firebase');
        }
      } else {
        debugPrint('❌ Failed to fetch user info: ${response.statusCode} - ${response.body}');
      }
    } catch (e) {
      debugPrint('❌ Error fetching ClickUp user info: $e');
    }
  }

  /// Manually refresh current user info
  Future<void> refreshCurrentUser() async {
    await _fetchAndStoreCurrentUser();
  }

  /// Get user's workspaces (teams)
  Future<List<Map<String, dynamic>>> getWorkspaces() async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('No access token for fetching workspaces');
        return [];
      }

      final response = await http.get(
        Uri.parse('$_apiBaseUrl/team'),
        headers: {
          'Authorization': token,
        },
      );

      debugPrint('Workspaces response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        debugPrint('Workspaces data: $data');
        final List<dynamic> teams = data['teams'] ?? [];
        debugPrint('✓ Found ${teams.length} workspaces');
        return teams.cast<Map<String, dynamic>>();
      } else {
        debugPrint('❌ Failed to fetch workspaces: ${response.statusCode} - ${response.body}');
      }

      return [];
    } catch (e) {
      debugPrint('❌ Error fetching ClickUp workspaces: $e');
      return [];
    }
  }

  /// Get spaces in a workspace
  Future<List<Map<String, dynamic>>> getSpaces(String teamId) async {
    try {
      final token = accessToken;
      if (token == null) return [];

      debugPrint('Fetching spaces for team: $teamId');
      final response = await http.get(
        Uri.parse('$_apiBaseUrl/team/$teamId/space?archived=false'),
        headers: {
          'Authorization': token,
        },
      );

      debugPrint('Spaces response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        debugPrint('Spaces response body: ${response.body}');
        final List<dynamic> spaces = data['spaces'] ?? [];
        debugPrint('✓ Found ${spaces.length} spaces');
        return spaces.cast<Map<String, dynamic>>();
      } else {
        debugPrint('❌ Failed to fetch spaces: ${response.statusCode} - ${response.body}');
      }

      return [];
    } catch (e) {
      debugPrint('❌ Error fetching ClickUp spaces: $e');
      return [];
    }
  }

  /// Get lists in a space
  Future<List<Map<String, dynamic>>> getLists(String spaceId) async {
    try {
      final token = accessToken;
      if (token == null) return [];

      debugPrint('Fetching lists for space: $spaceId');
      final response = await http.get(
        Uri.parse('$_apiBaseUrl/space/$spaceId/list?archived=false'),
        headers: {
          'Authorization': token,
        },
      );

      debugPrint('Lists response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        debugPrint('Lists response body: ${response.body}');
        final List<dynamic> lists = data['lists'] ?? [];
        debugPrint('✓ Found ${lists.length} lists');
        return lists.cast<Map<String, dynamic>>();
      } else {
        debugPrint('❌ Failed to fetch lists: ${response.statusCode} - ${response.body}');
      }

      return [];
    } catch (e) {
      debugPrint('❌ Error fetching ClickUp lists: $e');
      return [];
    }
  }

  /// Create a task in ClickUp
  Future<bool> createTask({
    required String name,
    String? description,
    DateTime? dueDate,
  }) async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('Not authenticated with ClickUp');
        return false;
      }

      // Get the selected list
      String? listId = SharedPreferencesUtil().clickupListId;
      if (listId == null) {
        debugPrint('No ClickUp list selected');
        return false;
      }

      // Get current user ID for assignee
      final userId = currentUserId;
      debugPrint('Creating task with user ID: $userId');

      // Build task data
      final taskData = <String, dynamic>{
        'name': name,
        if (description != null) 'description': description,
        if (dueDate != null) 'due_date': dueDate.millisecondsSinceEpoch,
        if (userId != null && userId.isNotEmpty) 'assignees': [int.parse(userId)],
      };

      debugPrint('Task data: $taskData');

      final response = await http.post(
        Uri.parse('$_apiBaseUrl/list/$listId/task'),
        headers: {
          'Authorization': token,
          'Content-Type': 'application/json',
        },
        body: jsonEncode(taskData),
      );

      if (response.statusCode == 200 || response.statusCode == 201) {
        final responseData = jsonDecode(response.body);
        debugPrint('✓ Task created successfully in ClickUp: ${responseData['id']}');
        return true;
      } else if (response.statusCode == 401) {
        debugPrint('❌ ClickUp token invalid, clearing authentication');
        await disconnect();
        return false;
      }

      debugPrint('❌ Failed to create task in ClickUp: ${response.statusCode} ${response.body}');
      return false;
    } catch (e) {
      debugPrint('❌ Error creating task in ClickUp: $e');
      return false;
    }
  }

  /// Disconnect from ClickUp (clear stored tokens and settings)
  Future<void> disconnect() async {
    SharedPreferencesUtil().clickupAccessToken = null;
    SharedPreferencesUtil().clickupUserId = null;
    SharedPreferencesUtil().clickupTeamId = null;
    SharedPreferencesUtil().clickupTeamName = null;
    SharedPreferencesUtil().clickupSpaceId = null;
    SharedPreferencesUtil().clickupSpaceName = null;
    SharedPreferencesUtil().clickupListId = null;
    SharedPreferencesUtil().clickupListName = null;

    // Remove connection from Firebase
    try {
      await deleteTaskIntegration('clickup');
      debugPrint('✓ Removed ClickUp connection from Firebase');
    } catch (e) {
      debugPrint('Error removing ClickUp connection from Firebase: $e');
    }
  }
}
