"""One original cold image and conditional-version predicate for both SDK paths."""

from database.jobstore.authority import AuthorityRefused, fingerprint


def packet_for(namespace, row, recording, original):
    seq, epoch, family, identity, operation, owner, body = row
    if family == 'docs':
        raise AuthorityRefused('staging document copy requires completed cold erasure; no live reverse adapter')
    if operation != 'put' or body is None:
        raise AuthorityRefused('cold delete requires real destructive-unit custody')
    if body.get('namespace') != namespace:
        raise AuthorityRefused('cold body namespace changed')
    return dict(
        namespace=namespace,
        epoch=epoch,
        seq=seq,
        family=family,
        identity=identity,
        owner_key=owner,
        recording_id=recording,
        cold_only=True,
        body=body,
        source_fingerprint=fingerprint(row),
        original_deadlines={
            sid: job['typed_provider']['custody_deadline'] for sid, job in original['intent']['payload']['jobs'].items()
        },
    )


def needs_write(previous, packet):
    if not previous:
        return True
    if (
        any(previous.get(key) != packet[key] for key in ('owner_key', 'identity', 'recording_id', 'namespace'))
        or previous.get('cold_only') is not True
    ):
        raise AuthorityRefused('cold destination ownership/identity changed')
    version = (previous.get('epoch', -1), previous.get('seq', -1))
    target = (packet['epoch'], packet['seq'])
    if version > target:
        return False
    if version == target:
        if previous != packet:
            raise AuthorityRefused('cold same-version payload changed')
        return False
    return True
