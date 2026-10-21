"""gcp_backend_listen_helm.yml listen_edge_image_digest: blank changes nothing; a value is a verified digest."""

import pytest

from scripts import admit_listen_edge_image as admitter

PROJECT = 'based-hardware'
SHA = 'a' * 40
OTHER_SHA = 'b' * 40
DIGEST = 'sha256:' + 'c' * 64
REF = f'gcr.io/{PROJECT}/listen-edge@{DIGEST}'


def edge_config(revision=SHA, env_sha=None):
    return {
        'Labels': {'org.opencontainers.image.revision': revision},
        'Env': [
            'PATH=/usr/local/bin',
            'EDGE_VAD_MODEL_PATH=/models/silero_vad.onnx',
            f'OMI_RELEASE_SHA={env_sha or revision}',
        ],
    }


def inspector(configs):
    calls = []

    def inspect(ref):
        calls.append(ref)
        return configs[ref]

    inspect.calls = calls
    return inspect


def test_blank_input_leaves_the_release_untouched_and_reads_nothing():
    inspect = inspector({})
    assert admitter.admit('', project=PROJECT, sha=SHA, inspect=inspect) == {}
    assert admitter.admit('   ', project=PROJECT, sha=SHA, inspect=inspect) == {}
    assert inspect.calls == []


def test_admitted_digest_yields_repository_and_digest():
    outputs = admitter.admit(REF, project=PROJECT, sha=SHA, inspect=inspector({REF: edge_config()}))
    assert outputs == {
        'LISTEN_EDGE_IMAGE_REPOSITORY': f'gcr.io/{PROJECT}/listen-edge',
        'LISTEN_EDGE_IMAGE_DIGEST': DIGEST,
    }


@pytest.mark.parametrize(
    'raw',
    [
        f'gcr.io/{PROJECT}/listen-edge:abc123456789',  # a tag, not a digest
        f'gcr.io/based-hardware-dev/listen-edge@{DIGEST}',  # another project's registry
        f'gcr.io/{PROJECT}/backend@{DIGEST}',  # another image
        f'gcr.io/{PROJECT}/backend-realtime@{DIGEST}',
        f'gcr.io/{PROJECT}/listen-edge@sha256:{"c" * 63}',  # short digest
        f'gcr.io/{PROJECT}/listen-edge@sha256:{"C" * 64}',  # uppercase hex
        f'listen-edge={REF}',  # the service_images pair shape
        f'{REF} {REF}',  # a list
        f'{REF},{REF}',
    ],
)
def test_malformed_or_foreign_references_are_refused_before_any_registry_read(raw):
    inspect = inspector({})
    with pytest.raises(admitter.ListenEdgeImageError):
        admitter.admit(raw, project=PROJECT, sha=SHA, inspect=inspect)
    assert inspect.calls == []


def test_digest_of_another_sha_is_refused():
    with pytest.raises(admitter.ListenEdgeImageError, match='labelled revision'):
        admitter.admit(REF, project=PROJECT, sha=SHA, inspect=inspector({REF: edge_config(revision=OTHER_SHA)}))


def test_revision_label_without_matching_release_env_is_refused():
    config = edge_config(revision=SHA, env_sha=OTHER_SHA)
    with pytest.raises(admitter.ListenEdgeImageError, match='OMI_RELEASE_SHA'):
        admitter.admit(REF, project=PROJECT, sha=SHA, inspect=inspector({REF: config}))


def test_unlabelled_image_is_refused():
    with pytest.raises(admitter.ListenEdgeImageError, match='labelled revision'):
        admitter.admit(REF, project=PROJECT, sha=SHA, inspect=inspector({REF: {'Env': [f'OMI_RELEASE_SHA={SHA}']}}))


def test_short_or_malformed_admitted_sha_is_refused():
    with pytest.raises(admitter.ListenEdgeImageError, match='40-character'):
        admitter.admit(REF, project=PROJECT, sha='abc1234', inspect=inspector({REF: edge_config()}))


def test_registry_read_failure_is_an_admission_error():
    def failing(ref):
        raise admitter.ListenEdgeImageError(f'cannot read the image config of {ref}')

    with pytest.raises(admitter.ListenEdgeImageError, match='cannot read'):
        admitter.admit(REF, project=PROJECT, sha=SHA, inspect=failing)


def test_main_writes_github_env_and_reports(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / 'env'
    monkeypatch.setattr(admitter, 'inspect_image_config', lambda ref: edge_config())
    rc = admitter.main(['--digest', REF, '--project', PROJECT, '--sha', SHA, '--github-env', str(env_file)])
    assert rc == 0
    assert env_file.read_text() == (
        f'LISTEN_EDGE_IMAGE_REPOSITORY=gcr.io/{PROJECT}/listen-edge\nLISTEN_EDGE_IMAGE_DIGEST={DIGEST}\n'
    )
    assert 'admitted' in capsys.readouterr().out


def test_main_blank_digest_exits_zero_without_writing(tmp_path, capsys):
    env_file = tmp_path / 'env'
    rc = admitter.main(['--digest', '', '--project', PROJECT, '--sha', SHA, '--github-env', str(env_file)])
    assert rc == 0
    assert not env_file.exists()
    assert 'left untouched' in capsys.readouterr().out


def test_main_refusal_exits_nonzero(capsys):
    rc = admitter.main(['--digest', f'gcr.io/{PROJECT}/backend@{DIGEST}', '--project', PROJECT, '--sha', SHA])
    assert rc == 1
    assert 'ERROR' in capsys.readouterr().err
