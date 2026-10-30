"""gcp_backend_listen_helm.yml listen_edge_image_digest: blank changes nothing; a value is a verified digest."""

import pytest

from scripts import admit_listen_edge_image as admitter

PROJECT = 'based-hardware'
HEAD = 'a' * 40  # the checked-out deploy source
OLDER = 'b' * 40  # an ancestor of HEAD (an earlier build-only train)
FOREIGN = 'c' * 40  # not in the repository / not contained by HEAD
DIGEST = 'sha256:' + 'd' * 64
REF = f'gcr.io/{PROJECT}/listen-edge@{DIGEST}'


def edge_config(revision=HEAD, env_sha=None):
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


def ancestry(contained=(HEAD, OLDER)):
    """A fake ``git merge-base --is-ancestor``: HEAD contains itself and OLDER, nothing else."""
    calls = []

    def check(revision, head):
        calls.append((revision, head))
        return head == HEAD and revision in contained

    check.calls = calls
    return check


def admit(raw, *, inspect, ancestor=None, sha=HEAD):
    return admitter.admit(raw, project=PROJECT, sha=sha, inspect=inspect, ancestor=ancestor or ancestry())


def test_blank_input_leaves_the_release_untouched_and_reads_nothing():
    inspect, ancestor = inspector({}), ancestry()
    assert admit('', inspect=inspect, ancestor=ancestor) == {}
    assert admit('   ', inspect=inspect, ancestor=ancestor) == {}
    assert inspect.calls == [] and ancestor.calls == []


def test_digest_built_from_the_checked_out_sha_is_admitted():
    outputs = admit(REF, inspect=inspector({REF: edge_config()}))
    assert outputs == {
        'LISTEN_EDGE_IMAGE_REPOSITORY': f'gcr.io/{PROJECT}/listen-edge',
        'LISTEN_EDGE_IMAGE_DIGEST': DIGEST,
        'LISTEN_EDGE_IMAGE_REVISION': HEAD,
    }


# The prod workflow checks out fresh main; the image was published by an
# earlier build-only train. Like listen's image_tag rule, an ancestor is fine.
def test_digest_built_from_an_ancestor_of_the_checkout_is_admitted():
    ancestor = ancestry()
    outputs = admit(REF, inspect=inspector({REF: edge_config(revision=OLDER)}), ancestor=ancestor)
    assert outputs['LISTEN_EDGE_IMAGE_REVISION'] == OLDER
    assert ancestor.calls == [(OLDER, HEAD)]


@pytest.mark.parametrize(
    'raw',
    [
        f'gcr.io/{PROJECT}/listen-edge:abc123456789',  # a tag, not a digest
        f'gcr.io/based-hardware-dev/listen-edge@{DIGEST}',  # another project's registry
        f'gcr.io/{PROJECT}/backend@{DIGEST}',  # another image
        f'gcr.io/{PROJECT}/backend-realtime@{DIGEST}',
        f'gcr.io/{PROJECT}/listen-edge@sha256:{"d" * 63}',  # short digest
        f'gcr.io/{PROJECT}/listen-edge@sha256:{"D" * 64}',  # uppercase hex
        f'listen-edge={REF}',  # the service_images pair shape
        f'{REF} {REF}',  # a list
        f'{REF},{REF}',
    ],
)
def test_malformed_or_foreign_references_are_refused_before_any_registry_read(raw):
    inspect, ancestor = inspector({}), ancestry()
    with pytest.raises(admitter.ListenEdgeImageError):
        admit(raw, inspect=inspect, ancestor=ancestor)
    assert inspect.calls == [] and ancestor.calls == []


def test_digest_built_from_a_commit_the_checkout_does_not_contain_is_refused():
    ancestor = ancestry()
    with pytest.raises(admitter.ListenEdgeImageError, match='not a commit in this repository that the checked-out'):
        admit(REF, inspect=inspector({REF: edge_config(revision=FOREIGN)}), ancestor=ancestor)
    assert ancestor.calls == [(FOREIGN, HEAD)]


