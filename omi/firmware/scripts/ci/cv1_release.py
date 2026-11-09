#!/usr/bin/env python3
"""CV1 QA packaging and promotion. Only `publish` writes to GitHub."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct
import tempfile
import zipfile

WORKFLOW = '.github/workflows/firmware_release.yml'
ARTIFACT = 'cv1-qa-release'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def version(value, conf, emergency=False):
    if not value:
        value = re.search(r'^CONFIG_BT_DIS_FW_REV_STR="([^"]+)"', conf.read_text(), re.M)[1]
    value = value.removeprefix('v')
    require(re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value), 'Expected version X.Y.Z')
    major, minor, patch = map(int, value.split('.'))
    require(major <= 255 and minor <= 255 and patch <= 65535, 'Version exceeds MCUboot header fields')
    require(
        emergency or not (major == 3 and minor == 0 and 90 <= patch <= 99),
        '3.0.90-3.0.99 is reserved; set emergency_revert explicitly',
    )
    return value


def asset_names(ver):
    return [f'Omi_CV1_OTA_v{ver}.zip', f'Omi_CV1_v{ver}.hex', f'Omi_CV1_v{ver}_CPUNET.hex']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ota_manifest(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), 'Duplicate zip members')
    manifest = json.loads(archive.read('manifest.json'))
    require(manifest.get('format-version') == 1, 'Unsupported manifest format')
    files = manifest['files']
    require(len(files) in (1, 2), 'Expected app and optional network image')
    expected = {'0': 'omi.signed.bin', '1': 'ipc_radio.bin'}
    indexes = [str(f['image_index']) for f in files]
    require('0' in indexes and len(set(indexes)) == len(indexes), 'Missing or duplicate app image')
    for item in files:
        require(expected.get(str(item['image_index'])) == item['file'], 'Unexpected image role/file')
        require(item['size'] == len(archive.read(item['file'])), 'Manifest size mismatch')
    require(set(names) == {'manifest.json', *(f['file'] for f in files)}, 'Unexpected zip members')
    return manifest


def repackage(source, target, include_network=False):
    with zipfile.ZipFile(source) as archive:
        manifest = ota_manifest(archive)
        if not include_network:
            manifest['files'] = [f for f in manifest['files'] if str(f['image_index']) == '0']
        else:
            require(len(manifest['files']) == 2, 'Network opt-in requires image 1')
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            for item in manifest['files']:
                out.writestr(item['file'], archive.read(item['file']))
            out.writestr('manifest.json', json.dumps(manifest, indent=4) + '\n')


def validate_signed_version(archive, ver):
    image = archive.read('omi.signed.bin')
    require(len(image) >= 32 and struct.unpack_from('<I', image)[0] == 0x96F3B83D, 'Invalid MCUboot app header')
    require(
        struct.unpack_from('<BBH', image, 20) == tuple(map(int, ver.split('.'))),
        'Signed MCUboot app version must equal the release version',
    )


def stage(build, out, ver, include_network, context):
    out.mkdir(parents=True, exist_ok=False)
    names = asset_names(ver)
    repackage(build / 'dfu_application.zip', out / names[0], include_network)
    with zipfile.ZipFile(out / names[0]) as archive:
        validate_signed_version(archive, ver)
        signed_sha256 = hashlib.sha256(archive.read('omi.signed.bin')).hexdigest()
    shutil.copyfile(build / 'merged.hex', out / names[1])
    shutil.copyfile(build / 'merged_CPUNET.hex', out / names[2])
    require(all((out / name).stat().st_size for name in names), 'Empty release asset')
    provenance = dict(
        context,
        mode='build-only',
        version=ver,
        include_network_core=include_network,
        signed_sha256=signed_sha256,
        sha256={name: digest(out / name) for name in names},
    )
    (out / 'qa-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


def validate_run(run, workflow_id, repo, sha, run_id, run_attempt):
    require(str(run['id']) == run_id, 'QA run ID mismatch')
    require(str(run['run_attempt']) == run_attempt, 'QA run attempt mismatch')
    require(run['repository']['full_name'] == repo, 'QA repository mismatch')
    require(run['workflow_id'] == workflow_id and run['path'] == WORKFLOW, 'QA run must use this workflow')
    require(run['event'] == 'workflow_dispatch', 'QA run must be manually dispatched')
    require(run['status'] == 'completed' and run['conclusion'] == 'success', 'QA run must finish successfully')
    require(run['head_sha'] == sha, 'QA source SHA must equal the published ref SHA')


def validate_assets(out, run, ver, include_network, tested_signed_sha256):
    data = json.loads((out / 'qa-provenance.json').read_text())
    expected = {
        'mode': 'build-only',
        'version': ver,
        'include_network_core': include_network,
        'sha': run['head_sha'],
        'run_id': str(run['id']),
        'run_attempt': str(run['run_attempt']),
        'workflow': WORKFLOW,
        'repository': run['repository']['full_name'],
    }
    require(
        all(data.get(key) == value for key, value in expected.items()),
        'QA provenance mismatch (mode/version/source/attempt/network)',
    )
    names = asset_names(ver)
    require(set(p.name for p in out.iterdir()) == {*names, 'qa-provenance.json'}, 'Unexpected QA assets')
    require(data.get('sha256') == {name: digest(out / name) for name in names}, 'QA asset checksum mismatch')
    with zipfile.ZipFile(out / names[0]) as archive:
        manifest = ota_manifest(archive)
        validate_signed_version(archive, ver)
        require(len(manifest['files']) == (2 if include_network else 1), 'QA OTA image count mismatch')
        require(
            hashlib.sha256(archive.read('omi.signed.bin')).hexdigest() == tested_signed_sha256.lower(),
            'Bench-tested signed image SHA-256 mismatch',
        )


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def validate_promotion_inputs(run_id, run_attempt, tested_signed_sha256):
    require(re.fullmatch(r'[1-9][0-9]*', run_id or ''), 'Publishing requires qa_run_id')
    require(re.fullmatch(r'[1-9][0-9]*', run_attempt or ''), 'Publishing requires qa_run_attempt')
    require(re.fullmatch(r'[0-9a-fA-F]{64}', tested_signed_sha256 or ''), 'Publishing requires tested_signed_sha256')


def validate_policy(rollout, blocked, emergency=False):
    require(re.fullmatch(r'[0-9]+', rollout) and 0 <= int(rollout) <= 100, 'rollout_percent must be 0-100')
    require(emergency or int(rollout) <= 1, 'Normal publish rollout_percent must be 0 or 1')
    require(blocked in ('true', 'false'), 'blocked must be true or false')


def promote(out, ver, include_network, run_id, run_attempt, tested_signed_sha256, repo, sha, ref):
    require(ref == 'refs/heads/main', 'Publishing is allowed only from main')
    validate_promotion_inputs(run_id, run_attempt, tested_signed_sha256)
    workflow = json.loads(gh('api', f'repos/{repo}/actions/workflows/firmware_release.yml'))
    run = json.loads(gh('api', f'repos/{repo}/actions/runs/{run_id}/attempts/{run_attempt}'))
    validate_run(run, workflow['id'], repo, sha, run_id, run_attempt)
    # Do not rebuild or repackage after download: these are the bytes tested on the bench.
    with tempfile.TemporaryDirectory() as temp:
        download = Path(temp)
        # The artifact API is run-wide, so only use the attempt-scoped name.
        gh(
            'run',
            'download',
            run_id,
            '--repo',
            repo,
            '--name',
            f'{ARTIFACT}-{run_id}-{run_attempt}',
            '--dir',
            str(download),
        )
        validate_assets(download, run, ver, include_network, tested_signed_sha256)
        shutil.copytree(download, out)
        (out.parent / 'cv1-validated-run.json').write_text(json.dumps({'run': run, 'workflow_id': workflow['id']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'stage', 'promote', 'publish'])
    args = parser.parse_args()
    env = os.environ
    conf = Path('omi/firmware/omi/omi.conf')
    ver = version(env.get('VERSION_INPUT', ''), conf, env.get('EMERGENCY_REVERT') == 'true')
    publishing = env.get('PUBLISH') == 'publish'
    include_network = env.get('INCLUDE_NETWORK_CORE') == 'true'
    out = Path(env.get('OUT', str(Path(env.get('RUNNER_TEMP', '.')) / 'cv1-assets')))
    if args.command == 'prepare':
        if publishing:
            require(env['GITHUB_REF'] == 'refs/heads/main', 'Publishing is allowed only from main')
            validate_promotion_inputs(
                env.get('QA_RUN_ID', ''), env.get('QA_RUN_ATTEMPT', ''), env.get('TESTED_SIGNED_SHA256', '')
            )
        else:
            require(
                not any(env.get(key) for key in ('QA_RUN_ID', 'QA_RUN_ATTEMPT', 'TESTED_SIGNED_SHA256')),
                'QA promotion inputs are only valid when publishing',
            )
            text = conf.read_text()
            for key in ('CONFIG_BT_DIS_FW_REV_STR', 'CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION'):
                text, count = re.subn(rf'^{key}=.*$', f'{key}="{ver}"', text, flags=re.M)
                if not count:
                    text += f'\n{key}="{ver}"\n'
            conf.write_text(text)
        rollout = env.get('ROLLOUT_PERCENT', '1')
        validate_policy(rollout, env.get('BLOCKED', 'false'), env.get('EMERGENCY_REVERT') == 'true')
        with open(env['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'ver={ver}\ntag=Omi_CV1_v{ver}\n')
    elif args.command == 'stage':
        require(not publishing and not env.get('QA_RUN_ID'), 'Only build-only runs may stage QA assets')
        context = {
            'sha': env['GITHUB_SHA'],
            'run_id': env['GITHUB_RUN_ID'],
            'run_attempt': env['GITHUB_RUN_ATTEMPT'],
            'workflow': WORKFLOW,
            'repository': env['GITHUB_REPOSITORY'],
        }
        stage(Path(env['BUILD']), out, ver, include_network, context)
    elif args.command == 'promote':
        require(publishing, 'Promotion requires publish=publish')
        promote(
            out,
            ver,
            include_network,
            env.get('QA_RUN_ID', ''),
            env.get('QA_RUN_ATTEMPT', ''),
            env.get('TESTED_SIGNED_SHA256', ''),
            env['GITHUB_REPOSITORY'],
            env['GITHUB_SHA'],
            env['GITHUB_REF'],
        )
    else:
        require(publishing and env['GITHUB_REF'] == 'refs/heads/main', 'Publishing is allowed only from main')
        validate_promotion_inputs(
            env.get('QA_RUN_ID', ''), env.get('QA_RUN_ATTEMPT', ''), env.get('TESTED_SIGNED_SHA256', '')
        )
        validate_policy(
            env.get('ROLLOUT_PERCENT', '1'), env.get('BLOCKED', 'false'), env.get('EMERGENCY_REVERT') == 'true'
        )
        # Recheck the promotion receipt and bytes immediately before the write.
        receipt = json.loads((out.parent / 'cv1-validated-run.json').read_text())
        validate_run(
            receipt['run'],
            receipt['workflow_id'],
            env['GITHUB_REPOSITORY'],
            env['GITHUB_SHA'],
            env['QA_RUN_ID'],
            env['QA_RUN_ATTEMPT'],
        )
        validate_assets(out, receipt['run'], ver, include_network, env['TESTED_SIGNED_SHA256'])
        tag = f'Omi_CV1_v{ver}'
        repo = env['GITHUB_REPOSITORY']
        sha = receipt['run']['head_sha']
        # Atomic create: an existing ref (even without a release) must fail.
        gh('api', '--method', 'POST', f'repos/{repo}/git/refs', '-f', f'ref=refs/tags/{tag}', '-f', f'sha={sha}')
        tag_ref = json.loads(gh('api', f'repos/{repo}/git/ref/tags/{tag}'))
        require(tag_ref['object']['type'] == 'commit' and tag_ref['object']['sha'] == sha, 'Release tag SHA mismatch')
        gh(
            'release',
            'create',
            tag,
            '--repo',
            repo,
            '--draft',
            '--verify-tag',
            '--title',
            f'Omi CV1 Firmware v{ver}',
            '--notes-file',
            env['BODY_FILE'],
            *(str(out / name) for name in asset_names(ver)),
        )
        # GET releases/tags/{tag} never returns drafts (404), so read the draft by tag through gh.
        created = json.loads(gh('release', 'view', tag, '--repo', repo, '--json', 'isDraft,tagName'))
        require(created['isDraft'] and created['tagName'] == tag, 'Release tag or draft mismatch')
        tag_ref = json.loads(gh('api', f"repos/{repo}/git/ref/tags/{created['tagName']}"))
        require(tag_ref['object']['type'] == 'commit' and tag_ref['object']['sha'] == sha, 'Release tag SHA mismatch')
        gh('release', 'edit', tag, '--repo', repo, '--draft=false')


if __name__ == '__main__':
    main()
