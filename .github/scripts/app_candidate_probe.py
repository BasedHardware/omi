#!/usr/bin/env python3
"""Fail-closed, read-only app candidate admission. Never promotes traffic."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

from verify_desktop_backend_image_lineage import (
    IMAGE_MEDIA_TYPES, INDEX_MEDIA_TYPES, LineageError, verify_lineage,
)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(*args):
    return subprocess.check_output(args, text=True, timeout=180).strip()


def cloud(kind, name, args):
    fields = ('status.traffic' if kind == 'services' else
              'metadata.name,status.imageDigest,status.conditions,spec.containers[0].image')
    return json.loads(run('gcloud', 'run', kind, 'describe', name,
                          '--project', args.project, '--region', args.region, f'--format=json({fields})'))


def traffic(service):
    rows = service.get('status', {}).get('traffic', [])
    result = sorted([r.get('revisionName'), r['percent']] for r in rows if r.get('percent', 0) > 0)
    require(result and sum(p for _, p in result) == 100, 'traffic identity unavailable')
    require(all(name for name, _ in result), 'unresolved traffic identity')
    return result


def ready(revision):
    return any(c.get('type') == 'Ready' and c.get('status') == 'True'
               for c in revision.get('status', {}).get('conditions', []))


def resolve_lineage(build_image, manifest):
    """Resolve one runnable child; provenance attestations are not runtime images."""
    require(isinstance(manifest, dict), 'registry manifest is not an object')
    checked_manifest = manifest
    if manifest.get('mediaType') in INDEX_MEDIA_TYPES:
        descriptors = manifest.get('manifests')
        require(isinstance(descriptors, list), 'image index descriptors missing')
        descriptors = [d for d in descriptors if not (
            isinstance(d, dict) and isinstance(d.get('annotations'), dict) and
            d['annotations'].get('vnd.docker.reference.type') == 'attestation-manifest')]
        runnable = [d for d in descriptors if isinstance(d, dict) and
                    isinstance(d.get('platform'), dict) and
                    d['platform'].get('os') == 'linux' and
                    d['platform'].get('architecture') == 'amd64']
        require(len(runnable) == 1, 'image index must select exactly one runnable linux/amd64 child')
        runtime_image = build_image.split('@')[0] + '@' + str(runnable[0].get('digest'))
        checked_manifest = {**manifest, 'manifests': descriptors}
    else:
        require(manifest.get('mediaType') in IMAGE_MEDIA_TYPES, 'unsupported image manifest')
        runtime_image = build_image
    try:
        evidence = verify_lineage(build_image_reference=build_image,
                                  runtime_image_reference=runtime_image, manifest=checked_manifest)
    except LineageError as error:
        raise RuntimeError(str(error)) from error
    return {key: evidence[key] for key in ['build_image', 'runtime_image', 'lineage']}


def registry_lineage(build_image):
    return resolve_lineage(build_image, json.loads(
        run('docker', 'buildx', 'imagetools', 'inspect', '--raw', build_image)))


def check_state(service, revision, args, baseline, runtime_image):
    require(traffic(service) == traffic(baseline), 'serving baseline changed')
    require(all(name != args.revision for name, _ in traffic(service)), 'candidate has traffic')
    require(ready(revision), 'candidate is not Ready')
    require(revision.get('metadata', {}).get('name') == args.revision, 'revision mismatch')
    require(revision.get('status', {}).get('imageDigest') == runtime_image, 'candidate runtime image mismatch')
    require(revision.get('spec', {}).get('containers', [{}])[0].get('image') in {args.image, runtime_image},
            'candidate image is outside verified index/runtime lineage')


def check_image(image, source, carrier):
    require(image.get('Os') == 'linux' and image.get('Architecture') == 'amd64', 'image platform mismatch')
    labels = image.get('Config', {}).get('Labels', {}) or {}
    require(labels.get('org.opencontainers.image.revision') == source, 'image source mismatch')
    require(labels.get('me.omi.carrier-source') == carrier, 'image carrier mismatch')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def framed(status, headers, body, helper):
    require(status == 200 and bool(body), 'empty/non-200 candidate response')
    require(headers.get('x-frame-options') == ('SAMEORIGIN' if helper else 'DENY'), 'framing mismatch')
    expected = "frame-ancestors 'self'" if helper else "frame-ancestors 'none'"
    require(expected in headers.get('content-security-policy', ''), 'CSP mismatch')
    if helper:
        require(headers.get('cache-control') == 'no-store', 'helper cache mismatch')


def candidate_gets(base):
    require(re.fullmatch(r'https://[a-z0-9-]+\.a\.run\.app', base) is not None,
            'candidate URL is not an exact Cloud Run URL')
    rows = []
    opener = urllib.request.build_opener(NoRedirect)
    for path in ['/login', '/__/auth/iframe', '/__/auth/iframe.js', '/__/auth/handler', '/__/auth/handler.js']:
        with opener.open(base + path, timeout=30) as response:
            body = response.read(2_000_001)
            require(len(body) <= 2_000_000, 'candidate response exceeds probe bound')
            headers = {k.lower(): v for k, v in response.headers.items()}
            framed(response.status, headers, body, path != '/login')
            rows.append({'path': path, 'status': response.status, 'sha256': hashlib.sha256(body).hexdigest()})
    return rows


def synthetic(image, hosting):
    """Exercise the exact image with networking disabled and synthetic callbacks only."""
    preload = Path(__file__).with_name('app_candidate_probe_preload.ts')
    container = None
    # Docker can mount an individual file from this trusted carrier checkout.
    try:
        container = run('docker', 'run', '-d', '--network=none', '--platform=linux/amd64',
                        '--mount', f'type=bind,src={preload.resolve()},dst=/probe/preload.ts,readonly',
                        '-e', f'PROBE_HOST={hosting}', '-e', 'PROBE_CAPTURE=/tmp/probe.jsonl',
                        image, 'bun', '--preload', '/probe/preload.ts', '.moonshine/server.ts')
        require(re.fullmatch('[a-f0-9]{64}', container) is not None, 'container identity missing')
        for attempt in range(30):
            try:
                output = run('docker', 'exec', container, 'bun', '-e',
                             "const r=await fetch('http://127.0.0.1:3000/login',{signal:AbortSignal.timeout(2000)});process.exit(r.status===200?0:1)")
                break
            except subprocess.CalledProcessError:
                require(attempt < 29, 'probe container unavailable')
                time.sleep(0.2)
        js = r"""
