class DevApiKey {
  final String id;
  final String name;
  final String keyPrefix;
  final DateTime createdAt;
  final DateTime? lastUsedAt;

  DevApiKey({
    required this.id,
    required this.name,
    required this.keyPrefix,
    required this.createdAt,
    this.lastUsedAt,
  });

  factory DevApiKey.fromJson(Map<String, dynamic> json) {
    return DevApiKey(
      id: json['id'],
      name: json['name'],
      keyPrefix: json['key_prefix'],
      createdAt: DateTime.parse(json['created_at']),
      lastUsedAt: json['last_used_at'] != null ? DateTime.parse(json['last_used_at']) : null,
    );
  }
}

class DevApiKeyCreated extends DevApiKey {
  final String key;

  DevApiKeyCreated({
    required super.id,
    required super.name,
    required super.keyPrefix,
    required super.createdAt,
    super.lastUsedAt,
    required this.key,
  });

  factory DevApiKeyCreated.fromJson(Map<String, dynamic> json) {
    return DevApiKeyCreated(
      id: json['id'],
      name: json['name'],
      keyPrefix: json['key_prefix'],
      createdAt: DateTime.parse(json['created_at']),
      lastUsedAt: json['last_used_at'] != null ? DateTime.parse(json['last_used_at']) : null,
      key: json['key'],
    );
  }
}
