import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/privacy_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

class MigrationRequest {
  final String id;
  final String type;
  final String targetLevel;

  MigrationRequest({required this.id, required this.type, required this.targetLevel});

  factory MigrationRequest.fromGenerated(wire.GeneratedMigrationRequest generated) {
    return MigrationRequest(id: generated.id, type: generated.type, targetLevel: generated.targetLevel);
  }

  wire.GeneratedMigrationRequest toGenerated() {
    return wire.GeneratedMigrationRequest(id: id, type: type, targetLevel: targetLevel);
  }

  Map<String, dynamic> toJson() {
    return toGenerated().toJson();
  }
}

class PrivacyApi {
  static Future<Map<String, dynamic>> getUserProfile() async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/profile',
        method: 'GET',
        headers: {},
        body: '',
      );

      if (response != null && response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        wire.GeneratedUserProfileResponse.fromJson(decoded);
        return decoded;
      } else {
        if (response?.statusCode == 410) {
          Logger.error('User profile not found: ${response?.statusCode} ${response?.body}');
          throw Exception('User profile not found');
        }
        Logger.error('Failed to get user profile: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to load user profile');
      }
    } catch (e, stackTrace) {
      Logger.error('Error getting user profile: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<void> startMigration(String targetLevel) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/migration/requests',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(wire.GeneratedMigrationTargetRequest(targetLevel: targetLevel).toJson()),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Failed to start migration: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to start migration');
      }
      final data = wire.GeneratedMigrationStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      if (data.status != 'ok') {
        throw Exception('Failed to start migration');
      }
    } catch (e, stackTrace) {
      Logger.error('Error starting migration: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<List<MigrationRequest>> checkMigration(String targetLevel) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/migration/requests?target_level=$targetLevel',
        method: 'GET',
        headers: {},
        body: '',
      );
      if (response != null && response.statusCode == 200) {
        final body = wire.GeneratedMigrationRequestsResponse.fromJson(
          jsonDecode(response.body) as Map<String, dynamic>,
        );
        final objects = body.needsMigration ?? const <Map<String, dynamic>>[];
        return objects
            .map(
              (obj) => MigrationRequest.fromGenerated(
                wire.GeneratedMigrationRequest.fromJson({
                  ...Map<String, dynamic>.from(obj),
                  'target_level': targetLevel,
                }),
              ),
            )
            .toList();
      } else {
        Logger.error('Failed to check migration status: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to check migration status');
      }
    } catch (e, stackTrace) {
      Logger.error('Error checking migration status: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<void> migrateObject(MigrationRequest request) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/migration/requests',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(request.toJson()),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Failed to migrate object ${request.id}: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to migrate object');
      }
      final data = wire.GeneratedMigrationStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      if (data.status != 'ok') {
        throw Exception('Failed to migrate object');
      }
    } catch (e, stackTrace) {
      Logger.error('Error migrating object ${request.id}: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<void> migrateObjectsBatch(List<MigrationRequest> requests) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/migration/batch-requests',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(
          wire.GeneratedBatchMigrationRequest(
            requests: requests.map((request) => request.toGenerated()).toList(),
          ).toJson(),
        ),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Failed to migrate batch: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to migrate batch');
      }
      final data = wire.GeneratedMigrationStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      if (data.status != 'ok') {
        throw Exception('Failed to migrate batch');
      }
    } catch (e, stackTrace) {
      Logger.error('Error migrating batch: $e\n$stackTrace');
      rethrow;
    }
  }

  static Future<void> finalizeMigration(String targetLevel) async {
    try {
      final response = await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/migration/requests/data-protection-level/finalize',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(wire.GeneratedMigrationTargetRequest(targetLevel: targetLevel).toJson()),
      );
      if (response == null || response.statusCode != 200) {
        Logger.error('Failed to finalize migration: ${response?.statusCode} ${response?.body}');
        throw Exception('Failed to finalize migration');
      }
      final data = wire.GeneratedMigrationStatusResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
      if (data.status != 'ok') {
        throw Exception('Failed to finalize migration');
      }
    } catch (e, stackTrace) {
      Logger.error('Error finalizing migration: $e\n$stackTrace');
      rethrow;
    }
  }
}
