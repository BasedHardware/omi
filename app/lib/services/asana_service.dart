import 'package:flutter/foundation.dart';

import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/http/api/task_integrations.dart';
import 'package:omi/utils/logger.dart';

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
        Logger.debug('Failed to get Asana OAuth URL from backend');
        return false;
      }

      final authUri = Uri.parse(authUrl);
      Logger.debug('Opening Asana auth URL');

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
      Logger.debug('Error starting Asana authentication: $e');
      return false;
    }
  }

  /// Handle OAuth callback
  Future<bool> handleCallback({String? userGid}) async {
    _isAuthenticated = true;
    _userGid = userGid;
    Logger.debug('Asana authentication successful');
    return true;
  }

  /// Get user's workspaces
  Future<List<Map<String, dynamic>>> getWorkspaces() async {
    try {
      final workspaces = await getAsanaWorkspaces();
      return workspaces ?? [];
    } catch (e) {
      Logger.debug('Error fetching Asana workspaces: $e');
      return [];
    }
  }

  /// Get projects in a workspace
  Future<List<Map<String, dynamic>>> getProjects(String workspaceGid) async {
    try {
      final projects = await getAsanaProjects(workspaceGid);
      if (projects != null && projects.isNotEmpty) {
        Logger.debug('✓ Found ${projects.length} projects');
      }
      return projects ?? [];
    } catch (e) {
      Logger.debug('Error fetching Asana projects: $e');
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
      final result = await createTaskViaIntegration(
        'asana',
        title: name,
        description: notes,
        dueDate: dueDate,
      );

      if (result != null && result['success'] == true) {
        Logger.debug('Task created successfully in Asana');
        return true;
      }

      Logger.debug('Failed to create task in Asana: ${result?['error']}');
      return false;
    } catch (e) {
      Logger.debug('Error creating task in Asana: $e');
      return false;
    }
  }

  /// Disconnect from Asana
  Future<void> disconnect() async {
    try {
      await deleteTaskIntegration('asana');
      _isAuthenticated = false;
      _userGid = null;
      Logger.debug('Disconnected from Asana');
    } catch (e) {
      Logger.debug('Error disconnecting from Asana: $e');
    }
  }
}
