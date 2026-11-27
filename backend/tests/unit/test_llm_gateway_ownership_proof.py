from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from testing.shell import bash_command, bash_path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROOF = BACKEND_ROOT / 'scripts/proof-llm-gateway-ownership-handoff.sh'
CLUSTER_PREFIX = 'llm-gateway-ownership-proof-'
EMPTY_DEFAULTS = 'default kube-node-lease kube-public kube-system'
READS = {'config', 'version', 'get'}

_CALL_LOG = '''name="$(basename "$0")"
printf '%s' "$name" >> "$FAKE_CALLS"
for arg in "$@"; do printf ' %q' "$arg" >> "$FAKE_CALLS"; done
printf '\\n' >> "$FAKE_CALLS"
'''
# Same log, with the kubeconfig the call was given: by flag, else by environment.
_KUBECONFIG_CALL_LOG = '''name="$(basename "$0")"
kubeconfig="${KUBECONFIG:-none}"
if [[ "${1:-}" == --kubeconfig ]]; then kubeconfig="$2"; fi
printf '%s' "$name" >> "$FAKE_CALLS"
for arg in "$@"; do printf ' %q' "$arg" >> "$FAKE_CALLS"; done
printf ' %s' "kubeconfig=$kubeconfig" >> "$FAKE_CALLS"
printf '\\n' >> "$FAKE_CALLS"
'''
_FAKE_KWOKCTL = _CALL_LOG + '''name='' kubeconfig='' prev=''
for arg in "$@"; do
  case "$prev" in --name) name="$arg" ;; --kubeconfig) kubeconfig="$arg" ;; esac
  prev="$arg"
done
case " $* " in
  ' create cluster '*)
    [[ "$FAKE_KWOKCTL" != fail ]] || { echo 'kwokctl: no port available' >&2; exit 1; }
    printf '%s\\n' "$name" > "$FAKE_STATE/cluster"
    printf 'apiVersion: v1\\nclusters:\\n- cluster:\\n    server: %s\\n  name: kwok-%s\\n' "$FAKE_SERVER" "$name" > "$kubeconfig"
    ;;
  ' get clusters ') [[ "$FAKE_KWOKCTL" == unlisted ]] || cat "$FAKE_STATE/cluster" ;;
  ' get kubeconfig '*) printf 'apiVersion: v1\\nclusters:\\n- cluster:\\n    server: %s\\n' "$FAKE_RECORDED_SERVER" ;;
esac
'''
_FAKE_KUBECTL = _KUBECONFIG_CALL_LOG + '''file=''
if [[ "${1:-}" == --kubeconfig ]]; then
  file="$2"
  shift 2
fi
blank() { # blank <count>: a list of <count> identical objects
  local out='[' i
  for ((i = 0; i < $1; i++)); do
    [[ $i == 0 ]] || out+=,
    out+='{"metadata":{"name":"item"}}'
  done
  printf '{"items":%s]}' "$out"
}
case " $* " in
  ' config view -o json ') printf '%s\\n' "$FAKE_CONFIG" ;;
  ' config view --minify -o jsonpath={.clusters[0].cluster.server} ') sed -n 's/^ *server: *//p' "$file" ;;
  ' version -o json ') printf '{"serverVersion":{"gitVersion":"%s"}}\\n' "$FAKE_GITVERSION" ;;
  ' get nodes -o json ')
    [[ "$FAKE_NODES" != unreadable ]] || { echo 'The connection to the server 127.0.0.1:32764 was refused' >&2; exit 1; }
    blank "$FAKE_NODES"
    ;;
  ' get pods --all-namespaces -o json ') blank "$FAKE_PODS" ;;
  ' get customresourcedefinitions -o json ') blank "$FAKE_CRDS" ;;
  ' get namespaces -o json ')
    out='' separator=''
    for namespace in $FAKE_NAMESPACES; do out+="${separator}{\\"metadata\\":{\\"name\\":\\"$namespace\\"}}"; separator=,; done
    printf '{"items":[%s]}\\n' "$out"
    ;;
  ' create namespace '*) ;;
  ' apply --server-side -f - ') cat >/dev/null ;;
  ' wait node '*) [[ "$FAKE_WAIT" != fail ]] || { echo 'error: timed out waiting for the condition' >&2; exit 1; } ;;
esac
'''
_FAKE_HELM = _KUBECONFIG_CALL_LOG
_FAKE_JQ = _CALL_LOG + '''[[ "$*" == '-r .serverVersion.gitVersion' ]] || { echo 'unexpected jq filter' >&2; exit 99; }
printf '%s\\n' "$FAKE_GITVERSION"
'''


