/// Reduced view of a backend `App` from `/v2/apps`. We only model the fields
/// the v0 grid actually renders — id/name/description/image and the install
/// signal — so the wire schema can grow without churning this file.
class NooApp {
  const NooApp({
    required this.id,
    required this.name,
    required this.description,
    required this.imageUrl,
    required this.enabled,
    required this.installs,
    required this.capabilities,
    this.author,
    this.ratingAvg,
    this.ratingCount,
  });

  final String id;
  final String name;
  final String description;
  final String imageUrl;
  final bool enabled;
  final int installs;
  final List<String> capabilities;
  final String? author;
  final double? ratingAvg;
  final int? ratingCount;

  factory NooApp.fromJson(Map<String, dynamic> json) {
    final caps = json['capabilities'];
    return NooApp(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      description: (json['description'] ?? '').toString(),
      imageUrl: (json['image'] ?? '').toString(),
      enabled: json['enabled'] as bool? ?? false,
      installs: (json['installs'] as num?)?.toInt() ?? 0,
      capabilities: caps is List
          ? caps.map((e) => e.toString()).toList(growable: false)
          : const <String>[],
      author: json['author'] as String?,
      ratingAvg: (json['rating_avg'] as num?)?.toDouble(),
      ratingCount: (json['rating_count'] as num?)?.toInt(),
    );
  }
}

/// One capability section in the Apps screen — e.g. "Popular", "Integrations".
/// `id` is the stable backend key; `title` is what we render.
class AppGroup {
  const AppGroup({required this.id, required this.title, required this.apps});

  final String id;
  final String title;
  final List<NooApp> apps;

  factory AppGroup.fromJson(Map<String, dynamic> json) {
    final cap = json['capability'] as Map?;
    final data = json['data'];
    return AppGroup(
      id: (cap?['id'] ?? '').toString(),
      title: (cap?['title'] ?? '').toString(),
      apps: data is List
          ? data
              .whereType<Map>()
              .map((m) => NooApp.fromJson(Map<String, dynamic>.from(m)))
              .toList(growable: false)
          : const <NooApp>[],
    );
  }
}
