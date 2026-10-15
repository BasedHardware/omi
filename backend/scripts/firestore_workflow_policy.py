"""Parse Firestore reconciliation commands used by deployment policy checks."""

from __future__ import annotations

import json
import pathlib
import re
import shlex
from dataclasses import dataclass

import yaml

_YAML_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)

RECONCILE_SCRIPT = 'reconcile_firestore_indexes.py'
FIELD_EXEMPTION_SCRIPT = 'reconcile_firestore_field_exemptions.py'
FIRESTORE_SCHEMA_SCRIPTS = frozenset({RECONCILE_SCRIPT, FIELD_EXEMPTION_SCRIPT})
FIRESTORE_MUTATION_VERBS = frozenset({'create', 'delete', 'update'})


@dataclass(frozen=True)
class ReconciliationInvocation:
    tokens: tuple[str, ...]

    def option_values(self, option: str) -> tuple[str, ...]:
        values: list[str] = []
        for index, token in enumerate(self.tokens):
            if token == option and index + 1 < len(self.tokens):
                values.append(self.tokens[index + 1])
            elif token.startswith(f'{option}='):
                values.append(token.partition('=')[2])
        return tuple(values)

    @property
    def is_readiness_check(self) -> bool:
        return (
            '--check-only' in self.tokens
            and '--provision-missing' not in self.tokens
            and '--dry-run' not in self.tokens
            and len(self.option_values('--proposal-output')) == 1
            and len(self.option_values('--source-commit')) == 1
            and self.option_values('--proposal-ttl-seconds') == ('3600',)
        )

    @property
    def is_proposal_validation(self) -> bool:
        return (
            len(self.option_values('--validate-proposal')) == 1
            and len(self.option_values('--source-commit')) == 1
            and self.option_values('--proposal-ttl-seconds') == ('3600',)
            and '--check-only' not in self.tokens
            and '--provision-missing' not in self.tokens
            and '--dry-run' not in self.tokens
        )

    @property
    def mutates_schema(self) -> bool:
        if any(token.endswith(FIELD_EXEMPTION_SCRIPT) for token in self.tokens):
            return '--apply' in self.tokens
        return (
            '--check-only' not in self.tokens
            and '--dry-run' not in self.tokens
            and '--validate-proposal' not in self.tokens
        )

    @property
    def project_values(self) -> tuple[str, ...]:
        return self.option_values('--project')


def _logical_lines(run: str) -> tuple[str, ...]:
    """Join explicit shell continuations without extending comments across lines."""

    lines: list[str] = []
    pending = ''
    for raw_line in run.replace('\r\n', '\n').replace('\r', '\n').splitlines():
        if raw_line.endswith('\\'):
            pending += raw_line[:-1] + ' '
            continue
        lines.append(pending + raw_line)
        pending = ''
    if pending:
        lines.append(pending)
    return tuple(lines)


def _shell_commands(run: str) -> tuple[tuple[tuple[str, ...], ...], tuple[str, ...]]:
    commands: list[tuple[str, ...]] = []
    malformed_lines: list[str] = []
    for line in _logical_lines(run):
        lexer = shlex.shlex(line, posix=True, punctuation_chars=';&|')
        lexer.whitespace_split = True
        lexer.commenters = '#'
        try:
            tokens = list(lexer)
        except ValueError:
            malformed_lines.append(line)
            continue

        command: list[str] = []
        for token in tokens:
            if token and all(character in ';&|' for character in token):
                if command:
                    commands.append(tuple(command))
                    command = []
                continue
            command.append(token)
        if command:
            commands.append(tuple(command))
    return tuple(commands), tuple(malformed_lines)


def reconciliation_invocations(run: str) -> tuple[ReconciliationInvocation, ...]:
    """Return each shell command that invokes the reconciliation script."""

    commands, malformed_lines = _shell_commands(run)
    invocations = [
        ReconciliationInvocation(tokens)
        for tokens in commands
        if any(token.endswith(tuple(FIRESTORE_SCHEMA_SCRIPTS)) for token in tokens)
    ]
    invocations.extend(
        ReconciliationInvocation((script,))
        for line in malformed_lines
        for script in FIRESTORE_SCHEMA_SCRIPTS
        if script in line
    )
    return tuple(invocations)


def _command_name(token: str) -> str:
    return token.replace('\\', '/').rsplit('/', 1)[-1].removesuffix('.cmd').removesuffix('.exe').lower()


def _firebase_deploy_mutates_firestore(tokens: tuple[str, ...]) -> bool:
    normalized = tuple(_command_name(token) for token in tokens)
    for firebase_index, name in enumerate(normalized):
        if name not in {'firebase', 'firebase-tools'} and not name.startswith(('firebase@', 'firebase-tools@')):
            continue
        try:
            deploy_index = normalized.index('deploy', firebase_index + 1)
        except ValueError:
            continue

        only_targets: list[str] = []
        has_only_flag = False
        deploy_tokens = tokens[deploy_index + 1 :]
        for index, token in enumerate(deploy_tokens):
            if token == '--only':
                has_only_flag = True
                if index + 1 >= len(deploy_tokens):
                    return True
                only_targets.extend(deploy_tokens[index + 1].lower().split(','))
            elif token.startswith('--only='):
                has_only_flag = True
                only_targets.extend(token.partition('=')[2].lower().split(','))

        if not has_only_flag:
            return True
        if any(target == 'firestore' or target.startswith('firestore:') for target in only_targets):
            return True
    return False


