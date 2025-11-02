import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:url_launcher/url_launcher.dart';

class AsanaService {
  static const String _authUrl = 'https://app.asana.com/-/oauth_authorize';
  static const String _tokenUrl = 'https://app.asana.com/-/oauth_token';
  static const String _apiBaseUrl = 'https://app.asana.com/api/1.0';

  // Asana requires HTTPS redirect URL
  // Using Omi's production API endpoint
  static final String _redirectUri = '${Env.apiBaseUrl}v2/integrations/asana/callback';

  static final AsanaService _instance = AsanaService._internal();
  factory AsanaService() => _instance;
  AsanaService._internal();

  /// Check if user is authenticated with Asana
  bool get isAuthenticated => SharedPreferencesUtil().asanaAccessToken != null;

  /// Get stored access token
  String? get accessToken => SharedPreferencesUtil().asanaAccessToken;

  /// Start OAuth authentication flow
  Future<bool> authenticate() async {
    try {
      final clientId = Env.asanaClientId;
      if (clientId == null || clientId.isEmpty) {
        debugPrint('Asana Client ID not configured');
        return false;
      }

      // Explicitly request only the scopes we need (space-separated)
      // This prevents Asana from trying to use default identity scopes
      const scopes = 'tasks:read tasks:write workspaces:read projects:read users:read';

      final authUri = Uri.parse(_authUrl).replace(queryParameters: {
        'client_id': clientId,
        'redirect_uri': _redirectUri,
        'response_type': 'code',
        'state': _generateState(),
        'scope': scopes,
      });

      debugPrint('Opening Asana auth URL: $authUri');

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
      debugPrint('Error starting Asana authentication: $e');
      return false;
    }
  }

  /// Handle OAuth callback and receive tokens from backend
  Future<bool> handleCallback(String accessToken, String? refreshToken) async {
    try {
      if (accessToken.isEmpty) {
        debugPrint('Asana: No access token received');
        return false;
      }

      // Save tokens
      await SharedPreferencesUtil().saveString('asanaAccessToken', accessToken);
      if (refreshToken != null && refreshToken.isNotEmpty) {
        await SharedPreferencesUtil().saveString('asanaRefreshToken', refreshToken);
      }

      debugPrint('✓ Tokens saved, fetching user info...');

      // Fetch and store current user info
      await _fetchAndStoreCurrentUser();

      debugPrint('✓ Asana authentication successful');
      return true;
    } catch (e) {
      debugPrint('Error handling Asana callback: $e');
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

      debugPrint('Fetching Asana user info...');
      final response = await http.get(
        Uri.parse('$_apiBaseUrl/users/me'),
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      debugPrint('User info response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        debugPrint('User data: $data');
        final userGid = data['data']['gid'] as String?;
        if (userGid != null && userGid.isNotEmpty) {
          await SharedPreferencesUtil().saveString('asanaUserGid', userGid);
          debugPrint('✓ Stored Asana user GID: $userGid');
          
          // Save connection to Firebase
          await saveTaskIntegration('asana', {
            'connected': true,
            'user_gid': userGid,
          });
          debugPrint('✓ Saved Asana connection to Firebase');
        } else {
          debugPrint('❌ No GID found in user data');
        }
      } else {
        debugPrint('❌ Failed to fetch user info: ${response.statusCode} - ${response.body}');
      }
    } catch (e) {
      debugPrint('❌ Error fetching Asana user info: $e');
    }
  }

  /// Get current user's GID
  String? get currentUserGid => SharedPreferencesUtil().asanaUserGid;

  /// Manually refresh current user info (useful for debugging)
  Future<void> refreshCurrentUser() async {
    await _fetchAndStoreCurrentUser();
  }

  /// Get user's workspaces
  Future<List<Map<String, dynamic>>> getWorkspaces() async {
    try {
      final token = accessToken;
      if (token == null) return [];

      final response = await http.get(
        Uri.parse('$_apiBaseUrl/workspaces'),
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> workspaces = data['data'];
        return workspaces.cast<Map<String, dynamic>>();
      }

      return [];
    } catch (e) {
      debugPrint('Error fetching Asana workspaces: $e');
      return [];
    }
  }

  /// Get projects in a workspace
  Future<List<Map<String, dynamic>>> getProjects(String workspaceGid) async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('No access token for fetching projects');
        return [];
      }

