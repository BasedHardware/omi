"""Guard production launch surfaces during the ordered structured-logging rollout.

The image registry owns declared modules; Docker COPY/CMD and Helm overrides are
checked independently so a new launch surface cannot evade that declaration.
"""

import argparse
import ast
from collections import Counter
import json
import io
import os
import posixpath
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Iterator, cast

import yaml

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.runtime_image_contracts import docker_target_instructions, dockerfile_shipped_by_github, load_contracts

ROOT = Path(__file__).resolve().parents[2]
PENDING = 'backend/logging_rollout_pending.json'
# These run infrastructure/test binaries, not production backend Python services.
NON_PRODUCTION = {
    'backend/testing/chaos-oom/Dockerfile.harness',
}


def launch_target(argv: list[str]) -> str:
    """Return a Python module or script; reject opaque application launchers."""
    if any(arg == '--app-dir' or arg.startswith('--app-dir=') for arg in argv):
        raise ValueError('Uvicorn --app-dir requires an explicit image contract; unsupported launch')
    args = list(argv)
    if not args:
        raise ValueError("empty application launcher")
    executable = PurePosixPath(args.pop(0)).name
    if executable in ('sh', 'bash') and args[:1] == ['-c']:
        lexer = shlex.shlex(args[1], posix=True, punctuation_chars=';&|')
        lexer.whitespace_split = True
        if '\n' in args[1]:
            raise ValueError('compound Docker shell launch is unsupported')
        tokens = list(lexer)
        if any(re.fullmatch(r'[;&|]+', token) for token in tokens):
            raise ValueError('compound Docker shell launch is unsupported')
        return launch_target(tokens[1:] if tokens[:1] == ['exec'] else tokens)
    if executable in ('python', 'python3'):
        if args[:1] == ['-m']:
            args = args[1:]
            if args[0] != 'uvicorn':
                return args[0]
            args = args[1:]
        elif args and args[0].endswith('.py'):
            return args[0]
        else:
            raise ValueError(f'unsupported Python launch: {argv}')
    elif executable != 'uvicorn':
        raise ValueError(f'unsupported application launcher: {argv}')
    if not args or ':' not in args[0]:
        raise ValueError(f'missing ASGI application: {argv}')
    return args[0].split(':')[0]


def docker_launch(path: Path, stage: str | None = None) -> tuple[PurePosixPath, str]:
    instructions = docker_target_instructions(path, stage)
    commands: dict[str, list[str]] = {}
    workdir = PurePosixPath('/')
    for line in instructions:
        op, _, value = line.partition(' ')
        if op.upper() == 'WORKDIR':
            workdir = workdir / value
        if op.upper() in ('CMD', 'ENTRYPOINT'):
            if not value.startswith('['):
                raise ValueError(f'{path}: shell-form Docker launch is unsupported; use exec form')
            commands[op.upper()] = json.loads(value)
    argv = commands.get('ENTRYPOINT', []) + commands.get('CMD', [])
    if not argv:
        raise ValueError(f'{path}: missing explicit launcher')
    return workdir, launch_target(argv)


def copied_source(
    dockerfile: Path, context: Path, workdir: PurePosixPath, runtime_path: PurePosixPath, stage: str | None = None
) -> Path | None:
    """Resolve one runtime file through COPY, honoring last-write precedence."""
    found = None
    current = PurePosixPath('/')
    for line in docker_target_instructions(dockerfile, stage):
        op, _, value = line.partition(' ')
        if op.upper() == 'WORKDIR':
            current = PurePosixPath(posixpath.normpath(str(current / value)))
        if op.upper() != 'COPY':
            continue
        if value.startswith('['):
            raise ValueError('JSON-form COPY needs explicit source-layout support')
        tokens = shlex.split(value)
        external = any(token.startswith('--from=') for token in tokens)
        tokens = [token for token in tokens if not token.startswith('--')]
        patterns, raw_destination = tokens[:-1], tokens[-1]
        destination = PurePosixPath(posixpath.normpath(str(current / raw_destination)))
        if external:
            if runtime_path == destination or runtime_path.is_relative_to(destination):
                raise ValueError(f'{dockerfile}: stage COPY may overwrite guarded path {runtime_path}')
            continue
        for pattern in patterns:
            matches = sorted(context.glob(pattern))
            for source in matches:
                target = destination
                if source.is_dir():
                    if runtime_path.is_relative_to(target):
                        candidate = source / runtime_path.relative_to(target)
                        if candidate.is_file():
                            found = candidate
                else:
                    if raw_destination.endswith('/') or raw_destination in ('.', './'):
                        target /= source.name
                    if runtime_path == target:
                        found = source

    return found


