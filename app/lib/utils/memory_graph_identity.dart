/// Backend owner labels and the given name identify the existing owner node.
/// Localized display fallbacks are excluded so concepts named "you" stay facts.
Set<String> memoryGraphKnownUserLabels(String givenName) {
  final name = givenName.trim().toLowerCase();
  return {'me', 'the user', if (name.isNotEmpty) name};
}

/// Share the same presentation identity test between read recovery and drawing.
bool memoryGraphIsUserNode(Map<dynamic, dynamic> node, Set<String> knownLabels) {
  final label = (node['label'] as String? ?? '').trim().toLowerCase();
  final type = (node['node_type'] as String? ?? '').trim().toLowerCase();
  return node['id'] == 'user-node' || knownLabels.contains(label) || type == 'user';
}
