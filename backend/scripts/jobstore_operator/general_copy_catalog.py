#!/usr/bin/env python3
"""Separate, closed catalog-only profile. Digests pin trusted inputs, not evidence authenticity."""

from __future__ import annotations
import argparse, hashlib, ipaddress, json, os, pathlib, pwd, re, signal, socket, stat, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import general_copy_catalog_contract as C


class Hold(Exception):
    pass


class Cancelled(Hold):
    pass


def need(value, reason):
    if not value:
        raise Hold(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def unique(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 'duplicate_key')
        out[key] = value
    return out


def read_pinned(path, digest, limit=65536):
    need(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'unbound_digest')
    path = pathlib.Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'absolute_path_required')
    for parent in (path, *path.parents):
        need(not parent.is_symlink(), 'symlink_input_refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        need(bool(os.fstatvfs(fd).f_flag & os.ST_RDONLY), 'readonly_input_required')
        need(
            stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not info.st_mode & 0o022,
            'regular_immutable_input_required',
        )
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        need(len(raw) <= limit and sha(raw) == digest, 'pinned_input_mismatch')
        return json.loads(raw, object_pairs_hook=unique)
    finally:
        os.close(fd)


def validate_bindings(b):
    need(isinstance(b, dict) and set(b) == C.BINDING_KEYS, 'binding_schema')
    need(
        type(b['version']) is int
        and b['version'] == 1
        and b['profile'] == C.PROFILE
        and b['source_sha'] == C.SOURCE
        and b['source_tree'] == C.TREE,
        'profile_source_mismatch',
    )
    need(type(b['uid']) is int and b['uid'] == 1000 and b['home'] == '/home/ubuntu', 'uid_home_binding')
    need(b['wrapper_sha256'] == C.WRAPPER_SHA and b['guard_sha256'] == C.GUARD_SHA, 'frozen_payload_mismatch')
    for key in ('probe_sha256', 'contract_sha256', 'structure_sha256', 'git_sha256', 'python_sha256'):
        need(isinstance(b[key], str) and re.fullmatch('[0-9a-f]{64}', b[key]), 'unbound_digest')
    need(
        isinstance(b['image_digest'], str)
        and re.fullmatch(r'[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}', b['image_digest']),
        'image_binding',
    )
    for key in ('namespace', 'ksa', 'pod_name', 'hostname'):
        need(
            isinstance(b[key], str) and re.fullmatch('[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?', b[key]), 'workload_binding'
        )
    need(
        isinstance(b['pod_uid'], str) and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', b['pod_uid']),
        'pod_uid_binding',
    )
    for key in ('target_host', 'database', 'current_role', 'session_role'):
        need(
            isinstance(b[key], str) and 0 < len(b[key]) <= 253 and not re.search(r'[\s\x00]', b[key]), 'target_binding'
        )
    for key in ('target_port', 'server_port'):
        need(type(b[key]) is int and 1 <= b[key] <= 65535, 'port_binding')
    need(type(b['server_major']) is int and b['server_major'] == 16, 'PG16_structure_profile_required')
    need(isinstance(b['server_address'], str), 'server_address_binding')
    ipaddress.ip_address(b['server_address'])
    flags = b['role_flags']
    need(
        isinstance(flags, dict)
        and set(flags) == {'superuser', 'inherit', 'bypassrls'}
        and all(type(v) is bool for v in flags.values()),
        'role_flags_binding',
    )
    for key in ('git_path', 'python_path', 'source_root', 'wrapper_path', 'guard_path', 'structure_path'):
        need(
            isinstance(b[key], str)
            and b[key].startswith('/')
            and '..' not in pathlib.Path(b[key]).parts
            and not re.search(r'[\s\x00]', b[key]),
            'absolute_path_binding',
        )
    need(
        b['source_root'] == '/opt/omi'
        and b['python_path'] == '/opt/operator-venv/bin/python'
        and b['wrapper_path'] == '/opt/runner/supervisor.py'
        and b['guard_path'] == '/opt/runner/process_guard.py',
        'image_layout_binding',
    )
    return b


def verify_source(b, deadline, clock=time.monotonic, check_output=subprocess.check_output):
    root = pathlib.Path(b['source_root'])
    gitdir = root / '.git'
    need(
        root.is_dir() and not root.is_symlink() and gitdir.is_dir() and not gitdir.is_symlink(),
        'standalone_source_required',
    )
    for name in ('commondir', 'gitdir', 'objects/info/alternates', 'objects/info/http-alternates'):
        need(not (gitdir / name).exists() and not (gitdir / name).is_symlink(), 'git_redirect_refused')
    need(not any(p.is_symlink() for p in gitdir.rglob('*')), 'git_symlink_refused')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(
        GIT_OPTIONAL_LOCKS='0',
        GIT_NO_LAZY_FETCH='1',
        GIT_NO_REPLACE_OBJECTS='1',
        GIT_TERMINAL_PROMPT='0',
        GIT_CONFIG_NOSYSTEM='1',
        GIT_CONFIG_GLOBAL='/dev/null',
    )

    def git(*args, cap=5):
        remaining = deadline - clock()
        need(remaining > 0, 'source_deadline')
        return check_output(
            [
                b['git_path'],
                '--no-optional-locks',
                '-c',
                'core.fsmonitor=false',
                '-c',
                'core.untrackedCache=false',
                '-c',
                'safe.directory=' + str(root),
                '-C',
                str(root),
                *args,
            ],
            env=env,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=min(cap, remaining),
        ).strip()

    need(git('rev-parse', '--show-toplevel') == str(root), 'source_root_mismatch')
    need(git('rev-parse', '--absolute-git-dir') == str(gitdir), 'git_dir_mismatch')
    need(git('rev-parse', '--path-format=absolute', '--git-common-dir') == str(gitdir), 'git_common_mismatch')
    need(
        git('rev-parse', '--path-format=absolute', '--git-path', 'objects') == str(gitdir / 'objects'),
        'git_objects_mismatch',
    )
    need(git('rev-parse', 'HEAD') == C.SOURCE and git('rev-parse', 'HEAD^{tree}') == C.TREE, 'source_pin_mismatch')
    need(not git('status', '--porcelain', '--untracked-files=all', cap=30), 'source_dirty')
    paths = sorted((root / 'backend/database/jobstore/migrations').glob('*.sql'))
    vector = []
    for path in paths:
        need(path.is_file() and not path.is_symlink(), 'migration_file')
        version, name = path.stem.split('_', 1)
        vector.append((int(version), name, sha(path.read_bytes())))
    need(exact(vector, C.SOURCE_VECTOR), 'complete_source9_mismatch')
    verify_working_tree(root, git('ls-tree', '-r', '-z', '--full-tree', 'HEAD', cap=10), deadline, clock)


def verify_working_tree(root, tree, deadline, clock=time.monotonic):
    # Read HEAD's object inventory, then hash working bytes without consulting the index.
    expected = {}
    for entry in tree.split('\0'):
        if not entry:
            continue
        metadata, name = entry.split('\t', 1)
        mode, kind, oid = metadata.split()
        rel = pathlib.PurePosixPath(name)
        need(
            not rel.is_absolute()
            and '..' not in rel.parts
            and '.git' not in rel.parts
            and kind == 'blob'
            and mode in ('100644', '100755', '120000')
            and re.fullmatch('[0-9a-f]{40}', oid),
            'source_tree_entry',
        )
        need(name not in expected, 'source_tree_duplicate')
        expected[name] = (mode, oid)
    need(bool(expected), 'source_tree_empty')
    observed = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        need(clock() < deadline, 'source_deadline')
        if pathlib.Path(directory) == root:
            dirs[:] = [d for d in dirs if d != '.git']
        for d in list(dirs):
            if (pathlib.Path(directory) / d).is_symlink():
                files.append(d)
                dirs.remove(d)
        for name in files:
            need(clock() < deadline, 'source_deadline')
            path = pathlib.Path(directory) / name
            rel = path.relative_to(root).as_posix()
            need(rel in expected, 'source_extra_file')
            observed.add(rel)
            mode, oid = expected[rel]
            info = path.lstat()
            if mode == '120000':
                need(stat.S_ISLNK(info.st_mode), 'source_symlink_mode')
                raw = os.fsencode(os.readlink(path))
                digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            else:
                need(
                    stat.S_ISREG(info.st_mode) and bool(info.st_mode & 0o111) == (mode == '100755'), 'source_file_mode'
                )
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    before = os.fstat(fd)
                    need(
                        stat.S_ISREG(before.st_mode) and before.st_ino == info.st_ino and before.st_dev == info.st_dev,
                        'source_file_changed',
                    )
                    digestor = hashlib.sha1(b'blob ' + str(before.st_size).encode() + b'\0')
                    count = 0
                    while True:
                        need(clock() < deadline, 'source_deadline')
                        block = os.read(fd, 1048576)
                        if not block:
                            break
                        count += len(block)
                        digestor.update(block)
                    after = os.fstat(fd)
                    need(
                        count == before.st_size
                        and (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                        == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                        'source_file_changed',
                    )
                    digest = digestor.hexdigest()
                finally:
                    os.close(fd)
            need(digest == oid, 'source_working_bytes_mismatch')
    need(observed == set(expected), 'source_missing_file')


def preauth(b, deadline):
    need(sys.platform == 'linux' and os.getuid() == os.geteuid() == 1000, 'designated_linux_uid_required')
    need(pwd.getpwuid(os.getuid()).pw_dir == b['home'] and os.getenv('HOME') == b['home'], 'pwd_home_mismatch')
    need(socket.gethostname() == b['hostname'], 'hostname_mismatch')
    for key, envkey in (
        ('pod_uid', 'OPERATOR_POD_UID'),
        ('pod_name', 'OPERATOR_POD_NAME'),
        ('namespace', 'OPERATOR_NAMESPACE'),
        ('ksa', 'OPERATOR_KSA'),
        ('image_digest', 'OPERATOR_IMAGE_DIGEST'),
    ):
        need(os.getenv(envkey) == b[key], 'workload_identity_mismatch')
    need(
        sha(pathlib.Path(__file__).read_bytes()) == b['probe_sha256']
        and sha((HERE / 'general_copy_catalog_contract.py').read_bytes()) == b['contract_sha256'],
        'catalog_payload_mismatch',
    )
    for pathkey, hashkey in (
        ('wrapper_path', 'wrapper_sha256'),
        ('guard_path', 'guard_sha256'),
        ('python_path', 'python_sha256'),
        ('git_path', 'git_sha256'),
    ):
        path = pathlib.Path(b[pathkey])
        need(path.is_file() and sha(path.read_bytes()) == b[hashkey], 'runtime_bytes_mismatch')
        need(bool(os.statvfs(path).f_flag & os.ST_RDONLY), 'readonly_runtime_required')
    need(
        pathlib.Path(sys.executable).resolve() == pathlib.Path(b['python_path']).resolve()
        and sys.version_info[:3] == (3, 11, 15),
        'interpreter_mismatch',
    )
    need(bool(os.statvfs(b['source_root']).f_flag & os.ST_RDONLY), 'readonly_source_required')
    need(bool(os.statvfs(__file__).f_flag & os.ST_RDONLY), 'readonly_catalog_required')
    need(bool(os.statvfs(b['structure_path']).f_flag & os.ST_RDONLY), 'readonly_structure_required')
    need(
        not any(
            os.getenv(k)
            for k in (
                'GOOGLE_APPLICATION_CREDENTIALS',
                'CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE',
                'GOOGLE_OAUTH_ACCESS_TOKEN',
                'CLOUDSDK_CONFIG',
                'PGSERVICE',
                'PGSERVICEFILE',
                'PGOPTIONS',
            )
        ),
        'credential_override_refused',
    )
    need(
        not (pathlib.Path(b['home']) / '.config/gcloud/application_default_credentials.json').exists(),
        'ambient_adc_refused',
    )
    verify_source(b, deadline)


def connect_workload(b):
    import psycopg

    need(psycopg.__version__ == '3.2.10', 'driver_mismatch')
    import google.auth
    from google.auth.compute_engine.credentials import Credentials

    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/sqlservice.login'])
    need(isinstance(credentials, Credentials), 'workload_adc_type')
    # Exact source already verified; this module has no data-plane constructor.
    import importlib.util

    path = pathlib.Path(b['source_root']) / 'backend/database/jobstore/connection.py'
    spec = importlib.util.spec_from_file_location('pinned_catalog_connection', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.iam_connector(b['target_host'], b['database'], b['current_role'], port=b['target_port'])()


class Statements:
    def __init__(self, conn, deadline, clock, cancelled):
        self.conn = conn
        self.deadline = deadline
        self.clock = clock
        self.cancelled = cancelled
        self.index = 0
        self.terminal = False
        self.transcript = []

    def execute(self, sid):
        need(sid in C.SQL and not self.terminal, 'unknown_or_terminal_statement')
        if sid != 'F01':
            if self.cancelled():
                raise Cancelled('cancelled')
            need(self.clock() < self.deadline, 'catalog_deadline')
            need(sid == C.ORDER[self.index], 'statement_order')
            self.index += 1
        else:
            self.terminal = True
        params = C.PARAMS.get(sid)
        self.transcript.append(sid)
        cursor = self.conn.execute(C.SQL[sid], params) if params is not None else self.conn.execute(C.SQL[sid])
        if sid in ('B01', 'B02', 'B03', 'F01'):
            return []
        rows = cursor.fetchmany(258)
        need(len(rows) < 258, 'catalog_rows_bound')
        need(len(json.dumps(rows, allow_nan=False).encode()) <= 32768, 'catalog_bytes_bound')
        if self.cancelled():
            raise Cancelled('cancelled')
        return [list(row) for row in rows]


def verify_rows(rows, b, structure):
    if 'I01' not in rows:
        return
    identity = rows['I01']
    need(len(identity) == 1 and len(identity[0]) == 7, 'identity_shape')
    db, role, session, address, port, version, readonly = identity[0]
    need(
        (db, role, session, address, port)
        == (b['database'], b['current_role'], b['session_role'], b['server_address'], b['server_port'])
        and type(port) is int,
        'session_identity',
    )
    need(
        isinstance(version, str)
        and version.isdigit()
        and int(version) // 10000 == b['server_major']
        and readonly == 'on',
        'server_or_readonly_mismatch',
    )
    if 'I02' not in rows:
        return
    tls = rows['I02']
    need(
        len(tls) == 1
        and len(tls[0]) == 3
        and tls[0][0] is True
        and isinstance(tls[0][1], str)
        and tls[0][1] in ('TLSv1.2', 'TLSv1.3')
        and isinstance(tls[0][2], str)
        and 0 < len(tls[0][2]) < 256,
        'TLS_required',
    )
    if 'R01' not in rows:
        return
    relations = rows['R01']
    need([r[1] for r in relations] == list(C.RELATIONS), 'relation_set')
    for row in relations:
        need(
            len(row) == 9
            and row[0] == 'public'
            and type(row[2]) is int
            and row[2] > 0
            and row[3] == 'r'
            and all(type(row[i]) is bool for i in (4, 5, 6, 8))
            and row[6] is False
            and isinstance(row[7], str)
            and 0 < len(row[7]) <= 63,
            'relation_or_RLS',
        )
    need(
        isinstance(structure, dict)
        and set(structure) == {'profile', 'source', 'R02', 'R03', 'X01'}
        and structure['profile'] == C.PROFILE
        and structure['source'] == C.SOURCE,
        'structure_profile',
    )
    for sid in ('R02', 'R03', 'X01'):
        if sid not in rows:
            return
        need(exact(rows[sid], structure[sid]), 'schema_structure_' + sid)
    if 'P01' not in rows:
        return
    need(exact(rows['P01'], [[True, True]]), 'connect_usage_privileges')
    if 'P02' not in rows:
        return
    flags = b['role_flags']
    need(
        exact(rows['P02'], [[b['current_role'], flags['superuser'], flags['inherit'], flags['bypassrls']]]),
        'role_flags',
    )
    if 'P03' not in rows:
        return
    grants = rows['P03']
    need([r[0] for r in grants] == list(C.APP), 'table_privilege_set')
    for row in grants:
        need(len(row) == 5 and all(type(v) is bool for v in row[1:]) and row[4] is True, 'DELETE_privilege')
    if 'P04' not in rows:
        return
    columns = rows['P04']
    expected = {(table, col) for table, cols in C.COLUMNS.items() for col in cols}
    seen = set()
    for row in columns:
        need(
            len(row) == 5
            and (row[0], row[1]) in expected
            and (row[0], row[1]) not in seen
            and all(type(v) is bool for v in row[2:]),
            'column_privilege_shape',
        )
        seen.add((row[0], row[1]))
        need(row[2] is True and row[3] is True and (row[1] != 'doc' or row[4] is True), 'effective_column_privilege')
    need(seen == expected, 'column_privilege_set')
    if 'P05' not in rows:
        return
    need(exact(rows['P05'], [[name, True] for name in C.META_COLUMNS]), 'metadata_SELECT_privilege')
    if 'V01' not in rows:
        return
    need(exact(rows['V01'], C.DATABASE_VECTOR), 'literal_schema8_mismatch')


def run_catalog(b, structure, connect, *, binding_digest, deadline=None, clock=time.monotonic, cancelled=lambda: False):
    stage = 'bindings'
    conn = None
    statements = None
    rollback = False
    closed = False
    rows = {}
    failure = None
    deadline = clock() + 40 if deadline is None else deadline
    try:
        validate_bindings(b)
        need(isinstance(binding_digest, str) and re.fullmatch('[0-9a-f]{64}', binding_digest), 'binding_digest')
        if cancelled():
            raise Cancelled('cancelled')
        need(clock() < deadline, 'catalog_deadline')
        stage = 'connect'
        conn = connect()
        statements = Statements(conn, deadline, clock, cancelled)
        for sid in C.ORDER:
            if sid == 'F01':
                break
            stage = sid
            rows[sid] = statements.execute(sid)
            verify_rows(rows, b, structure)
        stage = 'validate'
        verify_rows(rows, b, structure)
        if cancelled():
            raise Cancelled('cancelled')
        need(clock() < deadline, 'catalog_deadline')
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            failure = 'Cancelled'
        else:
            failure = 'Cancelled' if isinstance(error, Cancelled) else 'CatalogFailure'
    finally:
        if conn is not None:
            try:
                if statements is None:
                    raise Hold('no_statement_owner')
                statements.execute('F01')
                rollback = True
            except BaseException:
                failure = 'CleanupFailure'
                stage = 'rollback'
            try:
                conn.close()
                closed = True
            except BaseException:
                failure = 'CleanupFailure'
                stage = 'close'
        if cancelled():
            failure = 'Cancelled'
        if clock() >= deadline and failure is None:
            failure = 'CatalogDeadline'
            stage = 'deadline'
    transcript = statements.transcript if statements else []
    common = {
        'profile': C.PROFILE,
        'source_sha': C.SOURCE,
        'source_tree': C.TREE,
        'customer_rows_read': False,
        'state_initialized': False,
        'write_attempted': False,
        'runtime_admitted': False,
        'serving_proven': False,
        'rollback': rollback,
        'closed': closed,
        'statement_ids': transcript,
    }
    if failure:
        return dict(common, result='HOLD', failure_class=failure, failure_stage=stage)
    return dict(
        common,
        result='GENERAL_COPY_CATALOG_MATCH_ONLY',
        image_digest=b['image_digest'],
        bindings_sha256=binding_digest,
        probe_sha256=b['probe_sha256'],
        contract_sha256=b['contract_sha256'],
        structure_sha256=b['structure_sha256'],
        catalog=rows,
    )


def clean_failure(stage):
    return {
        'result': 'HOLD',
        'profile': C.PROFILE,
        'failure_stage': stage,
        'failure_class': 'BindingOrRuntimeFailure',
        'customer_rows_read': False,
        'state_initialized': False,
        'write_attempted': False,
        'runtime_admitted': False,
        'serving_proven': False,
        'rollback': False,
        'closed': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', required=True)
    parser.add_argument('--bindings-sha256', required=True)
    parser.add_argument('--internal-catalog-child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    stage = 'bindings'
    try:
        b = validate_bindings(read_pinned(args.bindings, args.bindings_sha256))
        stage = 'runtime'
        deadline = time.monotonic() + 50

        def interrupted(*_):
            raise Cancelled('signal')

        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
            signal.signal(sig, interrupted)
        signal.alarm(50)
        preauth(b, deadline - 10)
        structure = read_pinned(b['structure_path'], b['structure_sha256'])
        if args.internal_catalog_child:
            report = run_catalog(
                b, structure, lambda: connect_workload(b), binding_digest=args.bindings_sha256, deadline=deadline - 10
            )
        else:
            import importlib.util

            spec = importlib.util.spec_from_file_location('frozen_catalog_guard', b['guard_path'])
            guard = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(guard)
            # Parent timer is replaced by the frozen guard's own60s child/custody deadline.
            signal.alarm(0)
            outcome, raw = guard.run_group(
                [
                    sys.executable,
                    '-I',
                    '-B',
                    str(pathlib.Path(__file__).resolve()),
                    '--internal-catalog-child',
                    '--bindings',
                    args.bindings,
                    '--bindings-sha256',
                    args.bindings_sha256,
                ],
                timeout=60,
            )
            need(
                exact(outcome, {'result': 'COMPLETED', 'exit_code': 0}) and len(raw) <= 65536,
                'child_or_custody_failure',
            )
            report = json.loads(raw, object_pairs_hook=unique)
            need(
                isinstance(report, dict)
                and set(report)
                == {
                    'profile',
                    'source_sha',
                    'source_tree',
                    'customer_rows_read',
                    'state_initialized',
                    'write_attempted',
                    'runtime_admitted',
                    'serving_proven',
                    'rollback',
                    'closed',
                    'statement_ids',
                    'result',
                    'image_digest',
                    'bindings_sha256',
                    'probe_sha256',
                    'contract_sha256',
                    'structure_sha256',
                    'catalog',
                }
                and report.get('bindings_sha256') == args.bindings_sha256
                and all(report.get(k) == b[k] for k in ('probe_sha256', 'contract_sha256', 'structure_sha256'))
                and report.get('statement_ids') == list(C.ORDER)
                and set(report.get('catalog', {})) == set(C.ORDER) - {'F01'}
                and report.get('result') == 'GENERAL_COPY_CATALOG_MATCH_ONLY'
                and report.get('profile') == C.PROFILE
                and report.get('source_sha') == C.SOURCE
                and report.get('source_tree') == C.TREE
                and report.get('image_digest') == b['image_digest']
                and report.get('rollback') is True
                and report.get('closed') is True
                and all(
                    report.get(k) is False
                    for k in (
                        'customer_rows_read',
                        'state_initialized',
                        'write_attempted',
                        'runtime_admitted',
                        'serving_proven',
                    )
                ),
                'child_receipt_mismatch',
            )
        if report.get('result') == 'GENERAL_COPY_CATALOG_MATCH_ONLY':
            verify_rows(report['catalog'], b, structure)
        raw = json.dumps(report, sort_keys=True, allow_nan=False)
        need(len(raw.encode()) <= 65536, 'receipt_bound')
        print(raw)
        return 0 if report['result'] == 'GENERAL_COPY_CATALOG_MATCH_ONLY' else 2
    except BaseException:
        print(json.dumps(clean_failure(stage), sort_keys=True))
        return 2
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