def source_path(dockerfile: Path, context: Path, workdir: PurePosixPath, target: str, stage: str | None = None) -> Path:
    relative = target if target.endswith('.py') else target.replace('.', '/') + '.py'
    runtime = workdir / relative
    source = copied_source(dockerfile, context, workdir, runtime, stage)
    if source is None and not target.endswith('.py'):
        source = copied_source(dockerfile, context, workdir, workdir / target.replace('.', '/') / '__main__.py', stage)
    if source is None:
        raise ValueError(f'{dockerfile.relative_to(ROOT)}: launch target {target} is not copied into image')
    return source


def source_violations(source: str) -> dict[str, int]:
    tree = ast.parse(source)
    violations: Counter[str] = Counter()

    class Calls(ast.NodeVisitor):
        def __init__(self) -> None:
            self.aliases: dict[str, str] = {'print': 'builtins.print'}
            self.configured = False
            self.class_parent: dict[str, str] | None = None

        def name(self, node: ast.expr) -> str:
            first, dot, rest = ast.unparse(node).partition('.')
            return self.aliases.get(first, first) + (dot + rest if dot else '')

        def visit_Import(self, node: ast.Import) -> None:
            self.aliases.update({a.asname or a.name: a.name for a in node.names})

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            self.aliases.update({a.asname or a.name: f'{node.module}.{a.name}' for a in node.names})

        def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self.aliases[node.name] = '<local>'
            outer, class_parent = self.aliases, self.class_parent
            self.aliases = dict(class_parent if class_parent is not None else outer)
            self.class_parent = None
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                self.aliases[argument.arg] = '<local>'
            self.generic_visit(node)
            self.aliases, self.class_parent = outer, class_parent

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.aliases[node.name] = '<local>'
            outer, previous = self.aliases, self.class_parent
            self.aliases, self.class_parent = dict(outer), outer
            self.generic_visit(node)
            self.aliases, self.class_parent = outer, previous

        def visit_Assign(self, node: ast.Assign) -> None:
            self.visit(node.value)
            resolved = self.name(node.value)
            if resolved.split('.')[0] not in ('builtins', 'logging', 'uvicorn', 'omi_logging'):
                resolved = '<local>'
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                        self.aliases[name.id] = resolved

        def visit_Call(self, node: ast.Call) -> None:
            name = self.name(node.func)
            if name == 'builtins.print':
                violations['print'] += 1
            if name == 'logging.basicConfig':
                violations['basicConfig'] += 1
            if name == 'uvicorn.run' and not any(
                k.arg == 'log_config' and isinstance(k.value, ast.Constant) and k.value.value is None
                for k in node.keywords
            ):
                violations['uvicorn_reconfigures'] += 1
            self.generic_visit(node)

    visitor = Calls()
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if visitor.name(node.value.func) == 'omi_logging.configure_logging':
                visitor.configured = True
        visitor.visit(node)
    if not visitor.configured:
        violations['missing_setup'] = 1
    return dict(violations)


def dockerfiles(root: Path) -> Iterator[Path]:
    for directory, dirs, files in os.walk(root / 'backend'):
        dirs[:] = [d for d in dirs if d not in ('.venv', '.openapi-venv', '__pycache__', '.git', '.pytest_cache')]
        for name in files:
            if name.startswith('Dockerfile'):
                yield Path(directory) / name


