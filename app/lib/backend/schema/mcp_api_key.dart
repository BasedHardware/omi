import 'package:omi/backend/schema/gen/api_keys_wire.g.dart' as wire;

class McpApiKey {
  final String id;
  final String name;
  final String keyPrefix;
  final DateTime createdAt;
  final DateTime? lastUsedAt;
  final String? appId;
  final List<String>? scopes;

  McpApiKey({
    required this.id,
    required this.name,
    required this.keyPrefix,
    required this.createdAt,
    this.lastUsedAt,
    this.appId,
    this.scopes,
  });

  factory McpApiKey.fromJson(Map<String, dynamic> json) {
    return McpApiKey.fromGenerated(wire.GeneratedMcpApiKey.fromJson(json));
  }

  factory McpApiKey.fromGenerated(wire.GeneratedMcpApiKey generated) {
    return McpApiKey(
      id: generated.id,
      name: generated.name,
      keyPrefix: generated.keyPrefix,
      createdAt: generated.createdAt,
      lastUsedAt: generated.lastUsedAt,
      appId: generated.appId,
      scopes: generated.scopes,
    );
  }
}

class McpApiKeyCreated extends McpApiKey {
  final String key;

  McpApiKeyCreated({
    required super.id,
    required super.name,
    required super.keyPrefix,
    required super.createdAt,
    super.lastUsedAt,
    super.appId,
    super.scopes,
    required this.key,
  });

  factory McpApiKeyCreated.fromJson(Map<String, dynamic> json) {
    return McpApiKeyCreated.fromGenerated(wire.GeneratedMcpApiKeyCreated.fromJson(json));
  }

  factory McpApiKeyCreated.fromGenerated(wire.GeneratedMcpApiKeyCreated generated) {
    return McpApiKeyCreated(
      id: generated.id,
      name: generated.name,
      keyPrefix: generated.keyPrefix,
      createdAt: generated.createdAt,
      lastUsedAt: generated.lastUsedAt,
      appId: generated.appId,
      scopes: generated.scopes,
      key: generated.key,
    );
  }
}
