import 'package:omi/backend/schema/gen/api_keys_wire.g.dart' as wire;

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
    return DevApiKey.fromGenerated(wire.GeneratedDevApiKey.fromJson(json));
  }

  factory DevApiKey.fromGenerated(wire.GeneratedDevApiKey generated) {
    return DevApiKey(
      id: generated.id,
      name: generated.name,
      keyPrefix: generated.keyPrefix,
      createdAt: generated.createdAt,
      lastUsedAt: generated.lastUsedAt,
      scopes: generated.scopes,
    );
  }

  wire.GeneratedDevApiKey toGenerated() {
    return wire.GeneratedDevApiKey(
      id: id,
      name: name,
      keyPrefix: keyPrefix,
      createdAt: createdAt,
      lastUsedAt: lastUsedAt,
      scopes: scopes,
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
    return DevApiKeyCreated.fromGenerated(wire.GeneratedDevApiKeyCreated.fromJson(json));
  }

  factory DevApiKeyCreated.fromGenerated(wire.GeneratedDevApiKeyCreated generated) {
    return DevApiKeyCreated(
      id: generated.id,
      name: generated.name,
      keyPrefix: generated.keyPrefix,
      createdAt: generated.createdAt,
      lastUsedAt: generated.lastUsedAt,
      scopes: generated.scopes,
      key: generated.key,
    );
  }

  wire.GeneratedDevApiKeyCreated toCreatedGenerated() {
    return wire.GeneratedDevApiKeyCreated(
      id: id,
      name: name,
      keyPrefix: keyPrefix,
      createdAt: createdAt,
      lastUsedAt: lastUsedAt,
      scopes: scopes,
      key: key,
    );
  }
}