def inspect_configmap_chart(root: Path, chart: Path, binding: dict[str, str], target: str) -> dict[str, int]:
    """Validate mounted script provenance separately from built-image COPY provenance.

    Only literal ConfigMap Files.Get/mount wiring is supported. The shared stdlib
    module is a generated chart asset, checked byte-for-byte against its owner.
    """
    if target != binding['entrypoint']:
        raise ValueError(f'{chart}: unexpected ConfigMap entrypoint {target}')
    template = (chart / binding['template']).read_text()
    mount = str(PurePosixPath(target).parent)
    volume = re.escape(binding['volume'])
    if not re.search(rf'- name: {volume}\s+mountPath: {re.escape(mount)}\s+readOnly: true', template):
        raise ValueError(f'{chart}: script read-only volume mount missing')
    match = re.search(rf'- name: {volume}\s+configMap:\s+name: (.+)', template)
    if not match:
        raise ValueError(f'{chart}: script ConfigMap volume missing')
    configmap = next(
        (block for block in template.split('---') if 'kind: ConfigMap' in block and f"name: {match[1]}" in block), ''
    )
    for source, name in [(binding['source'], PurePosixPath(target).name), (binding['logging'], 'omi_logging.py')]:
        if not (chart / source).resolve().is_relative_to((chart / 'files').resolve()):
            raise ValueError(f'{chart}: ConfigMap source must be inside chart files')
        expected = f'  {name}: |\n' + '{{ .Files.Get "' + source + '" | indent 4 }}'
        if expected not in configmap:
            raise ValueError(f'{chart}: missing ConfigMap source binding for {name}')
    if (chart / binding['logging']).read_bytes() != (root / 'backend/omi_logging.py').read_bytes():
        raise ValueError(f'{chart}: shared omi_logging.py missing or shadowed; regenerate chart copy')
    return source_violations((chart / binding['source']).read_text())


def inventory(root: Path = ROOT) -> dict[str, dict[str, int]]:
    contracts = [c for c in load_contracts() if c.source_root.is_relative_to(root / 'backend')]
    by_docker: dict[Path, list[Any]] = {}
    for c in contracts:
        by_docker.setdefault(c.dockerfile, []).append(c)
    registry = json.loads((root / 'backend/runtime_images.json').read_text())
    bindings: dict[str, str] = registry['logging_chart_images']
    configmap_bindings = registry.get('logging_configmap_charts', {})
    # Non-Python images (the Rust listen-edge) log through their own runtime; the
    # registry records how, and this Python launch guard does not apply to them.
    native = {spec['dockerfile'] for spec in registry.get('native_images', {}).values()}
    by_name = {c.name: c for c in contracts}
    sources: dict[str, dict[str, int]] = {}

    def inspect(
        dockerfile: Path, context: Path, workdir: PurePosixPath, target: str, binding: str, stage: str | None = None
    ) -> None:
        source = source_path(dockerfile, context, workdir, target, stage)
        key = f'{source.relative_to(root).as_posix()}::{binding}'
        sources[key] = source_violations(source.read_text())
        if not sources[key].get('missing_setup'):
            shared = copied_source(dockerfile, context, workdir, workdir / 'omi_logging.py', stage)
            if shared != root / 'backend/omi_logging.py':
                raise ValueError(f'{dockerfile}: shared omi_logging.py missing or shadowed')

    for dockerfile in sorted(set(dockerfiles(root)) | set(by_docker)):
        if dockerfile.relative_to(root).as_posix() in NON_PRODUCTION | native:
            continue
        registered = by_docker.get(dockerfile, [])
        if (
            registered
            and all(getattr(c, 'build_only', False) for c in registered)
            and not dockerfile_shipped_by_github(dockerfile)
        ):
            # Build-only images (runtime_images.json) are built and probed but no
            # workflow or action references their Dockerfile, so they have no launch
            # surface yet. Marking a shipped image build_only does not hide it: the
            # Dockerfile reference keeps it inspected (and check-roles rejects it).
            continue
        # A multi-target Dockerfile launches one image per registered build stage.
        stages: list[str | None] = sorted({c.target for c in registered if getattr(c, 'target', None)})
        if not registered or any(getattr(c, 'target', None) is None for c in registered):
            stages.append(None)
        for stage in stages:
            stage_contracts = [c for c in registered if getattr(c, 'target', None) == stage]
            context = stage_contracts[0].build_context if stage_contracts else root
            workdir, target = docker_launch(dockerfile, stage)
            targets = {module for c in stage_contracts for module in c.entrypoints} | {target}
            label = dockerfile.relative_to(root).as_posix() + (f'@{stage}' if stage else '')
            for target in targets:
                inspect(dockerfile, context, workdir, target, f'docker:{label}:{target}', stage)
    # Helm overrides add application entrypoints independently of Docker CMD.
    for chart in (root / 'backend/charts').iterdir():
        if chart.name == 'monitoring' or not chart.is_dir():
            continue
        for path in sorted(set(chart.rglob('*.yaml')) | set(chart.rglob('*.yml'))):
            for position, target in enumerate(helm_targets(path.read_text())):
                if chart.name in configmap_bindings:
                    binding = configmap_bindings[chart.name]
                    if path != chart / binding['template']:
                        raise ValueError(f'{path}: ConfigMap launcher outside registered template')
                    key = f"{(chart / binding['source']).relative_to(root).as_posix()}::configmap:{target}"
                    sources[key] = inspect_configmap_chart(root, chart, binding, target)
                    continue
                if chart.name not in bindings or bindings[chart.name] not in by_name:
                    raise ValueError(f'{path}: Python launcher has no registered chart/image binding')
                contract = by_name[bindings[chart.name]]
                workdir, _ = docker_launch(contract.dockerfile, getattr(contract, 'target', None))
                inspect(
                    contract.dockerfile,
                    contract.build_context,
                    workdir,
                    target,
                    f'helm:{path.relative_to(root)}:{position}:{contract.name}:{target}',
                    getattr(contract, 'target', None),
                )
    return dict(sorted(sources.items()))