      debugPrint('Fetching projects for workspace: $workspaceGid');

      // First try to get user's projects in this workspace
      final userGid = currentUserGid;
      Uri projectsUri;

      if (userGid != null && userGid.isNotEmpty) {
        // Get projects assigned to the user in this workspace
        projectsUri =
            Uri.parse('$_apiBaseUrl/projects?workspace=$workspaceGid&archived=false&opt_fields=name,gid,owner');
      } else {
        // Get all projects in workspace
        projectsUri =
            Uri.parse('$_apiBaseUrl/projects?workspace=$workspaceGid&archived=false&opt_fields=name,gid,owner');
      }

      final response = await http.get(
        projectsUri,
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      debugPrint('Projects response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        debugPrint('Projects response body: ${response.body}');
        final List<dynamic> projects = data['data'];
        debugPrint('✓ Found ${projects.length} projects');
        return projects.cast<Map<String, dynamic>>();
      } else {
        debugPrint('❌ Failed to fetch projects: ${response.statusCode} - ${response.body}');
      }

      return [];
    } catch (e) {
      debugPrint('❌ Error fetching Asana projects: $e');
      return [];
    }
  }

  /// Create a task in Asana
  Future<bool> createTask({
    required String name,
    String? notes,
    DateTime? dueDate,
  }) async {
    try {
      final token = accessToken;
      if (token == null) {
        debugPrint('Not authenticated with Asana');
        return false;
      }

      // Get workspace from preferences (or use first available)
      String? targetWorkspace = SharedPreferencesUtil().asanaWorkspaceGid;
      if (targetWorkspace == null) {
        final workspaces = await getWorkspaces();
        if (workspaces.isEmpty) {
          debugPrint('No Asana workspaces available');
          return false;
        }
        targetWorkspace = workspaces.first['gid'] as String;
      }

      // Get current user GID for assignee
      final userGid = currentUserGid;
      debugPrint('Creating task with user GID: $userGid');

      // Build task data
      final taskData = <String, dynamic>{
        'name': name,
        if (notes != null) 'notes': notes,
        if (dueDate != null) 'due_on': _formatDueDate(dueDate),
        'workspace': targetWorkspace,
        if (userGid != null && userGid.isNotEmpty) 'assignee': userGid,
      };

      debugPrint('Task data: $taskData');

      // Add project if selected
      final projectGid = SharedPreferencesUtil().asanaProjectGid;
      if (projectGid != null) {
        taskData['projects'] = [projectGid];
      }

      final body = {'data': taskData};

      final response = await http.post(
        Uri.parse('$_apiBaseUrl/tasks'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode(body),
      );

      if (response.statusCode == 200 || response.statusCode == 201) {
        final responseData = jsonDecode(response.body);
        debugPrint('✓ Task created successfully in Asana: ${responseData['data']}');
        return true;
      } else if (response.statusCode == 401) {
        // Token expired or invalid
        debugPrint('❌ Asana token invalid, clearing authentication');
        await disconnect();
        return false;
      }

      debugPrint('❌ Failed to create task in Asana: ${response.statusCode} ${response.body}');
      return false;
    } catch (e) {
      debugPrint('Error creating task in Asana: $e');
      return false;
    }
  }

  /// Disconnect from Asana (clear stored tokens and settings)
  Future<void> disconnect() async {
    SharedPreferencesUtil().asanaAccessToken = null;
    SharedPreferencesUtil().asanaRefreshToken = null;
    SharedPreferencesUtil().asanaUserGid = null;
    SharedPreferencesUtil().asanaWorkspaceGid = null;
    SharedPreferencesUtil().asanaWorkspaceName = null;
    SharedPreferencesUtil().asanaProjectGid = null;
    SharedPreferencesUtil().asanaProjectName = null;
    
    // Remove connection from Firebase
    try {
      await deleteTaskIntegration('asana');
      debugPrint('✓ Removed Asana connection from Firebase');
    } catch (e) {
      debugPrint('Error removing Asana connection from Firebase: $e');
    }
  }

  /// Generate random state for OAuth
  String _generateState() {
    return DateTime.now().millisecondsSinceEpoch.toString();
  }

  /// Format due date for Asana API (YYYY-MM-DD)
  String _formatDueDate(DateTime date) {
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }
}
