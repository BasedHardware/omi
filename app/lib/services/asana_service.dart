import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:omi/env/env.dart';

class AsanaService {
  static final AsanaService _instance = AsanaService._internal();
  factory AsanaService() => _instance;
  AsanaService._internal();

  bool _isAuthenticated = false;
  String? _userGid;

  /// Check if user is authenticated (updated by provider from Firebase)
  bool get isAuthenticated => _isAuthenticated;

  String? get currentUserGid => _userGid;

  void setAuthenticated(bool value, {String? userGid}) {
    _isAuthenticated = value;
    _userGid = userGid;
  }

  /// Start OAuth authentication flow (get URL from backend)
  Future<bool> authenticate() async {
    try {
      final authUrl = await getOAuthUrl('asana');
      if (authUrl == null) {
        debugPrint('Failed to get Asana OAuth URL from backend');
        return false;
      }

      final authUri = Uri.parse(authUrl);
      debugPrint('Opening Asana auth URL');

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

  /// Handle OAuth callback (tokens stored in backend Firebase)
  Future<bool> handleCallback({String? userGid}) async {
    _isAuthenticated = true;
    _userGid = userGid;
    debugPrint('Asana authentication successful');
    return true;
  }

  /// Get user's workspaces (via backend stored token)
  Future<List<Map<String, dynamic>>> getWorkspaces() async {
    try {
      // Get integration from backend to access token
      final integrations = await getTaskIntegrations();
      if (integrations == null) return [];

      final asanaIntegration = integrations.integrations['asana'];
      if (asanaIntegration == null) return [];

      final accessToken = asanaIntegration['access_token'];
      if (accessToken == null) return [];

      final response = await http.get(
        Uri.parse('https://app.asana.com/api/1.0/workspaces'),
        headers: {'Authorization': 'Bearer $accessToken'},
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

  /// Get projects in a workspace (via backend stored token)
  Future<List<Map<String, dynamic>>> getProjects(String workspaceGid) async {
    try {
      // Get integration from backend to access token
      final integrations = await getTaskIntegrations();
      if (integrations == null) return [];

      final asanaIntegration = integrations.integrations['asana'];
      if (asanaIntegration == null) return [];

      final accessToken = asanaIntegration['access_token'];
      if (accessToken == null) return [];

      final projectsUri = Uri.parse(
          'https://app.asana.com/api/1.0/projects?workspace=$workspaceGid&archived=false&opt_fields=name,gid,owner');

      final response = await http.get(
        projectsUri,
        headers: {'Authorization': 'Bearer $accessToken'},
      );

      debugPrint('Projects response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> projects = data['data'];
        debugPrint('✓ Found ${projects.length} projects');
        return projects.cast<Map<String, dynamic>>();
      } else {
        debugPrint('❌ Failed to fetch projects: ${response.statusCode}');
      }

      return [];
    } catch (e) {
      debugPrint('❌ Error fetching Asana projects: $e');
      return [];
    }
  }

  /// Create a task in Asana (via backend API)
  Future<bool> createTask({
    required String name,
    String? notes,
    DateTime? dueDate,
  }) async {
    try {
      final result = await createTaskViaIntegration(
        'asana',
        title: name,
        description: notes,
        dueDate: dueDate,
      );

      if (result != null && result['success'] == true) {
        debugPrint('✓ Task created successfully in Asana');
        return true;
      }

      debugPrint('❌ Failed to create task in Asana: ${result?['error']}');
      return false;
    } catch (e) {
      debugPrint('Error creating task in Asana: $e');
      return false;
    }
  }

  /// Disconnect from Asana (remove from Firebase)
  Future<void> disconnect() async {
    try {
      await deleteTaskIntegration('asana');
      _isAuthenticated = false;
      _userGid = null;
      debugPrint('✓ Disconnected from Asana');
    } catch (e) {
      debugPrint('Error disconnecting from Asana: $e');
    }
  }
}