const check=(ok,m)=>{if(!ok)throw Error(m)};
const query='?state=a%2Bb%26c&task=A&task=B&task=C&empty=';
const body='code=synthetic%2Bcode&state=abc%26xyz&duplicate=1&duplicate=2';
for(const method of ['GET','POST']) {
 const r=await fetch('http://127.0.0.1:3000/__/auth/handler'+query,{
 method,redirect:'manual',signal:AbortSignal.timeout(5000),...(method==='POST'?{body}:{}),
 headers:{Accept:'text/html','Content-Type':'application/x-www-form-urlencoded',Cookie:'synthetic=private',
 Authorization:'Bearer synthetic','X-Probe-Private':'excluded'}});
 check(r.status===(method==='POST'?302:200),'status');
 check(r.headers.get('x-frame-options')==='SAMEORIGIN','XFO');
 check(r.headers.get('content-security-policy')==="script-src 'self'; frame-ancestors 'self'",'CSP');
 check(r.headers.get('cache-control')==='no-store','cache');
 if(method==='POST')check(r.headers.get('location')==='https://accounts.google.com/synthetic-probe','redirect');
 else check(await r.text()==='synthetic-helper-response','body');
}
const captures=(await Bun.file('/tmp/probe.jsonl').text()).trim().split('\n').map(JSON.parse);
check(captures.length===2,'unexpected outbound');
for(const [i,c] of captures.entries()) {
 check(c.url==='https://'+process.env.PROBE_HOST+'/__/auth/handler'+query,'query');
 check(c.method===(i?'POST':'GET')&&c.redirect==='manual','method/redirect');
 check(JSON.stringify(Object.keys(c.headers).sort())===JSON.stringify(['accept','content-type']),'header exclusion');
 check(c.body===(i?Buffer.from(body).toString('base64'):null),'POST bytes');
}
const login=await fetch('http://127.0.0.1:3000/login',{signal:AbortSignal.timeout(5000)});
check(login.status===200&&login.headers.get('x-frame-options')==='DENY','login');
check(login.headers.get('content-security-policy')==="frame-ancestors 'none'",'login CSP');
console.log(JSON.stringify({synthetic:'PASS',captures:captures.length,network:'none'}));
"""
        return json.loads(run('docker', 'exec', container, 'bun', '-e', js))
    finally:
        if container and re.fullmatch('[a-f0-9]{64}', container):
            subprocess.run(['docker', 'rm', '-f', container], check=True, timeout=30, stdout=subprocess.DEVNULL)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['baseline', 'probe', 'recheck'])
    for name in ['project', 'region', 'service', 'baseline']:
        p.add_argument('--' + name, required=True)
    for name in ['revision', 'image', 'source', 'carrier', 'tag', 'hosting', 'receipt']:
        p.add_argument('--' + name)
    args = p.parse_args()
    service = cloud('services', args.service, args)
    baseline_path = Path(args.baseline)
    if args.mode == 'baseline':
        require(len(traffic(service)) == 1, 'baseline must have one 100-percent revision')
        require(ready(cloud('revisions', traffic(service)[0][0], args)), 'rollback baseline not Ready')
        baseline_path.write_text(json.dumps({'status': {'traffic': service['status']['traffic']}}))
        return
    require(all([args.revision, args.image, args.source, args.carrier, args.receipt]), 'identity arguments missing')
    require(re.fullmatch('[a-f0-9]{40}', args.source) and re.fullmatch('[a-f0-9]{40}', args.carrier), 'invalid source')
    require(re.fullmatch(r'gcr\.io/[a-z0-9-]+/[a-z0-9-]+@sha256:[a-f0-9]{64}', args.image), 'invalid image digest')
    baseline = json.loads(baseline_path.read_text())
    lineage = registry_lineage(args.image)
    runtime_image = lineage['runtime_image']['reference']
    revision = cloud('revisions', args.revision, args)
    check_state(service, revision, args, baseline, runtime_image)
    receipt_path = Path(args.receipt)
    identity = {k: getattr(args, k) for k in ['revision', 'image', 'source', 'carrier', 'service', 'project', 'region']}
    identity['runtime_image'] = runtime_image
    if args.mode == 'recheck':
        receipt = json.loads(receipt_path.read_text())
        require(receipt.get('identity') == identity and receipt.get('result') == 'PASS', 'probe receipt mismatch')
        require(receipt.get('lineage') == lineage, 'probe receipt lineage mismatch')
        require(receipt.get('baseline') == traffic(baseline), 'receipt baseline mismatch')
        return
    require(args.hosting and re.fullmatch(r'[a-z0-9-]+\.firebaseapp\.com', args.hosting), 'invalid Firebase host')
    run('docker', 'pull', '--platform=linux/amd64', runtime_image)
    image = json.loads(run('docker', 'image', 'inspect', runtime_image))[0]
    require(runtime_image in image.get('RepoDigests', []), 'pulled runtime image digest mismatch')
    check_image(image, args.source, args.carrier)
    synthetic_result = synthetic(runtime_image, args.hosting)
    base = run('python3', 'backend/scripts/resolve_cloud_run_tagged_url.py', '--project', args.project,
               '--region', args.region, '--service', args.service, '--revision', args.revision, '--tag', args.tag)
    gets = candidate_gets(base)
    check_state(cloud('services', args.service, args), cloud('revisions', args.revision, args),
                args, baseline, runtime_image)
    # JSON normalizes traffic tuples to lists for the recheck.
    receipt_path.write_text(json.dumps({'identity': identity, 'lineage': lineage,
                                       'baseline': traffic(baseline), 'result': 'PASS',
                                       'synthetic': synthetic_result, 'candidate_gets': gets}, indent=2))
    print('APP_CANDIDATE_PROBE PASS ' + json.dumps(identity))


if __name__ == '__main__':
    main()
