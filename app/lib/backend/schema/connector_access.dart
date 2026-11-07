/// The backend-owned connector product contract. Missing/invalid contracts come
/// from older backends; callers retain their offline literals in that case.
class ConnectorAccess {
  const ConnectorAccess({required this.clientIds, required this.requiredScopes, required this.defaultScopes});

  final Set<String> clientIds;
  final Set<String> requiredScopes;
  final List<String> defaultScopes;

  static ConnectorAccess? fromJson(dynamic json) {
    if (json is! Map) return null;
    for (final field in ['client_ids', 'required_scopes', 'default_scopes']) {
      if (json[field] is! List || (json[field] as List).any((value) => value is! String)) return null;
    }
    return ConnectorAccess(
      clientIds: Set<String>.from(json['client_ids'] as List),
      requiredScopes: Set<String>.from(json['required_scopes'] as List),
      defaultScopes: List<String>.from(json['default_scopes'] as List),
    );
  }
}

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
