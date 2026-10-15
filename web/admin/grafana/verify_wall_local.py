#!/usr/bin/env python3
"""Local-only Grafana 13.1.3 wall verification. Never reads Firebase/Stripe keys.

Select ro-prod ADC and the managed Docker socket in the calling shell first.
The serve command injects only the explicitly authorized PostHog/Shopify fields.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ADMIN = Path(__file__).resolve().parents[1]
RECORD = Path('/Users/dazheng/workspace/omi/data/run-2026-10-14-omi-tv-metrics')
NAME = 'omi-tv-v2-local'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def serve(replay: str | None):
    env = os.environ.copy()
    for path, names in [
        (Path.home()/'.hermes/.env', {'POSTHOG_PERSONAL_API_KEY'}),
        (Path.home()/'.local/share/hostctl/secrets/omi-shopify-data.env', {'SHOPIFY_STORE','SHOPIFY_ACCESS_TOKEN','SHOPIFY_CLIENT_ID','SHOPIFY_CLIENT_SECRET','SHOPIFY_API_VERSION'}),
    ]:
        for raw in path.read_text().splitlines():
            key, sep, value = raw.partition('=')
            key = key.removeprefix('export ').strip()
            if sep and key in names:
                env[key] = value.strip().strip('"').strip("'")
    for key in list(env):
        if key.startswith('FIREBASE_') or key in {'STRIPE_SECRET_KEY','GCP_BILLING_SA_JSON'}:
            env.pop(key, None)
    env.update(DEV_BYPASS_AUTH='1', POSTHOG_PROJECT_ID='302298', GRAFANA_ORIGIN='http://127.0.0.1:3207',
               OMI_TV_LOCAL_STRIPE_FIXTURE_PATH=str(ADMIN/'lib/__fixtures__/wall-stripe.json'))
    if replay:
        env['OMI_TV_LOCAL_FIXTURE_PATH'] = str(Path(replay).resolve())
    run('npm','run','dev','--','--hostname','127.0.0.1','--port','3107','--webpack',cwd=ADMIN,env=env)


def provision():
    # Unique project-owned name; intentionally no automatic replacement/removal.
    run('docker','run','-d','--name',NAME,'--label','com.omi.task=omi-tv-v2',
        '-p','127.0.0.1:3207:3000','-e','GF_PLUGINS_PREINSTALL=yesoreyeram-infinity-datasource@4.1.1',
        '-e','GF_AUTH_ANONYMOUS_ENABLED=true','-e','GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer',
        '-e','GF_AUTH_DISABLE_LOGIN_FORM=true','grafana/grafana:13.1.3')
    with tempfile.TemporaryDirectory(prefix='omi-tv-v2-') as directory:
        tmp = Path(directory)
        (tmp/'source.yaml').write_text('''apiVersion: 1
datasources:
  - name: Omi admin API
    uid: omi-admin-api
    type: yesoreyeram-infinity-datasource
    access: proxy
    jsonData:
      allowedHosts: [http://host.lima.internal:3107]
      httpHeaderName1: Authorization
    secureJsonData:
      httpHeaderValue1: Bearer dev-bypass-token
''')
        (tmp/'provider.yaml').write_text('''apiVersion: 1
providers:
  - name: local-omi-tv-v2
    type: file
    options:
      path: /var/lib/grafana/boards
''')
        board = json.loads((ADMIN/'grafana/dashboards/omi-tv-v2.json').read_text())
        for panel in board['panels']:
            for target in panel.get('targets',[]):
                target['url'] = target['url'].replace('http://127.0.0.1:8899','http://host.lima.internal:3107')
        (tmp/'board.json').write_text(json.dumps(board))
        run('docker','cp',str(tmp/'source.yaml'),f'{NAME}:/etc/grafana/provisioning/datasources/omi.yaml')
        run('docker','cp',str(tmp/'provider.yaml'),f'{NAME}:/etc/grafana/provisioning/dashboards/omi.yaml')
        run('docker','exec',NAME,'mkdir','-p','/var/lib/grafana/boards')
        run('docker','cp',str(tmp/'board.json'),f'{NAME}:/var/lib/grafana/boards/omi-tv-v2.json')
    run('docker','restart',NAME)


def screens():
    from playwright.sync_api import sync_playwright
    out = RECORD/'build-screens'
    out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        page.goto('http://127.0.0.1:3207/d/omi-tv-v2/omi-tv-v2?orgId=1&kiosk',wait_until='domcontentloaded',timeout=60000)
        page.get_by_text('Growth',exact=True).wait_for(timeout=60000)
        page.get_by_text('Weekly active people',exact=True).first.wait_for(timeout=60000)
        page.locator('svg[data-omi-card]').nth(22).wait_for(timeout=60000)
        page.evaluate('document.fonts.ready')
        page.wait_for_timeout(1000)
        for width,height in [(1440,1000),(1920,1080)]:
            page.set_viewport_size({'width':width,'height':height})
            page.wait_for_timeout(1000)
            clipped = page.locator('svg[data-omi-card]').evaluate_all('''svgs => svgs.flatMap(svg => Array.from(svg.querySelectorAll('text')).flatMap(t => {
              const b=t.getBoundingClientRect(), root=svg.getBoundingClientRect();
              return b.left < root.left || b.right > root.right || b.top < root.top || b.bottom > root.bottom ? [t.textContent] : [];
            }))''')
            overlap = page.locator('svg[data-omi-card]').evaluate_all('''svgs => svgs.flatMap(svg => {
              const title=svg.querySelector('text'), chip=svg.querySelector('rect[fill="#26374d"]');
              if (!title || !chip) return [];
              const b=title.getBoundingClientRect();return b.right > chip.getBoundingClientRect().left-5 ? [title.textContent] : [];
            })''')
            if overlap:
                raise RuntimeError(f'Card title overlaps its scope chip at {width}px: {overlap}')
            if clipped:
                raise RuntimeError(f'Card text outside its card at {width}px: {clipped}')
            diagnostics = page.get_by_text('Diagnostics · definitions and coverage',exact=True)
            if diagnostics.count() and diagnostics.bounding_box()['y'] < height:
                raise RuntimeError(f'Diagnostics visible above the fold at {width}px')
            page.screenshot(path=str(out/f'omi-tv-v2-rev1-{width}.png'))
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','provision','screens'])
    parser.add_argument('--replay',help='Optional local aggregate wall payload; source timestamps are preserved')
    args = parser.parse_args()
    if args.command == 'serve':
        serve(args.replay)
    elif args.command == 'provision':
        provision()
    else:
        screens()
