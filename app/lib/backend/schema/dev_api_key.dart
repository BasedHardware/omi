class DevApiKey {
  final String id;
  final String name;
  final String keyPrefix;
  final DateTime createdAt;
  final DateTime? lastUsedAt;
  final List<String>? scopes;

  DevApiKey({
    required this.id,
    required this.name,
    required this.keyPrefix,
    required this.createdAt,
    this.lastUsedAt,
    this.scopes,
  });

  factory DevApiKey.fromJson(Map<String, dynamic> json) {
    return DevApiKey(
      id: json['id'],
      name: json['name'],
      keyPrefix: json['key_prefix'],
      createdAt: DateTime.parse(json['created_at']),
      lastUsedAt: json['last_used_at'] != null ? DateTime.parse(json['last_used_at']) : null,
      scopes: json['scopes'] != null ? List<String>.from(json['scopes']) : null,
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
    super.scopes,
    required this.key,
  });

  factory DevApiKeyCreated.fromJson(Map<String, dynamic> json) {
    return DevApiKeyCreated(
      id: json['id'],
      name: json['name'],
      keyPrefix: json['key_prefix'],
      createdAt: DateTime.parse(json['created_at']),
      lastUsedAt: json['last_used_at'] != null ? DateTime.parse(json['last_used_at']) : null,
      scopes: json['scopes'] != null ? List<String>.from(json['scopes']) : null,
      key: json['key'],
    );
  }
}
