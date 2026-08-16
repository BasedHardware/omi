"""Parse Firestore reconciliation commands used by deployment policy checks."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

RECONCILE_SCRIPT = 'reconcile_firestore_indexes.py'
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
        if any(token.endswith(RECONCILE_SCRIPT) for token in tokens)
    ]
    invocations.extend(
        ReconciliationInvocation((RECONCILE_SCRIPT,)) for line in malformed_lines if RECONCILE_SCRIPT in line
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