def _gcloud_index_mutation(tokens: tuple[str, ...]) -> bool:
    normalized = tuple(_command_name(token) for token in tokens)
    for gcloud_index, name in enumerate(normalized):
        if name != 'gcloud':
            continue
        try:
            firestore_index = normalized.index('firestore', gcloud_index + 1)
            indexes_index = normalized.index('indexes', firestore_index + 1)
        except ValueError:
            continue
        if any(token in FIRESTORE_MUTATION_VERBS for token in normalized[indexes_index + 1 :]):
            return True
    return False


def has_direct_firestore_mutation(run: str) -> bool:
    """Return whether active shell commands directly mutate Firestore indexes."""

    commands, malformed_lines = _shell_commands(run)
    candidates = [*commands, *(tuple(line.split()) for line in malformed_lines)]
    return any(_firebase_deploy_mutates_firestore(tokens) or _gcloud_index_mutation(tokens) for tokens in candidates)


READINESS_ACTION = './.github/firestore-workflow/.github/actions/firestore-readiness'
READINESS_CONTROL_PATH = '.github/firestore-workflow'
READINESS_CONTROL_REF = '${{ github.workflow_sha }}'
READINESS_CREDENTIALS = '${{ secrets.GCP_FIRESTORE_READONLY_CREDENTIALS }}'
RUNTIME_PROJECT_INPUT = '${{ vars.RUNTIME_GCP_PROJECT_ID }}'
QA_PROJECT_INPUT = '${{ env.QA_PROJECT }}'
QA_DATABASE_INPUT = '${{ env.QA_FIRESTORE_DATABASE }}'
DEPLOY_ENVIRONMENT = re.compile(
    r"^\$\{\{\s*github\.event\.inputs\.environment\s*==\s*'prod'\s*&&\s*'prod'\s*\|\|\s*'development'\s*\}\}$"
)

NON_FIRESTORE_IMAGE_EXCLUSIONS = {
    'models': 'Modal GPU inference image serves VAD only and queries no Firestore collections',
    'diarizer': 'speaker embedding service with its own source root; queries no Firestore collections',
    'parakeet': 'self-hosted STT service with its own source root; queries no Firestore collections',
    'nllb-translation': 'self-hosted translation service with its own source root; queries no Firestore collections',
    'plugins': 'built from the plugins tree, not backend source',
    'typesense-jit-qa': 'JIT QA repins the upstream Typesense image; it carries no backend query code',
}
NON_BACKEND_DOCKERFILE_EXCLUSIONS = {
    'backend/Dockerfile.jit_qa_typesense': 'JIT QA repins the upstream Typesense image',
    'backend/modal/Dockerfile.finops_unit_cost_job': (
        'batch unit-cost job reads Firestore as a pull input and does not serve a Firestore-backed API'
    ),
}
SERVICE_IMAGE_NAMES = {
    'backend': 'backend',
    'backend-listen': 'backend',
    'backend-sync': 'backend',
    'backend-sync-backfill': 'backend',
    'backend-integration': 'backend',
    'llm-gateway': 'backend',
    'sync-ledger-drain': 'knowledge-ledger-drain-job',
}

_DOCKERFILE_FLAG = re.compile(r'(?:--file|--dockerfile|-f|file:)\s*=?["\']?([^\s"\']*Dockerfile[^\s"\']*)')
_GCR_IMAGE = re.compile(r'gcr\.io/[A-Za-z0-9_.${} /-]+?/([A-Za-z0-9_-]+)(?=[@:\s]|$)')
# The two project-segment alternatives are disjoint (a `${{` opener can only be
# consumed by the expression branch), so the match cannot backtrack exponentially.
_GCR_REPO = re.compile(r"gcr\.io/(?:\$\{\{[^}]*\}\}|\$(?!\{\{)|[^\s:/'\"$])+?/([A-Za-z0-9_-]+)")
_GCR_HOST = re.compile(r'(?<![\w.-])gcr\.io/')
_RUN_DEPLOY = re.compile(r'gcloud\s+run\s+(?:deploy|jobs\s+(?:deploy|update))\s+["\']?([^\s"\']+)')
_HELM_MUTATION = re.compile(r'\bhelm\s+(?:upgrade|rollback)\b')
_RUN_SERVICES_UPDATE = re.compile(r'gcloud\s+run\s+services\s+update\s')
# sync_ledger_fence_cutover.py stage/activate only consumes a backend image that
# was already built by a gated builder (operator backend-image contract; the
# generic @sha256 digest check does not enforce the repository). The named
# cutover workflow is the only file allowed to invoke it without its own gate;
# any other workflow doing so produces an uncovered 'backend' shipment.
_CUTOVER = re.compile(r'sync_ledger_fence_cutover\.py\s+(?:stage|activate)')
_CUTOVER_WORKFLOW = 'sync_ledger_fence_cutover.yml'
_LISTEN_REPLAY = re.compile(r'BACKEND_LISTEN_IMAGE_TAG|\brollback\b')
_LISTEN_MUTATION_RUN = re.compile(
    r'deploy-backend-config\.sh|deploy-backend-secrets\.sh|\bhelm\s+(?:upgrade|rollback)\b'
)
_LISTEN_SELECT_STEP = 'Resolve backend-listen image tag'
_LISTEN_DEPLOY_IF = "${{ (github.event.inputs.mode || 'deploy') == 'deploy' }}"
_DOCKER_PUSH = re.compile(r'\b(?:docker|podman)\s+push\s+([^\s;&|]+)')
_DOCKER_BUILD = re.compile(r'\b(?:docker|podman)\s+(?:buildx\s+)?build\b')
_SHELL_IF = re.compile(
    r'if\s+\[{1,2}\s+"?\$([A-Za-z_][A-Za-z0-9_]*)"?\s*(={1,2}|!=)\s*["\']?([^"\'\]]+?)["\']?\s*\]{1,2}'
)
_ENV_ASSIGNMENT = re.compile(
    r"(?m)^\s*(?:export\s+|local\s+|declare\s+)?([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^\s]+)"
)
_GITHUB_ENV_WRITE = re.compile(r'>>\s*"?\$?\{?GITHUB_ENV\}?')
_ATOM_DETAIL = re.compile(r"([A-Za-z_][A-Za-z0-9_.\-]*)\s*(==|!=)\s*(?:'([^']*)'|([A-Za-z0-9_.]+)(?![A-Za-z0-9_.(]))")
_EXPR_ATOM = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-]*\s*(?:==|!=)\s*(?:'[^']*'|[A-Za-z0-9_.]+(?![A-Za-z0-9_.(]))")
_KNOWN_NAME_BOUNDARY = r'(?<![A-Za-z0-9_-]){}(?![A-Za-z0-9_-])'

