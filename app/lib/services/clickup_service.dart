import 'package:flutter/foundation.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/utils/logger.dart';

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
        Logger.debug('Failed to get ClickUp OAuth URL from backend');
        return false;
      }

      final authUri = Uri.parse(authUrl);
      Logger.debug('Opening ClickUp auth URL');

      final canLaunch = await canLaunchUrl(authUri);
      if (!canLaunch) {
        Logger.debug('Cannot launch auth URL');
        return false;
      }

      await launchUrl(
        authUri,
        mode: LaunchMode.externalApplication,
      );

      return true;
    } catch (e) {
      Logger.debug('Error starting ClickUp authentication: $e');
      return false;
    }
  }

  /// Handle OAuth callback
  Future<bool> handleCallback({String? userId}) async {
    _isAuthenticated = true;
    _userId = userId;
    Logger.debug('ClickUp authentication successful');
    return true;
  }

  /// Get user's workspaces/teams
  Future<List<Map<String, dynamic>>> getWorkspaces() async {
    try {
      final teams = await getClickUpTeams();
      return teams ?? [];
    } catch (e) {
      Logger.debug('Error fetching ClickUp workspaces: $e');
      return [];
    }
  }

  /// Get spaces in a team
  Future<List<Map<String, dynamic>>> getSpaces(String teamId) async {
    try {
      final spaces = await getClickUpSpaces(teamId);
      return spaces ?? [];
    } catch (e) {
      Logger.debug('Error fetching ClickUp spaces: $e');
      return [];
    }
  }

  /// Get lists in a space
  Future<List<Map<String, dynamic>>> getLists(String spaceId) async {
    try {
      final lists = await getClickUpLists(spaceId);
      return lists ?? [];
    } catch (e) {
      Logger.debug('Error fetching ClickUp lists: $e');
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
      final result = await createTaskViaIntegration(
        'clickup',
        title: name,
        description: description,
        dueDate: dueDate,
      );

      if (result != null && result['success'] == true) {
        Logger.debug('Task created successfully in ClickUp');
        return true;
      }

      Logger.debug('Failed to create task in ClickUp: ${result?['error']}');
      return false;
    } catch (e) {
      Logger.debug('Error creating task in ClickUp: $e');
      return false;
    }
  }

  /// Disconnect from ClickUp
  Future<void> disconnect() async {
    try {
      await deleteTaskIntegration('clickup');
      _isAuthenticated = false;
      _userId = null;
      Logger.debug('Disconnected from ClickUp');
    } catch (e) {
      Logger.debug('Error disconnecting from ClickUp: $e');
    }
  }
}