def test_revision_label_without_matching_release_env_is_refused_before_the_ancestry_check():
    ancestor = ancestry()
    config = edge_config(revision=OLDER, env_sha=HEAD)
    with pytest.raises(admitter.ListenEdgeImageError, match='OMI_RELEASE_SHA'):
        admit(REF, inspect=inspector({REF: config}), ancestor=ancestor)
    assert ancestor.calls == []


@pytest.mark.parametrize(
    'config',
    [
        {'Env': [f'OMI_RELEASE_SHA={HEAD}']},  # unlabelled
        {'Labels': {'org.opencontainers.image.revision': 'abc1234'}, 'Env': ['OMI_RELEASE_SHA=abc1234']},  # short
        {
            'Labels': {'org.opencontainers.image.revision': 'unknown'},
            'Env': ['OMI_RELEASE_SHA=unknown'],
        },  # Dockerfile default
    ],
)
def test_image_without_a_full_revision_label_is_refused(config):
    ancestor = ancestry()
    with pytest.raises(admitter.ListenEdgeImageError, match='not labelled'):
        admit(REF, inspect=inspector({REF: config}), ancestor=ancestor)
    assert ancestor.calls == []


# `imagetools inspect --format '{{json .Image.Config}}'` prints null for a
# multi-arch index; that must be a clean refusal, not an AttributeError.
def test_image_without_a_single_image_config_is_refused(capsys):
    ancestor = ancestry()
    with pytest.raises(admitter.ListenEdgeImageError, match='no single-image config'):
        admit(REF, inspect=inspector({REF: None}), ancestor=ancestor)
    assert ancestor.calls == []


def test_short_or_malformed_checked_out_sha_is_refused():
    with pytest.raises(admitter.ListenEdgeImageError, match='40-character'):
        admit(REF, inspect=inspector({REF: edge_config()}), sha='abc1234')


def test_registry_read_failure_is_an_admission_error():
    def failing(ref):
        raise admitter.ListenEdgeImageError(f'cannot read the image config of {ref}')

    with pytest.raises(admitter.ListenEdgeImageError, match='cannot read'):
        admit(REF, inspect=failing)


def test_main_writes_github_env_and_reports(tmp_path, monkeypatch, capsys):
    env_file = tmp_path / 'env'
    monkeypatch.setattr(admitter, 'inspect_image_config', lambda ref: edge_config(revision=OLDER))
    monkeypatch.setattr(admitter, 'is_ancestor', lambda revision, head: (revision, head) == (OLDER, HEAD))
    rc = admitter.main(['--digest', REF, '--project', PROJECT, '--sha', HEAD, '--github-env', str(env_file)])
    assert rc == 0
    assert env_file.read_text() == (
        f'LISTEN_EDGE_IMAGE_REPOSITORY=gcr.io/{PROJECT}/listen-edge\n'
        f'LISTEN_EDGE_IMAGE_DIGEST={DIGEST}\n'
        f'LISTEN_EDGE_IMAGE_REVISION={OLDER}\n'
    )
    assert 'admitted' in capsys.readouterr().out


def test_main_blank_digest_exits_zero_without_writing(tmp_path, capsys):
    env_file = tmp_path / 'env'
    rc = admitter.main(['--digest', '', '--project', PROJECT, '--sha', HEAD, '--github-env', str(env_file)])
    assert rc == 0
    assert not env_file.exists()
    assert 'left untouched' in capsys.readouterr().out


def test_main_refusal_exits_nonzero(capsys):
    rc = admitter.main(['--digest', f'gcr.io/{PROJECT}/backend@{DIGEST}', '--project', PROJECT, '--sha', HEAD])
    assert rc == 1
    assert 'ERROR' in capsys.readouterr().err