# gcp_backend_listen_helm.yml gates only the explicit-tag deploy path: kept and
# rollback lanes redeploy an image already served in the same environment, and
# the index pipeline is create-only, so its readiness gate is conditioned on
# env.BACKEND_LISTEN_SOURCE_SHA != '' and rollback gains no new failure mode.
LISTEN_WORKFLOW = 'gcp_backend_listen_helm.yml'
_LISTEN_SOURCE_ATOM = ('env.BACKEND_LISTEN_SOURCE_SHA', '!=', '')
_SUPPORTED_GATE_ATOMS = frozenset(
    {
        ('steps.admitted_source.outputs.superseded', '!=', 'true'),
        ('inputs.mode', '==', 'prove'),
        _LISTEN_SOURCE_ATOM,
    }
)
_UNSUPPORTED_SCOPE = frozenset({('@unsupported', '==', '@')})
_UNBOUND_IMAGE = '__unbound__'

_BUILD_VALUE_FLAGS = frozenset(
    (
        '--build-arg --platform --target --label --cache-from --cache-to --add-host --network '
        '--memory --shm-size --output -o --secret --ssh --ulimit --iidfile --progress --builder '
        '--attest --provenance --sbom --pull --load -c'
    ).split()
)


def _runtime_images(root):
    registry = json.loads((root / 'backend' / 'runtime_images.json').read_text(encoding='utf-8'))
    dockerfiles: dict[str, set[str]] = {}
    for image in registry['images']:
        dockerfiles.setdefault(image['dockerfile'], set()).add(image['name'])
    return dockerfiles


def _yaml_document(text):
    return yaml.load(text, Loader=_YAML_LOADER)


def _known_image_names(dockerfiles: dict[str, set[str]]) -> frozenset[str]:
    names: set[str] = set(NON_FIRESTORE_IMAGE_EXCLUSIONS) | set(SERVICE_IMAGE_NAMES)
    for images in dockerfiles.values():
        names.update(images)
    return frozenset(names)