def _run_proof(
    root: Path, *args: str, **cluster: str
) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, list[str]]]]:
    """Run the real proof script over fake kwokctl, kubectl, helm and jq that model one cluster."""
    layout = root / 'repo'
    scripts = layout / 'backend' / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copy(PROOF, scripts / PROOF.name)
    state = root / 'state'
    state.mkdir()
    binaries = root / 'bin'
    binaries.mkdir()

    def shim(name: str, body: str) -> None:
        path = binaries / name
        path.write_text('#!/usr/bin/env bash\n' + body, encoding='utf-8')
        path.chmod(0o755)

    shim('kwokctl', _FAKE_KWOKCTL)
    shim('kubectl', _FAKE_KUBECTL)
    shim('helm', _FAKE_HELM)
    shim('jq', _FAKE_JQ)
    shim('python3', 'exec "$FAKE_PYTHON" "$@"\n')

    # The caller's kubeconfig names a remote cluster. The proof must never open it.
    ambient = root / 'ambient-kubeconfig'
    ambient.write_text(
        'apiVersion: v1\nclusters:\n- cluster:\n    server: https://prod.example.invalid:6443\n  name: prod\n',
        encoding='utf-8',
    )
    server = cluster.get('server', 'https://127.0.0.1:32764')
    env = {key: value for key, value in os.environ.items() if key != 'KUBECONFIG'}
    env.update(
        PATH=f'{binaries}{os.pathsep}{os.environ["PATH"]}',
        FAKE_CALLS=str(root / 'calls.txt'),
        FAKE_CONFIG=cluster.get('config', '{"clusters":[{}],"contexts":[{}]}'),
        FAKE_CRDS=cluster.get('crds', '0'),
        FAKE_GITVERSION=cluster.get('git_version', 'v1.36.1'),
        FAKE_KWOKCTL=cluster.get('kwokctl', 'ok'),
        FAKE_NAMESPACES=cluster.get('namespaces', EMPTY_DEFAULTS),
        FAKE_NODES=cluster.get('nodes', '0'),
        FAKE_PODS=cluster.get('pods', '0'),
        FAKE_PYTHON=sys.executable,
        FAKE_RECORDED_SERVER=cluster.get('recorded_server', server),
        FAKE_SERVER=server,
        FAKE_STATE=str(state),
        KUBECONFIG=str(ambient),
    )
    log = root / 'calls.txt'
    result = subprocess.run(
        bash_command(bash_path(scripts / PROOF.name, cwd=layout), *args),
        cwd=layout,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    calls = []
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            parts = shlex.split(line)
            calls.append((parts[0], parts[1:]))
    return result, calls


def _calls_of(calls: list[tuple[str, list[str]]], tool: str) -> list[list[str]]:
    return [argv for name, argv in calls if name == tool]


def _command(argv: list[str]) -> list[str]:
    """A logged call without its kubeconfig note and without a leading --kubeconfig pair."""
    if argv[-1].startswith('kubeconfig='):
        argv = argv[:-1]
    return argv[2:] if argv[:1] == ['--kubeconfig'] else argv


def _assert_refused_before_any_write(
    result: subprocess.CompletedProcess[str],
    calls: list[tuple[str, list[str]]],
    reason: str,
    *,
    cluster_created: bool = True,
) -> None:
    assert result.returncode == 3, result.stderr
    assert f'REFUSED: {reason}' in result.stderr
    kwokctl = _calls_of(calls, 'kwokctl')
    assert [argv[:2] for argv in kwokctl][0] == ['create', 'cluster']
    assert [argv[:2] for argv in kwokctl][-1] == ['delete', 'cluster'], 'the cluster this run asked for is removed'
    if cluster_created:
        name = kwokctl[0][kwokctl[0].index('--name') + 1]
        assert name[: len(CLUSTER_PREFIX)] == CLUSTER_PREFIX and len(name) == len(CLUSTER_PREFIX) + 12
    written = [argv for argv in _calls_of(calls, 'kubectl') if _command(argv)[0] not in READS]
    assert written == [], f'the proof wrote before refusing: {written}'


def test_proof_refuses_a_cluster_kwokctl_does_not_list(tmp_path):
    result, calls = _run_proof(tmp_path, kwokctl='unlisted')
    _assert_refused_before_any_write(result, calls, 'kwokctl does not list llm-gateway-ownership-proof-')
    assert _calls_of(calls, 'kubectl') == [], 'nothing is asked of a cluster kwokctl does not vouch for'


def test_proof_refuses_when_kwokctl_cannot_create_the_cluster(tmp_path):
    result, calls = _run_proof(tmp_path, kwokctl='fail')
    _assert_refused_before_any_write(
        result, calls, 'kwokctl could not create the throwaway cluster', cluster_created=False
    )
    assert 'kwokctl: no port available' in result.stderr, 'the kwokctl failure is shown'


def test_proof_refuses_a_kubeconfig_that_is_not_the_one_kwokctl_holds(tmp_path):
    """A kubeconfig swapped for another cluster's, even one on loopback, is not the run's cluster."""
    result, calls = _run_proof(tmp_path, recorded_server='https://127.0.0.1:32765')
    _assert_refused_before_any_write(
        result,
        calls,
        'the kubeconfig in use is not the one kwokctl holds for llm-gateway-ownership-proof-',
    )


def test_proof_refuses_a_kubeconfig_that_names_more_than_one_cluster(tmp_path):
    result, calls = _run_proof(tmp_path, config='{"clusters":[{},{}],"contexts":[{},{}]}')
    _assert_refused_before_any_write(
        result,
        calls,
        'the kubeconfig kwokctl wrote for llm-gateway-ownership-proof-',
    )
    assert 'names other clusters as well' in result.stderr


def test_proof_refuses_an_api_server_that_is_not_on_loopback(tmp_path):
    result, calls = _run_proof(tmp_path, server='https://10.0.0.1:6443')
    _assert_refused_before_any_write(result, calls, "the API server of llm-gateway-ownership-proof-")
    assert "is 'https://10.0.0.1:6443', not loopback" in result.stderr


def test_proof_refuses_a_vendor_kubernetes_build(tmp_path):
    result, calls = _run_proof(tmp_path, git_version='v1.31.5-gke.1023000')
    _assert_refused_before_any_write(
        result,
        calls,
        "llm-gateway-ownership-proof-",
    )
    assert "reports 'v1.31.5-gke.1023000', not an upstream Kubernetes build" in result.stderr


@pytest.mark.parametrize(
    'cluster',
    [
        pytest.param({'nodes': '1'}, id='nodes'),
        pytest.param({'pods': '1'}, id='pods'),
        pytest.param({'crds': '1'}, id='crds'),
        pytest.param({'namespaces': f'{EMPTY_DEFAULTS} prod-omi-backend'}, id='namespaces'),
    ],
)
def test_proof_refuses_a_cluster_that_is_not_empty(tmp_path, cluster):
    result, calls = _run_proof(tmp_path, **cluster)
    assert result.returncode == 3, result.stderr
    assert 'REFUSED: llm-gateway-ownership-proof-' in result.stderr
    written = [argv for argv in _calls_of(calls, 'kubectl') if _command(argv)[0] not in READS]
    assert written == [], f'the proof wrote to a cluster that holds something: {written}'
    assert [argv[:2] for argv in _calls_of(calls, 'kwokctl')][-1] == ['delete', 'cluster']


def test_proof_refuses_a_cluster_whose_contents_it_cannot_read(tmp_path):
    result, calls = _run_proof(tmp_path, nodes='unreadable')
    _assert_refused_before_any_write(result, calls, 'could not list nodes in llm-gateway-ownership-proof-')
    assert result.stderr.count('REFUSED:') == 1, 'one refusal, naming what could not be established'


def test_proof_rejects_arguments_it_does_not_know_before_creating_anything(tmp_path):
    result, calls = _run_proof(tmp_path, '--force')
    assert result.returncode == 2
    assert 'usage: bash backend/scripts/proof-llm-gateway-ownership-handoff.sh [--keep]' in result.stderr
    assert calls == [], 'nothing is created for a run that was not understood'


@pytest.mark.parametrize('keep', [False, True], ids=['removes-the-cluster', 'keeps-the-cluster'])
def test_proof_writes_only_after_the_identity_check_and_only_through_the_run_kubeconfig(tmp_path, keep):
    """Once the cluster is established as the run's own, every call is pinned to its kubeconfig."""
    args = ('--keep',) if keep else ()
    result, calls = _run_proof(tmp_path, *args)
    # The proof goes on to the scenarios, which stop here at the deploy script this layout does not copy.
    assert result.returncode == 127, (result.returncode, result.stderr)

    for line in (
        'ok: kwokctl lists llm-gateway-ownership-proof-',
        'created by this run',
        'ok: the kubeconfig in use is the one kwokctl holds for it; API server https://127.0.0.1:32764 is loopback',
        'ok: v1.36.1 is an upstream Kubernetes build',
        f'ok: the cluster is empty: 0 nodes, 0 pods, 0 CRDs, namespaces {EMPTY_DEFAULTS}',
    ):
        assert line in result.stdout

    kwokctl = _calls_of(calls, 'kwokctl')
    assert [argv[:2] for argv in kwokctl][:3] == [['create', 'cluster'], ['get', 'clusters'], ['get', 'kubeconfig']]
    assert (['delete', 'cluster'] in [argv[:2] for argv in kwokctl]) is not keep
    run_kubeconfig = kwokctl[0][kwokctl[0].index('--kubeconfig') + 1]
    recorded_kubeconfig = str(Path(run_kubeconfig).with_name('kwokctl-kubeconfig'))

    kubectl = _calls_of(calls, 'kubectl')
    first_write = next(index for index, argv in enumerate(kubectl) if _command(argv)[0] not in READS)
    assert _command(kubectl[first_write])[:2] == ['create', 'namespace']
    verified = calls.index(('kwokctl', kwokctl[2]))
    assert verified < calls.index(('kubectl', kubectl[first_write])), 'the identity check ends before the first write'
    assert {argv[-1] for argv in kubectl} == {f'kubeconfig={run_kubeconfig}', f'kubeconfig={recorded_kubeconfig}'}

    helm = _calls_of(calls, 'helm')
    assert helm, 'the proof reaches its scenarios'
    assert {argv[-1] for argv in helm} == {
        f'kubeconfig={run_kubeconfig}'
    }, 'the deploy tooling inherits the run kubeconfig'
    assert 'ambient-kubeconfig' not in (tmp_path / 'calls.txt').read_text(encoding='utf-8')


def test_proof_gates_every_cluster_write_behind_the_run_cluster_identity():
    """Static guard: the caller's kubeconfig has no path into the proof."""
    text = PROOF.read_text(encoding='utf-8')
    lines = text.splitlines()
    assert '--force-conflicts' not in text
    assert '--ignore-not-found' not in text, 'the proof deletes nothing it did not create in this run'

    def only(needle: str) -> int:
        hits = [index for index, line in enumerate(lines) if needle in line]
        assert len(hits) == 1, f'{needle!r} expected exactly once, found {len(hits)}'
        return hits[0]

    create = only('kwokctl create cluster --name "$CLUSTER"')
    gate = [index for index, line in enumerate(lines) if line == 'require_run_cluster']
    assert len(gate) == 1, 'the identity check is called exactly once, on its own line'
    first_write = only('kubectl create namespace "$NAMESPACE"')
    pinned = only('export PATH="$WORK/bin:$PATH"')
    assert create < gate[0] < first_write
    assert pinned < first_write, 'writes go through the wrappers that pin the run kubeconfig'
    for index, line in enumerate(lines[:pinned]):
        code = line.split(' #', 1)[0].strip()
        if 'kubectl' not in code or code.startswith(('#', 'for tool in')):
            continue
        assert '--kubeconfig' in code, f'line {index + 1} reaches kubectl without the run kubeconfig: {code}'
