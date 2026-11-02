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
NAME = 'omi-tv-v3-local'


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
    run('docker','run','-d','--name',NAME,'--label','com.omi.task=omi-tv-v3',
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
        run('docker','cp',str(tmp/'source.yaml'),f'{NAME}:/etc/grafana/provisioning/datasources/omi.yaml')
        run('docker','cp',str(tmp/'provider.yaml'),f'{NAME}:/etc/grafana/provisioning/dashboards/omi.yaml')
        run('docker','exec',NAME,'mkdir','-p','/var/lib/grafana/boards')
    reload()
    run('docker','restart',NAME)


def reload():
    """Copy the current board into the existing local container (file provider rescans)."""
    with tempfile.TemporaryDirectory(prefix='omi-tv-v3-') as directory:
        board = json.loads((ADMIN/'grafana/dashboards/omi-tv-v2.json').read_text())
        for panel in board['panels']:
            for target in panel.get('targets',[]):
                target['url'] = target['url'].replace('http://127.0.0.1:8899','http://host.lima.internal:3107')
        path = Path(directory)/'board.json'
        path.write_text(json.dumps(board))
        run('docker','cp',str(path),f'{NAME}:/var/lib/grafana/boards/omi-tv-v2.json')


def screens(out: Path | None = None):
    """Render the real board; fail on scroll at 1920×1080, truncated titles or panel errors."""
    from playwright.sync_api import sync_playwright
    out = out or RECORD/'build-screens'
    out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width,height in [(1920,1080),(1440,900)]:
            page = browser.new_page(viewport={'width':width,'height':height},device_scale_factor=1)
            page.goto('http://127.0.0.1:3207/d/omi-tv-v2/omi-tv-v2?orgId=1&kiosk',wait_until='networkidle',timeout=120000)
            page.get_by_text('Data & coverage',exact=True).wait_for(timeout=60000)
            page.wait_for_function("!document.body.innerText.includes('Loading…')",timeout=120000)
            page.evaluate('document.fonts.ready')
            page.wait_for_timeout(2000)
            truncated = page.locator('[data-testid="data-testid header-container"] h2').evaluate_all(
                'hs => hs.filter(h => h.scrollWidth > h.clientWidth + 1).map(h => h.textContent)')
            if truncated:
                raise RuntimeError(f'Truncated panel titles at {width}px: {truncated}')
            errors = [t for t in ('Unable to find field','Data does not have','No data') if page.get_by_text(t).count()]
            if errors:
                raise RuntimeError(f'Panel errors at {width}px: {errors}')
            # A kiosk TV cannot scroll: neither the page nor any panel (legend, table) may overflow.
            overflow = page.evaluate("() => Array.from(document.querySelectorAll('*'))"
                                     ".filter(e => getComputedStyle(e).overflowY !== 'visible' && e.scrollHeight - e.clientHeight > 4)"
                                     ".map(e => (e.closest('[data-viz-panel-key]')?.innerText || 'page').split('\\n')[0])")
            if width == 1920 and overflow:
                raise RuntimeError(f'Content overflows at 1920×1080: {overflow}')
            page.screenshot(path=str(out/f'omi-tv-v3-{width}.png'))
            page.close()
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','provision','reload','screens'])
    parser.add_argument('--replay',help='Optional local aggregate wall payload; source timestamps are preserved')
    parser.add_argument('--out',type=Path,help='Screenshot directory (default: the run record build-screens/)')
    args = parser.parse_args()
    if args.command == 'serve':
        serve(args.replay)
    elif args.command == 'provision':
        provision()
    elif args.command == 'reload':
        reload()
    else:
        screens(args.out)