def helm_targets(text: str) -> Iterator[str]:
    """Read literal inline/block command+args, including shell Python launches.

    Templated commands are supplied by values files, which are scanned as well.
    Native probes/admin tools and Python -c diagnostics are not app modules.
    """
    lines = text.splitlines()
    parents: list[tuple[int, str]] = []
    argument_lines = {i for i, line in enumerate(lines) if re.match(r"^\s*(?:- )?args:", line)}
    resolved_arguments: set[int] = set()
    for index, line in enumerate(lines):
        key = re.match(r'^(\s*)(?:- )?([\w]+):', line)
        if key:
            depth = len(key[1])
            while parents and parents[-1][0] >= depth:
                parents.pop()
        match = re.match(r'^(\s*)(?:- )?command:\s*(.*)$', line)
        if not match:
            if key:
                parents.append((len(key[1]), key[2]))
            continue
        probe = any(
            name in ('initContainers', 'readinessProbe', 'livenessProbe', 'startupProbe', 'lifecycle')
            for _, name in parents
        )
        sequence = line.lstrip().startswith('- ')
        indent = len(match[1]) + (2 if sequence else 0)
        block = [line[indent:]]
        sibling_arguments: set[int] = set()
        for following_index, following in enumerate(lines[index + 1 :], index + 1):
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                if not following.lstrip().startswith(('args:', '- ')):
                    break
            if following_index in argument_lines and len(following) - len(following.lstrip()) == indent:
                sibling_arguments.add(following_index)
            block.append(following[indent:])
        fragment = '\n'.join(block)
        if match[2].lstrip().startswith('{{') or re.search(r'^\s*{{-?\s*toYaml', fragment, re.MULTILINE):
            if '.Values.command' not in fragment and not (
                index and re.search(r'with\s+\.Values\.command\s', lines[index - 1])
            ):
                raise ValueError('unsupported templated Helm command')
            continue  # toYaml .Values.command; its literal values are checked
        fragment = re.sub(r'{{.*?}}', 'template-value', fragment)
        data: dict[str, Any] = yaml.safe_load(fragment)
        argv = (data.get('command') or []) + (data.get('args') or [])
        if not isinstance(argv, list) or not all(isinstance(value, str) for value in argv):
            raise ValueError('Helm command/args must be literal string arrays')
        argv = cast(list[str], argv)
        resolved_arguments.update(sibling_arguments)
        if not argv:
            continue
        if PurePosixPath(argv[0]).name in ('sh', 'bash'):
            lexer = shlex.shlex(argv[-1], posix=True, punctuation_chars=';&|\n')
            lexer.whitespace = ' \t\r'
            lexer.whitespace_split = True
            candidates: list[list[str]] = [[]]
            for token in lexer:
                if re.fullmatch(r'[;&|\n]+', token):
                    candidates.append([])
                else:
                    candidates[-1].append(token)
            candidates = [c[1:] if c[:1] == ['exec'] else c for c in candidates if c]
        else:
            candidates = [argv]
        for candidate in candidates:
            if PurePosixPath(candidate[0]).name in ('python', 'python3', 'uvicorn'):
                if candidate[1:2] == ['-c'] and probe:
                    continue  # inline init/probe diagnostics, no application module
                yield launch_target(candidate)
            elif not probe and PurePosixPath(candidate[0]).name not in ('kubectl', 'curl', 'wget', 'sleep'):
                raise ValueError(f'unsupported Helm launcher: {candidate[0]}')

    if argument_lines - resolved_arguments:
        raise ValueError("unresolved Helm args override; place literal args directly after an explicit command")