def _step_env(document: dict, job: dict, step: dict, run: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for layer in (document.get('env'), job.get('env'), step.get('env')):
        if isinstance(layer, dict):
            env.update({str(key): str(value) for key, value in layer.items()})
    for match in _ENV_ASSIGNMENT.finditer(run):
        env.setdefault(match.group(1), match.group(2).strip('"\''))
    return env


def _substitute(text: str, env: dict[str, str]) -> str:
    def replace(match):
        name = match.group(1) or match.group(2) or match.group(3)
        value = env.get(name)
        if value is None or '${{' in value:
            return match.group(0)
        return value

    pattern = re.compile(
        r'\$\{\{\s*(?:env|vars)\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}'
        r'|\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)'
    )
    resolved = text
    for _pass in range(5):
        updated = pattern.sub(replace, resolved)
        if updated == resolved:
            break
        resolved = updated
    return resolved


def _resolve_name(raw: str, known: frozenset[str]) -> frozenset[str]:
    candidates: set[str] = set()
    for name in known:
        if re.search(_KNOWN_NAME_BOUNDARY.format(re.escape(name)), raw):
            candidates.add(name)
    return frozenset(candidates)


def _names_in_text(text: str, known: frozenset[str]) -> frozenset[str]:
    names: set[str] = set()
    for match in _GCR_IMAGE.finditer(text):
        names.update(_resolve_name(match.group(1), known))
    for match in _RUN_DEPLOY.finditer(text):
        names.update(_resolve_name(match.group(1), known))
    return frozenset(names)


def _norm_path(path: str) -> str:
    normalized = path.replace('\\', '/')
    parts: list[str] = []
    for part in normalized.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return '/'.join(parts) or '.'


def _dockerfile_names(dockerfile: str, dockerfiles: dict[str, set[str]]):
    normalized = _norm_path(dockerfile)
    if normalized in dockerfiles:
        return frozenset(dockerfiles[normalized]), False, None
    if normalized in NON_BACKEND_DOCKERFILE_EXCLUSIONS:
        return frozenset(), True, None
    if normalized.startswith('backend/'):
        return frozenset(), False, normalized
    return frozenset(), False, None


def _attribute(fragment: str, dockerfiles: dict[str, set[str]], known: frozenset[str]):
    included: set[str] = set()
    excluded: set[str] = set()
    unregistered: list[str] = []
    for dockerfile in _DOCKERFILE_FLAG.findall(fragment):
        names, is_excluded, bad = _dockerfile_names(dockerfile, dockerfiles)
        included.update(names)
        if is_excluded:
            excluded.add(_norm_path(dockerfile))
        if bad:
            unregistered.append(bad)
    for name in _names_in_text(fragment, known):
        mapped = SERVICE_IMAGE_NAMES.get(name, name)
        if mapped in NON_FIRESTORE_IMAGE_EXCLUSIONS:
            excluded.add(mapped)
        elif mapped:
            included.add(mapped)
    if _CUTOVER.search(fragment):
        included.add('backend')
    return frozenset(included), frozenset(excluded), unregistered


def _condition_atoms(expression, *, allow_or=False):
    """Return (atoms, supported) where atoms are (expr, op, literal) tuples.

    Strict mode rejects disjunction and negation: a gate or control checkout is
    only provably bound by a conjunction of supported atoms. allow_or is used
    for dependency approval, where top-level alternatives are checked
    individually by _dependency_allows instead.
    """

    raw = str(expression).strip()
    wrapper = re.fullmatch(r'\$\{\{(.*)\}\}', raw, re.DOTALL)
    if wrapper:
        raw = wrapper.group(1).strip()
    if not raw:
        return frozenset(), True
    residual = re.sub(r'\bsuccess\(\)', ' ', raw)
    if not allow_or and ('||' in residual or re.search(r'!(?!=)', residual)):
        return frozenset(), False
    atoms = frozenset(
        (match.group(1), match.group(2), match.group(3) if match.group(3) is not None else match.group(4))
        for match in _ATOM_DETAIL.finditer(residual)
    )
    leftover = _EXPR_ATOM.sub(' ', residual)
    leftover = re.sub(r'\b(?:always|failure|cancelled)\(\)', ' ', leftover)
    leftover = re.sub(r'&&|\|\||[()]', ' ', leftover)
    if not allow_or:
        leftover = re.sub(r'!(?!=)', '', leftover)
    if leftover.strip():
        return frozenset(), False
    return atoms, True


def _gate_scope(step: dict):
    """Return the gate's canonical condition atoms, or None when unsupported."""

    condition = step.get('if')
    if condition is None:
        return frozenset()
    if re.search(r'\b(?:always|failure|cancelled)\(\)', str(condition)):
        return None
    atoms, supported = _condition_atoms(condition)
    if not supported or not atoms <= _SUPPORTED_GATE_ATOMS:
        return None
    return atoms


def _scope_for(step: dict, shell_scope):
    atoms: set = set()
    for condition in (step.get('if'), *step.get('__ifs__', ())):
        if condition is None:
            continue
        parsed, supported = _condition_atoms(condition)
        if not supported:
            return _UNSUPPORTED_SCOPE
        atoms |= parsed
    if shell_scope is not None:
        atoms |= shell_scope
    return frozenset(atoms)


def _scope_blocks(run: str, env: dict[str, str]) -> list[tuple[int, int, frozenset]]:
    blocks: list[tuple[int, int, frozenset]] = []
    for match in _SHELL_IF.finditer(run):
        variable, operator, literal = match.group(1), match.group(2), match.group(3).strip()
        end_match = re.search(r'\bfi\b', run[match.end() :])
        if end_match is None:
            continue
        end = match.end() + end_match.start()
        bound = env.get(variable, '')
        expr = re.search(r'\$\{\{\s*([A-Za-z_.]+)\s*\}\}', bound)
        source = expr.group(1) if expr else f'env.{variable}'
        op = '!=' if operator == '!=' else '=='
        blocks.append((match.start(), end + 2, frozenset({(source, op, literal)})))
    return blocks


def _scope_at(position: int, scopes) -> frozenset | None:
    for start, end, key in scopes:
        if start < position < end:
            return key
    return None


_COMMAND_BOUNDARY = re.compile(r'&&|\|\||[;|]|(?<!\\)\n')


def _command_fragment(text: str, position: int) -> str:
    start = 0
    end = len(text)
    for boundary in _COMMAND_BOUNDARY.finditer(text):
        if boundary.end() <= position:
            start = boundary.end()
        if boundary.start() >= position:
            end = boundary.start()
            break
    return text[start:end]


def _working_directory(document: dict, job: dict, step: dict) -> str:
    layers = (step, (job.get('defaults') or {}).get('run'), (document.get('defaults') or {}).get('run'))
    for layer in layers:
        if isinstance(layer, dict) and layer.get('working-directory'):
            return str(layer['working-directory'])
    return ''


def _var_reference(token: str) -> str | None:
    match = re.fullmatch(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?', token.strip().strip('"\''))
    return match.group(1) if match else None


def _parse_docker_build(fragment: str, workdir: str):
    """Return (dockerfile, tags, pushed) for a docker build command fragment."""

    try:
        tokens = shlex.split(fragment)
    except ValueError:
        tokens = fragment.split()
    try:
        build_index = next(i for i, t in enumerate(tokens) if t == 'build')
    except StopIteration:
        return None
    tags: list[str] = []
    file_ref = ''
    pushed = False
    positionals: list[str] = []
    index = build_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token == '--push':
            pushed = True
        elif token in ('-f', '--file', '--dockerfile'):
            if index + 1 < len(tokens):
                file_ref = tokens[index + 1]
            index += 1
        elif token.startswith(('--file=', '--dockerfile=')):
            file_ref = token.partition('=')[2]
        elif token in ('-t', '--tag'):
            if index + 1 < len(tokens):
                tags.append(tokens[index + 1])
            index += 1
        elif token.startswith('--tag='):
            tags.append(token.partition('=')[2])
        elif token in _BUILD_VALUE_FLAGS:
            index += 1
        elif token.startswith('-'):
            pass
        else:
            positionals.append(token)
        index += 1
    context = positionals[-1] if positionals else '.'
    if file_ref:
        dockerfile = _norm_path('/'.join(part for part in (workdir, file_ref) if part))
    else:
        dockerfile = _norm_path('/'.join(part for part in (workdir, context, 'Dockerfile') if part))
    return dockerfile, tuple(tags), pushed


def _dockerfile_for_action(with_block: dict) -> str:
    file_ref = str(with_block.get('file', '') or '')
    if file_ref:
        return _norm_path(file_ref)
    return _norm_path(f"{with_block.get('context', '') or ''}/Dockerfile")


def _step_shipments(
    step: dict,
    document: dict,
    job: dict,
    dockerfiles: dict[str, set[str]],
    known: frozenset[str],
    job_state: dict,
    workflow_name: str = '',
):
    """Return (shipments, unregistered, published); job_state carries tag provenance across steps."""

    run = step.get('run') or ''
    with_block = step.get('with') or {}
    uses = str(step.get('uses', ''))
    run_text = run if isinstance(run, str) else ''
    env = _step_env(document, job, step, run_text)
    env.update(job_state['env'])
    unregistered: list[str] = []
    published: set[str] = set()
    shipments: list[tuple[frozenset, frozenset[str]]] = []
    workdir = _norm_path(_working_directory(document, job, step)) if _working_directory(document, job, step) else ''

    if uses.startswith('docker/build-push-action'):
        push = str(with_block.get('push', '')).strip().lower()
        cache_to = str(with_block.get('cache-to', ''))
        dockerfile = _dockerfile_for_action(with_block)
        names, is_excluded, bad = _dockerfile_names(dockerfile, dockerfiles)
        if bad:
            unregistered.append(bad)
        tag_names = _names_in_text(_substitute(str(with_block.get('tags', '')), env), known)
        names = frozenset(set(names) | set(tag_names))
        if push == 'true' or 'type=registry' in cache_to:
            shipments.append((_scope_for(step, None), frozenset() if is_excluded else names))
            for match in _GCR_REPO.finditer(_substitute(str(with_block.get('tags', '')), env)):
                published.add(match.group(1))
            cache_ref = _GCR_REPO.search(_substitute(cache_to, env))
            if cache_ref:
                published.add(cache_ref.group(1))

    if uses.startswith('google-github-actions/deploy-cloudrun'):
        image = _substitute(str(with_block.get('image', '') or ''), env)
        target = _substitute(str(with_block.get('service', '') or with_block.get('job', '') or ''), env)
        inc, exc, unreg = _attribute(f'{image} {target}', dockerfiles, known)
        unregistered.extend(unreg)
        deploy_names = set(inc) - set(exc)
        if not deploy_names and not exc and job_state['built_firestore']:
            deploy_names = {_UNBOUND_IMAGE}
        if deploy_names:
            shipments.append((_scope_for(step, None), frozenset(deploy_names)))

    if not run_text:
        return shipments, unregistered, published

    resolved = _substitute(run_text, env)
    scopes = _scope_blocks(resolved, env)

    for match in _ENV_ASSIGNMENT.finditer(resolved):
        name, value = match.group(1), match.group(2).strip('"\'')
        names_in_value = _names_in_text(value, known)
        if names_in_value or _GCR_HOST.search(value):
            excluded_only = names_in_value and names_in_value <= set(NON_FIRESTORE_IMAGE_EXCLUSIONS)
            job_state['var_images'][name] = (frozenset(names_in_value), bool(excluded_only))
            line_end = resolved.find('\n', match.end())
            line_tail = resolved[match.end() : line_end if line_end >= 0 else len(resolved)]
            if _GITHUB_ENV_WRITE.search(line_tail):
                job_state['env'][name] = value

    def scope_at(position):
        return _scope_for(step, _scope_at(position, scopes))

    for match in _DOCKER_BUILD.finditer(resolved):
        fragment = _command_fragment(resolved, match.start())
        parsed = _parse_docker_build(fragment, workdir)
        if parsed is None:
            continue
        dockerfile, tags, pushed = parsed
        names, is_excluded, bad = _dockerfile_names(dockerfile, dockerfiles)
        if bad:
            unregistered.append(bad)
        if names - set(NON_FIRESTORE_IMAGE_EXCLUSIONS):
            job_state['built_firestore'] = True
        build_names = frozenset() if is_excluded else names
        for tag in tags:
            tag_names = _names_in_text(tag, known)
            merged = frozenset(set(build_names) | set(tag_names))
            var = _var_reference(tag)
            if var:
                job_state['var_images'][var] = (merged, is_excluded)
            else:
                job_state['tag_images'][tag.strip('"\'')] = (merged, is_excluded)
        if pushed and not is_excluded:
            shipments.append((scope_at(match.start()), build_names))
            for tag in tags:
                for repo_match in _GCR_REPO.finditer(_substitute(tag, env)):
                    published.add(repo_match.group(1))

    for match in _DOCKER_PUSH.finditer(resolved):
        fragment = _command_fragment(resolved, match.start())
        arg = match.group(1).strip('"\'')
        var = _var_reference(arg)
        for repo_match in _GCR_REPO.finditer(env.get(var, '') if var else _substitute(arg, env)):
            published.add(repo_match.group(1))
        if var and var in job_state['var_images']:
            names, is_excluded = job_state['var_images'][var]
            if is_excluded:
                continue
            if not names and job_state['built_firestore']:
                names = {_UNBOUND_IMAGE}
            shipments.append((scope_at(match.start()), frozenset(names)))
            continue
        if var is None and arg in job_state['tag_images']:
            names, is_excluded = job_state['tag_images'][arg]
            if is_excluded:
                continue
            if not names and job_state['built_firestore']:
                names = {_UNBOUND_IMAGE}
            shipments.append((scope_at(match.start()), frozenset(names)))
            continue
        inc, exc, unreg = _attribute(fragment, dockerfiles, known)
        unregistered.extend(unreg)
        names = inc - exc
        if not names:
            if exc:
                continue
            if var or '$' in arg:
                names = {_UNBOUND_IMAGE} if job_state['built_firestore'] else set()
                if not names:
                    names = set(_names_in_text(fragment, known))
            elif job_state['built_firestore']:
                names = {_UNBOUND_IMAGE}
        shipments.append((scope_at(match.start()), frozenset(names)))

    for pattern in (_RUN_DEPLOY, _HELM_MUTATION, _CUTOVER, _RUN_SERVICES_UPDATE):
        for match in pattern.finditer(resolved):
            if pattern is _CUTOVER and workflow_name == _CUTOVER_WORKFLOW:
                continue
            fragment = _command_fragment(resolved, match.start())
            if workflow_name == LISTEN_WORKFLOW and pattern is _HELM_MUTATION and _LISTEN_REPLAY.search(fragment):
                # backend-listen's kept/rollback lanes replay an image already
                # served in the same environment; only its explicit-tag path
                # resolves a new source SHA, and the conditional gate covers it.
                continue
            if pattern is _RUN_SERVICES_UPDATE and '--image' not in fragment:
                continue
            inc, exc, unreg = _attribute(fragment, dockerfiles, known)
            unregistered.extend(unreg)
            names = inc - exc
            if not names:
                if exc:
                    continue
                if job_state['built_firestore']:
                    names = {_UNBOUND_IMAGE}
            shipments.append((scope_at(match.start()), frozenset(names)))

    return shipments, unregistered, published


def _environment_ok(environment) -> bool:
    if isinstance(environment, dict):
        environment = environment.get('name', '')
    value = str(environment).strip()
    return value in {'prod', 'development'} or bool(DEPLOY_ENVIRONMENT.fullmatch(value))


def _checkout_is_control(step: dict) -> bool:
    with_block = step.get('with') or {}
    return (
        str(step.get('uses', '')).startswith('actions/checkout@')
        and str(with_block.get('ref', '')) == READINESS_CONTROL_REF
        and str(with_block.get('path', '')) == READINESS_CONTROL_PATH
        and str(with_block.get('persist-credentials', '')).strip().lower() == 'false'
    )


def _checkout_erases_controls(step: dict) -> bool:
    if not str(step.get('uses', '')).startswith('actions/checkout@'):
        return False
    return str((step.get('with') or {}).get('path', '')).strip() in {'', '.', './'}


def _continue_on_error(value) -> bool:
    return value not in (None, False) and str(value).strip().lower() not in {'', 'false'}


def _condition_enabled(step: dict) -> bool:
    if _continue_on_error(step.get('continue-on-error')):
        return False
    condition = step.get('if')
    return condition is None or re.sub(r'\$\{\{|\}\}|\'|"|\s', '', str(condition)) != 'false'


def _gate_errors(step: dict, expanded: list[dict], index: int, job: dict, job_id: str, name: str) -> list[str]:
    errors: list[str] = []
    if str(step.get('uses', '')) != READINESS_ACTION:
        errors.append('readiness gate must use ./.github/firestore-workflow/.github/actions/firestore-readiness')
    if not _condition_enabled(step):
        errors.append('readiness gate must not be disabled or tolerated')
    if _continue_on_error(job.get('continue-on-error')):
        errors.append('readiness gate job must not be continue-on-error')
    is_listen = pathlib.Path(name).name == LISTEN_WORKFLOW
    gate_key = _gate_scope(step)
    if gate_key is None:
        errors.append('readiness gate condition must be unconditional or a supported lane predicate')
    elif _LISTEN_SOURCE_ATOM in gate_key and not is_listen:
        errors.append('env.BACKEND_LISTEN_SOURCE_SHA gating is only valid in gcp_backend_listen_helm.yml')
    if is_listen and gate_key != frozenset({_LISTEN_SOURCE_ATOM}):
        errors.append('listen readiness gate must be conditioned on env.BACKEND_LISTEN_SOURCE_SHA != \'\'')
    with_block = step.get('with') or {}
    source_sha = str(with_block.get('source_sha', ''))
    if not source_sha:
        errors.append('readiness gate requires a source_sha input')
    elif 'github.workflow_sha' in source_sha:
        errors.append('readiness gate source_sha must be the deployed source, not the workflow commit')
    elif not (re.fullmatch(r'[0-9a-f]{40}', source_sha) or 'sha' in source_sha.lower()):
        errors.append('readiness gate source_sha must resolve to a full source commit SHA')
    if str(with_block.get('credentials_json', '')) != READINESS_CREDENTIALS:
        errors.append('readiness gate must receive secrets.GCP_FIRESTORE_READONLY_CREDENTIALS')
    project = str(with_block.get('project_id', ''))
    database = str(with_block.get('database', ''))
    if project == RUNTIME_PROJECT_INPUT:
        if database and database != '(default)':
            errors.append('readiness gate on the runtime project must use the (default) database')
    elif project == QA_PROJECT_INPUT:
        if database != QA_DATABASE_INPUT:
            errors.append('QA readiness gate must set database: ${{ env.QA_FIRESTORE_DATABASE }}')
    else:
        errors.append('readiness gate project_id must be vars.RUNTIME_GCP_PROJECT_ID or env.QA_PROJECT')
    if is_listen and source_sha != '${{ env.BACKEND_LISTEN_SOURCE_SHA }}':
        errors.append('listen readiness gate source_sha must be env.BACKEND_LISTEN_SOURCE_SHA')
    if not _environment_ok(job.get('environment')):
        errors.append('readiness gate must run inside a prod/development deployment environment')

    control_index = -1
    for earlier_index, earlier in enumerate(expanded[:index]):
        if _checkout_is_control(earlier):
            control_index = earlier_index
            control_condition = earlier.get('if')
            control_atoms = None
            if control_condition is not None:
                control_atoms, ok = _condition_atoms(control_condition)
                if not ok or control_atoms - (gate_key or frozenset()):
                    errors.append('control checkout must share the gate condition or be unconditional')
            if is_listen and control_atoms != gate_key:
                errors.append(
                    "listen control checkout must carry exactly the env.BACKEND_LISTEN_SOURCE_SHA != '' condition"
                )
            if not _condition_enabled(earlier):
                errors.append('control checkout must not be disabled or tolerated')
    if control_index < 0:
        errors.append(
            'readiness gate requires an earlier actions/checkout staging .github/firestore-workflow at github.workflow_sha'
        )
    else:
        for between in expanded[control_index + 1 : index]:
            if _checkout_erases_controls(between):
                errors.append('a later root actions/checkout before the gate erases the staged controls')
                break
    return errors


def _job_needs(job: dict) -> set[str]:
    needs = job.get('needs')
    items = needs if isinstance(needs, list) else [needs]
    return {str(item) for item in items if isinstance(item, str)}


_INPUT_REF = re.compile(r'\$\{\{\s*inputs\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}')


def _substitute_inputs(obj, inputs: dict[str, str]):
    if isinstance(obj, str):
        return _INPUT_REF.sub(lambda match: inputs.get(match.group(1), match.group(0)), obj)
    if isinstance(obj, dict):
        return {key: _substitute_inputs(value, inputs) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_substitute_inputs(value, inputs) for value in obj]
    return obj


def _expand_steps(
    steps, local_actions: dict[str, str], name: str, job_id: str, errors: list[str], inherited=(), depth=0
) -> list[dict]:
    expanded: list[dict] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        uses = str(step.get('uses', ''))
        ifs = inherited + (() if step.get('if') is None else (str(step.get('if')),))
        if uses.startswith('./') and 'firestore-readiness' not in uses:
            key = uses.removeprefix('./')
            marker = '/.github/actions/'
            if marker in key:
                key = '.github/actions/' + key.rsplit(marker, 1)[-1]
            text = None
            for candidate in (key, f'{key}/action.yml', f'{key}/action.yaml', f'{key}.yml'):
                if candidate in local_actions:
                    text = local_actions[candidate]
                    break
            if text is None:
                errors.append(f'{name}:{job_id}: cannot expand local action {uses}')
                continue
            if depth >= 8:
                errors.append(f'{name}:{job_id}: local action expansion exceeded depth limit')
                continue
            try:
                inner_doc = _yaml_document(text)
            except Exception:
                errors.append(f'{name}:{job_id}: local action {uses} must parse')
                continue
            inner = ((inner_doc or {}).get('runs') or {}).get('steps') or []
            caller_inputs = {str(k): str(v) for k, v in (step.get('with') or {}).items()}
            inner = [_substitute_inputs(inner_step, caller_inputs) for inner_step in inner]
            expanded.extend(_expand_steps(inner, local_actions, name, job_id, errors, ifs, depth + 1))
            continue
        copied = dict(step)
        copied['__ifs__'] = ifs
        expanded.append(copied)
    return expanded


def _split_top_level(expression: str, operator: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(expression):
        char = expression[index]
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        elif char == operator and index + 1 < len(expression) and expression[index + 1] == operator and depth == 0:
            parts.append(expression[start:index])
            index += 1
            start = index + 1
        index += 1
    parts.append(expression[start:])
    return parts


def _unwrap_outer(expression: str) -> str:
    text = expression.strip()
    if not (text.startswith('(') and text.endswith(')')):
        return text
    depth = 0
    for index, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return text
        if depth == 0 and index == len(text) - 1:
            return text[1:-1].strip()
    return text


def _dependency_allows(job: dict, dep_condition_atoms, dep_id: str) -> bool:
    raw = re.sub(r'\$\{\{|\}\}', '', str(job.get('if', '') or '')).strip()
    if not raw:
        return True
    alternatives = _split_top_level(raw, '|')
    override = (
        len(alternatives) > 1
        or re.search(r'\b(?:always|failure|cancelled)\(\)', raw) is not None
        or re.search(r'needs\.[\w.-]*\.result\s*!=', raw) is not None
        or re.search(r'!(?!=)', raw) is not None
    )
    target = f"needs.{dep_id}.result=='success'"
    for alternative in alternatives:
        atoms, supported = _condition_atoms(alternative, allow_or=True)
        if not supported or not dep_condition_atoms <= atoms:
            return False
        if override:
            conjuncts = (_unwrap_outer(c) for c in _split_top_level(_unwrap_outer(alternative), '&'))
            if not any(
                re.sub(r'\s+', '', re.sub(r'\$\{\{|\}\}', '', conjunct)).replace('"', "'") == target
                for conjunct in conjuncts
            ):
                return False
    return True


def workflow_gate_violations(
    text: str, *, name: str, local_actions: dict[str, str] | None = None, dockerfiles=None
) -> list[str]:
    """Return Firestore readiness coverage violations for one workflow document."""

    errors: list[str] = []
    try:
        document = _yaml_document(text)
    except Exception:
        return [f'{name}: workflow YAML must parse']
    if not isinstance(document, dict):
        return errors
    jobs = document.get('jobs')
    if not isinstance(jobs, dict):
        return errors
    local_actions = local_actions or {}
    dockerfiles = dockerfiles or {}
    known = _known_image_names(dockerfiles)

    is_listen = pathlib.Path(name).name == LISTEN_WORKFLOW
    if is_listen and ('BACKEND_LISTEN_ROLLBACK_REVISION' in text or '--revision' in text):
        errors.append(
            f'{name}: backend-listen must not reintroduce a rollback-target resolver; '
            'rollback reuses the requested Helm revision directly'
        )
    if is_listen:
        select_runs = [
            str(step.get('run', ''))
            for job in jobs.values()
            if isinstance(job, dict)
            for step in (job.get('steps') or [])
            if isinstance(step, dict)
            and step.get('name') == _LISTEN_SELECT_STEP
            and str(step.get('if', '')).strip() == _LISTEN_DEPLOY_IF
        ]
        select_run = select_runs[0] if len(select_runs) == 1 else ''
        if not (0 <= select_run.find('exit 0') < select_run.find('BACKEND_LISTEN_SOURCE_SHA')) or (
            select_run.count('BACKEND_LISTEN_SOURCE_SHA') != 1
        ):
            errors.append(
                f'{name}: {_LISTEN_SELECT_STEP!r} must be deploy-conditioned and write '
                'BACKEND_LISTEN_SOURCE_SHA exactly once after the kept-tag exit'
            )

    gate_jobs: set[str] = set()
    uncovered: dict[str, list[frozenset[str]]] = {}
    job_if_atoms: dict[str, frozenset | None] = {}
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            job_if_atoms[job_id] = None
            continue
        condition = job.get('if')
        if condition is None:
            job_if_atoms[job_id] = frozenset()
        else:
            atoms, supported = _condition_atoms(condition)
            job_if_atoms[job_id] = atoms if supported else None

    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        job_uses = str(job.get('uses', ''))
        if job_uses:
            if not job_uses.startswith('./.github/workflows/'):
                errors.append(f'{name}:{job_id}: cannot prove Firestore gate coverage for reusable workflow {job_uses}')
            continue
        steps = job.get('steps')
        if not isinstance(steps, list):
            continue
        expanded = _expand_steps(steps, local_actions, name, job_id, errors)
        job_state = {'var_images': {}, 'tag_images': {}, 'env': {}, 'built_firestore': False}

        valid_gates: list[tuple[int, dict, frozenset]] = []
        for index, step in enumerate(expanded):
            if 'actions/firestore-readiness' not in str(step.get('uses', '')):
                continue
            gate_errors = _gate_errors(step, expanded, index, job, job_id, name)
            errors.extend(f'{name}:{job_id}: {error}' for error in gate_errors)
            if not gate_errors:
                scope = _gate_scope(step) or frozenset()
                valid_gates.append((index, step, scope))
                gate_jobs.add(job_id)

        gate_positions = [(index, scope) for index, _step, scope in valid_gates]
        if is_listen:
            gate_index = next((index for index, _step, scope in valid_gates if scope == {_LISTEN_SOURCE_ATOM}), None)
            if gate_index is None:
                errors.append(
                    f'{name}:{job_id}: listen requires the env.BACKEND_LISTEN_SOURCE_SHA-conditional readiness gate'
                )
            mutations = [
                index
                for index, step in enumerate(expanded)
                if isinstance(step.get('run'), str) and _LISTEN_MUTATION_RUN.search(step['run'])
            ]
            if mutations and (gate_index is None or gate_index > min(mutations)):
                errors.append(
                    f'{name}:{job_id}: the conditional readiness gate must run before any '
                    'backend config, secret, or Helm mutation step'
                )

        for index, step in enumerate(expanded):
            if 'actions/firestore-readiness' in str(step.get('uses', '')):
                continue
            shipments, unregistered, _published = _step_shipments(
                step, document, job, dockerfiles, known, job_state, workflow_name=pathlib.Path(name).name
            )
            for dockerfile in unregistered:
                errors.append(f'{name}:{job_id}: {dockerfile} is an unregistered backend Dockerfile')
            for scope, names in shipments:
                if not names or names <= set(NON_FIRESTORE_IMAGE_EXCLUSIONS):
                    continue
                if any(position < index and gate_key <= scope for position, gate_key in gate_positions):
                    continue
                uncovered.setdefault(job_id, []).append(names)

    protected: set[str] = set(gate_jobs)
    changed = True
    while changed:
        changed = False
        for job_id, job in jobs.items():
            if job_id in protected or not isinstance(job, dict):
                continue
            for dep in _job_needs(job) & protected:
                if _dependency_allows(job, job_if_atoms.get(dep) or frozenset(), dep):
                    protected.add(job_id)
                    changed = True
                    break

    for job_id, names_list in uncovered.items():
        if job_id not in gate_jobs and job_id in protected:
            continue
        for names in names_list:
            errors.append(
                f'{name}:{job_id}: image shipment {sorted(names) or "with unbound target"}'
                ' lacks an earlier successful Firestore readiness gate'
            )
    for job_id, job in jobs.items():
        for dep in _job_needs(job):
            if dep == 'firestore_readiness' and dep not in gate_jobs:
                errors.append(f'{name}:{job_id}: needs firestore_readiness, which does not run a valid readiness gate')
            elif dep not in jobs:
                errors.append(f'{name}:{job_id}: needs {dep}, which does not exist')
    return errors


def repository_gate_violations(root) -> list[str]:
    """Scan every workflow and local composite action for gate coverage."""

    root = pathlib.Path(root)
    dockerfiles = _runtime_images(root)
    actions_dir = root / '.github' / 'actions'
    local_actions = (
        {
            str(path.relative_to(root)): path.read_text(encoding='utf-8')
            for path in sorted(actions_dir.rglob('action.yml')) + sorted(actions_dir.rglob('action.yaml'))
        }
        if actions_dir.is_dir()
        else {}
    )
    errors: list[str] = []
    workflows_dir = root / '.github' / 'workflows'
    for path in sorted(workflows_dir.rglob('*.yml')) + sorted(workflows_dir.rglob('*.yaml')):
        errors.extend(
            workflow_gate_violations(
                path.read_text(encoding='utf-8'),
                name=str(path.relative_to(root)),
                local_actions=local_actions,
                dockerfiles=dockerfiles,
            )
        )
    return errors
