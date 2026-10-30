"""Independent documented Vertex structured-output contract for offline replays."""

# Vertex v1 GenerationConfig.response_json_schema's documented keyword set.
# Keep this independent of the converter so additions require a contract review.
SUPPORTED = {
    '$id',
    '$defs',
    '$ref',
    '$anchor',
    'type',
    'format',
    'title',
    'description',
    'enum',
    'items',
    'prefixItems',
    'minItems',
    'maxItems',
    'minimum',
    'maximum',
    'anyOf',
    'oneOf',
    'properties',
    'additionalProperties',
    'required',
    'propertyOrdering',
}


def assert_vertex_subset(node):
    assert isinstance(node, dict)
    assert set(node) <= SUPPORTED
    if 'enum' in node:
        assert all(isinstance(value, (str, int, float)) and not isinstance(value, bool) for value in node['enum'])
    properties = node.get('properties', {})
    if 'required' in node:
        assert len(node['required']) == len(set(node['required']))
        assert set(node['required']) <= set(properties)
    if 'propertyOrdering' in node:
        assert len(node['propertyOrdering']) == len(set(node['propertyOrdering']))
        assert set(node['propertyOrdering']) <= set(properties)
    if '$ref' in node:
        assert all(key.startswith('$') for key in node)
    for key in ('properties', '$defs'):
        for child in node.get(key, {}).values():
            assert_vertex_subset(child)
    for key in ('items', 'additionalProperties'):
        child = node.get(key)
        if isinstance(child, dict):
            assert_vertex_subset(child)
    for key in ('anyOf', 'oneOf', 'prefixItems'):
        for child in node.get(key, []):
            assert_vertex_subset(child)


def assert_local_references(schema):
    """Every canary ref resolves locally and its fully expanded graph is acyclic."""

    def walk(node, visiting=frozenset()):
        if '$ref' in node:
            ref = node['$ref']
            assert ref.startswith('#/') and ref not in visiting
            target = schema
            for part in ref[2:].split('/'):
                target = target[part.replace('~1', '/').replace('~0', '~')]
            walk(target, visiting | {ref})
        for key in ('properties', '$defs'):
            for child in node.get(key, {}).values():
                walk(child, visiting)
        for key in ('items', 'additionalProperties'):
            if isinstance(node.get(key), dict):
                walk(node[key], visiting)
        for key in ('anyOf', 'oneOf', 'prefixItems'):
            for child in node.get(key, []):
                walk(child, visiting)

    walk(schema)