def check_pending(
    actual: dict[str, dict[str, int]],
    pending: dict[str, dict[str, int]],
    previous: dict[str, dict[str, int]] | None = None,
) -> list[str]:
    errors: list[str] = []
    for path, violations in actual.items():
        allowed = pending.get(path, {})
        for kind, count in violations.items():
            if count > allowed.get(kind, 0):
                errors.append(f'{path}: {kind}={count} exceeds pending={allowed.get(kind, 0)}')
    for path, allowed in pending.items():
        if actual.get(path) != allowed:
            errors.append(f'{path}: remove or shrink stale pending entry to {actual.get(path)}')
        if previous is not None and any(n > previous.get(path, {}).get(k, 0) for k, n in allowed.items()):
            errors.append(f'{path}: rollout pending entries may only shrink')
    return errors


def previous_pending(base: str) -> dict[str, dict[str, int]]:
    subprocess.run(['git', 'rev-parse', '--verify', f'{base}^{{commit}}'], cwd=ROOT, check=True, capture_output=True)
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', base], cwd=ROOT, text=True).splitlines()
    if PENDING in names:
        return json.loads(subprocess.check_output(['git', 'show', f'{base}:{PENDING}'], cwd=ROOT, text=True))
    # Bootstrap the first guard from the base revision's actual production sources.
    # Only new guard metadata/code is overlaid; entrypoints and Dockerfiles stay at base.
    selected = [
        n
        for n in names
        if n.startswith(('backend/', 'plugins/', '.github/workflows/'))
        and (Path(n).suffix in ('.py', '.json', '.yaml', '.yml') or Path(n).name.startswith('Dockerfile'))
    ]
    archive = subprocess.check_output(['git', 'archive', base, '--', *selected], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='omi-logging-base-') as directory:
        root = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(root, filter='data')
        registry = root / 'backend/runtime_images.json'
        data = json.loads(registry.read_text())
        data['logging_chart_images'] = json.loads((ROOT / 'backend/runtime_images.json').read_text())[
            'logging_chart_images'
        ]
        registry.write_text(json.dumps(data))
        script = root / 'backend/scripts/check_logging_entrypoints.py'
        script.write_text(Path(__file__).read_text())
        return json.loads(
            subprocess.check_output([sys.executable, str(script), '--inventory-only'], cwd=root, text=True)
        )


def main() -> bool:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base')
    parser.add_argument('--inventory-only', action='store_true')
    args = parser.parse_args()
    pending: dict[str, dict[str, int]] = {}
    try:
        actual = inventory()
        if args.inventory_only:
            print(json.dumps(actual))
            return False
        pending = json.loads((ROOT / PENDING).read_text())
        previous = previous_pending(args.base) if args.base else None
        errors = check_pending(actual, pending, previous)
    except (ValueError, OSError, SyntaxError, subprocess.CalledProcessError) as error:
        errors = [str(error)]
    for error in errors:
        print(error)
    if not errors:
        print(f'Logging entrypoint guard passed; {len(pending)} ordered migrations remain.')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
