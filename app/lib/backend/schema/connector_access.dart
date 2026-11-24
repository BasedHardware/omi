// Projects the generated connector contract into connection-state sets.
// Missing or invalid rows retain the callers' compatibility literals.
// Scope and client-ID decoding stays owned by the generated wire DTO.
import 'package:omi/backend/schema/gen/api_keys_wire.g.dart' as wire;

/// Scope requirements used by connection checks and key minting.
class ConnectorAccess {
  const ConnectorAccess._(this._wire);

  final wire.GeneratedConnectorAccess _wire;

  Set<String> get clientIds => _wire.clientIds.toSet();
  Set<String> get requiredScopes => _wire.requiredScopes.toSet();
  List<String> get defaultScopes => _wire.defaultScopes;

  static ConnectorAccess? fromJson(dynamic json) {
    if (json is! Map) return null;
    try {
      return ConnectorAccess._(wire.GeneratedConnectorAccess.fromJson(Map<String, dynamic>.from(json)));
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }
}

/// Carries existing raw grant snapshots alongside validated connector metadata.
class McpOauthGrants {
  const McpOauthGrants({required this.grants, this.chatGptAccess});

  final List<Map<String, dynamic>> grants;
  final ConnectorAccess? chatGptAccess;

  factory McpOauthGrants.fromJson(Map<String, dynamic> json) {
    final access = json['connector_access'];
    return McpOauthGrants(
      grants: [
        if (json['grants'] is List)
          for (final grant in json['grants'] as List)
            if (grant is Map<String, dynamic>) grant,
      ],
      chatGptAccess: ConnectorAccess.fromJson(access is Map ? access['chatgpt'] : null),
    );
  }
}
