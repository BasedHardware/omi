import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class ClickUpService {
  static final ClickUpService _instance = ClickUpService._internal();
  factory ClickUpService() => _instance;
  ClickUpService._internal();

  bool _isAuthenticated = false;
  String? _userId;

  /// Check if user is authenticated (updated by provider from Firebase)
  bool get isAuthenticated => _isAuthenticated;

  String? get currentUserId => _userId;

  void setAuthenticated(bool value, {String? userId}) {
    _isAuthenticated = value;
    _userId = userId;
  }

  /// Start OAuth authentication flow (get URL from backend)
  Future<bool> authenticate() async {
    try {
      final authUrl = await getOAuthUrl('clickup');
      if (authUrl == null) {
        debugPrint('Failed to get ClickUp OAuth URL from backend');
        return false;
      }

      final authUri = Uri.parse(authUrl);
      debugPrint('Opening ClickUp auth URL');

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

  /// Handle OAuth callback (tokens stored in backend Firebase)
  Future<bool> handleCallback({String? userId}) async {
    _isAuthenticated = true;
    _userId = userId;
    debugPrint('ClickUp authentication successful');
    return true;
  }

  /// Get user's workspaces/teams (via backend stored token)
  Future<List<Map<String, dynamic>>> getWorkspaces() async {
    try {
      // Get integration from backend to access token
      final integrations = await getTaskIntegrations();
      if (integrations == null) return [];

      final clickupIntegration = integrations.integrations['clickup'];
      if (clickupIntegration == null) return [];

      final accessToken = clickupIntegration['access_token'];
      if (accessToken == null) return [];

      final response = await http.get(
        Uri.parse('https://api.clickup.com/api/v2/team'),
        headers: {'Authorization': accessToken},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> teams = data['teams'];
        return teams.cast<Map<String, dynamic>>();
      }

      return [];
    } catch (e) {
      debugPrint('Error fetching ClickUp workspaces: $e');
      return [];
    }
  }

  /// Get spaces in a team (via backend stored token)
  Future<List<Map<String, dynamic>>> getSpaces(String teamId) async {
    try {
      // Get integration from backend to access token
      final integrations = await getTaskIntegrations();
      if (integrations == null) return [];

      final clickupIntegration = integrations.integrations['clickup'];
      if (clickupIntegration == null) return [];

      final accessToken = clickupIntegration['access_token'];
      if (accessToken == null) return [];

      final response = await http.get(
        Uri.parse('https://api.clickup.com/api/v2/team/$teamId/space?archived=false'),
        headers: {'Authorization': accessToken},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> spaces = data['spaces'];
        return spaces.cast<Map<String, dynamic>>();
      }

      return [];
    } catch (e) {
      debugPrint('Error fetching ClickUp spaces: $e');
      return [];
    }
  }

  /// Get lists in a space (via backend stored token)
  Future<List<Map<String, dynamic>>> getLists(String spaceId) async {
    try {
      // Get integration from backend to access token
      final integrations = await getTaskIntegrations();
      if (integrations == null) return [];

      final clickupIntegration = integrations.integrations['clickup'];
      if (clickupIntegration == null) return [];

      final accessToken = clickupIntegration['access_token'];
      if (accessToken == null) return [];

      final response = await http.get(
        Uri.parse('https://api.clickup.com/api/v2/space/$spaceId/list?archived=false'),
        headers: {'Authorization': accessToken},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final List<dynamic> lists = data['lists'];
        return lists.cast<Map<String, dynamic>>();
      }

      return [];
    } catch (e) {
      debugPrint('Error fetching ClickUp lists: $e');
      return [];
    }
  }

  /// Create a task in ClickUp (via backend API)
  Future<bool> createTask({
    required String name,
    String? description,
    DateTime? dueDate,
  }) async {
    try {
      final result = await createTaskViaIntegration(
        'clickup',
        title: name,
        description: description,
        dueDate: dueDate,
      );

      if (result != null && result['success'] == true) {
        debugPrint('✓ Task created successfully in ClickUp');
        return true;
      }

      debugPrint('❌ Failed to create task in ClickUp: ${result?['error']}');
      return false;
    } catch (e) {
      debugPrint('Error creating task in ClickUp: $e');
      return false;
    }
  }

  /// Disconnect from ClickUp (remove from Firebase)
  Future<void> disconnect() async {
    try {
      await deleteTaskIntegration('clickup');
      _isAuthenticated = false;
      _userId = null;
      debugPrint('✓ Disconnected from ClickUp');
    } catch (e) {
      debugPrint('Error disconnecting from ClickUp: $e');
    }
  }
}
