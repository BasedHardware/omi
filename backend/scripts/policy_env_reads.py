"""Static input adapter for the immutable policy resolver and live-switch allowlist.

Deployment checks must see the same defaults after reads move behind policy
helpers. Parse source rather than importing application modules or running env.
"""

import ast


def policy_env_reads(source, module_paths):
    paths = set(module_paths)
    switches = {}
    allowlist = 'backend/config/policy/kill_switches.py'
    if allowlist in paths:
        for node in ast.parse(source.read(allowlist)).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'KILL_SWITCHES' for t in node.targets
            ):
                switches = ast.literal_eval(node.value)
    for rel in module_paths:
        for node in ast.walk(ast.parse(source.read(rel))):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            )
            args = node.args
            key, default, boolean = None, None, False
            if name == 'kill_switch' and args and isinstance(args[0], ast.Constant):
                key = args[0].value
                if key in switches:
                    default, boolean = str(switches[key]).lower(), True
                else:
                    continue
            elif rel in {'backend/config/policy/batch.py', 'backend/config/policy/stages.py'}:
                offset = {'enabled': 0, 'boolean': 1, 'cohort': 1, 'member': 3}.get(name)
                if offset is not None and len(args) > offset and isinstance(args[offset], ast.Constant):
                    key = args[offset].value
                    boolean = name in {'enabled', 'boolean'}
                    default = 'false' if boolean else ''
                    if boolean and len(args) > offset + 1 and isinstance(args[offset + 1], ast.Constant):
                        default = str(args[offset + 1].value)
                elif (
                    name == 'get'
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'env'
                ):
                    if args and isinstance(args[0], ast.Constant):
                        key = args[0].value
                        if len(args) > 1 and isinstance(args[1], ast.Constant):
                            default = str(args[1].value)
            if isinstance(key, str) and key.isupper():
                yield rel, key, default, boolean
