class McpApiKey {
  final String id;
  final String name;
  final String keyPrefix;
  final DateTime createdAt;
  final DateTime? lastUsedAt;

  McpApiKey({
    required this.id,
    required this.name,
    required this.keyPrefix,
    required this.createdAt,
    this.lastUsedAt,
  });

  factory McpApiKey.fromJson(Map<String, dynamic> json) {
    return McpApiKey(
      id: json['id'],
      name: json['name'],
      keyPrefix: json['key_prefix'],
      createdAt: DateTime.parse(json['created_at']),
      lastUsedAt: json['last_used_at'] != null ? DateTime.parse(json['last_used_at']) : null,
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
    required this.key,
  });

  factory McpApiKeyCreated.fromJson(Map<String, dynamic> json) {
    return McpApiKeyCreated(
      id: json['id'],
      name: json['name'],
      keyPrefix: json['key_prefix'],
      createdAt: DateTime.parse(json['created_at']),
      lastUsedAt: json['last_used_at'] != null ? DateTime.parse(json['last_used_at']) : null,
      key: json['key'],
    );
  }
}
