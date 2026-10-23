/// Share owner identity between read recovery and drawing. The canonical graph
/// reserves ID "user"; "user-node" and explicit type "user" are the existing
/// legacy presentation contract. Labels/profile names do not prove identity.
bool memoryGraphIsUserNode(Map<dynamic, dynamic> node) {
  final type = (node['node_type'] as String? ?? '').trim().toLowerCase();
  return node['id'] == 'user' || node['id'] == 'user-node' || type == 'user';
}

/// Prefer canonical identity even when an alias appears first (or the owner is
/// beyond the canvas bound). Stable legacy selection avoids response-order drift.
String memoryGraphPrimaryOwnerId(Iterable<dynamic> nodes) {
  final ids = nodes
      .whereType<Map>()
      .where(memoryGraphIsUserNode)
      .map((node) => node['id'])
      .whereType<String>()
      .where((id) => id.trim().isNotEmpty)
      .toSet();
  if (ids.contains('user')) return 'user';
  if (ids.contains('user-node')) return 'user-node';
  final legacyIds = ids.toList()..sort();
  return legacyIds.isEmpty ? 'user-node' : legacyIds.first;
}
