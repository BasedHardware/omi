/// Registered presentation experiments never select backend/product authority.
class ExperimentDefinition<T> {
  ExperimentDefinition({
    required this.key,
    required this.version,
    required Map<String, T> variants,
    required this.defaultVariant,
    required Set<String> namespaces,
    required Set<String> surfaces,
    required this.expiresAt,
    this.minimumBuild = 0,
    this.maximumBuild,
    this.layer,
    Set<String> holdoutVariants = const {},
    Map<bool, String> booleanVariants = const {},
  })  : variants = Map.unmodifiable(variants),
        namespaces = Set.unmodifiable(namespaces),
        surfaces = Set.unmodifiable(surfaces),
        holdoutVariants = Set.unmodifiable(holdoutVariants),
        booleanVariants = Map.unmodifiable(booleanVariants) {
    final identifier = RegExp(r'^[a-z][a-z0-9_-]{0,79}$');
    if (!identifier.hasMatch(key) ||
        version < 1 ||
        minimumBuild < 0 ||
        (maximumBuild != null && maximumBuild! < minimumBuild) ||
        variants.length < 2 ||
        !variants.containsKey(defaultVariant) ||
        namespaces.isEmpty ||
        surfaces.isEmpty ||
        [...variants.keys, ...surfaces, ...namespaces, if (layer != null) layer!].any((v) => !identifier.hasMatch(v)) ||
        !holdoutVariants.every(variants.containsKey) ||
        !booleanVariants.values.every(variants.containsKey)) {
      throw ArgumentError('Invalid experiment definition');
    }
  }

  final String key;
  final int version;
  final Map<String, T> variants;
  final String defaultVariant;
  final Set<String> namespaces;
  final Set<String> surfaces;
  final DateTime expiresAt;
  final int minimumBuild;
  final int? maximumBuild;

  /// A server multivariate flag `mobile-layer-<layer>` must select this key.
  /// The server, never client ordering or hashing, owns mutual exclusion.
  final String? layer;
  final Set<String> holdoutVariants;

  /// Explicit true/false mappings. False is a real control only when registered.
  final Map<bool, String> booleanVariants;

  String? variantKey(Object? value) => value is bool
      ? booleanVariants[value]
      : value is String
          ? value
          : null;
}

class ExperimentContext {
  const ExperimentContext(
      {required this.identityKey, required this.analyticsEnabled, required this.namespace, required this.appBuild});
  final String identityKey;
  final bool analyticsEnabled;
  final String namespace;
  final int appBuild;
}

class ExperimentFlagSnapshot {
  ExperimentFlagSnapshot(
      {required Map<String, Object> values,
      required this.fetchedAt,
      required this.identityKey,
      this.authoritative = true})
      : values = Map.unmodifiable(values);
  final Map<String, Object> values;
  final DateTime fetchedAt;
  final String identityKey;
  final bool authoritative;
}

abstract class ExperimentFlagProvider {
  Future<ExperimentFlagSnapshot> fetch(ExperimentContext context);
}
