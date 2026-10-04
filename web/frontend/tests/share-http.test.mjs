import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const app = fileURLToPath(new URL('../', import.meta.url));
const fixture = JSON.parse(
  readFileSync(new URL('../src/__fixtures__/agent-share.sample.json', import.meta.url)),
);

test(
  'actual share HTTP representations and human rendering, without live meeting data',
  { timeout: 180000 },
  async () => {
    const generatedFiles = ['tsconfig.json', 'next-env.d.ts'].map((name) => {
      const path = new URL(`../${name}`, import.meta.url);
      return [path, readFileSync(path)];
    });
    let shared = true;
    const backend = createServer((req, res) => {
      res.setHeader('Content-Type', 'application/json');
      if (!shared || req.url.includes('missing')) {
        res.writeHead(404).end('{}');
      } else if (req.url.endsWith('/screenshots')) {
        res.end(JSON.stringify({ revision: 0, strip: [] }));
      } else if (req.url === '/v1/conversations/synthetic-share/shared') {
        res.end(JSON.stringify(fixture));
      } else {
        res.writeHead(404).end('{}');
      }
    });
    backend.listen(0, '127.0.0.1');
    await once(backend, 'listening');
    const portProbe = createServer();
    portProbe.listen(0, '127.0.0.1');
    await once(portProbe, 'listening');
    const port = portProbe.address().port;
    await new Promise((resolve) => portProbe.close(resolve));
    const base = `http://127.0.0.1:${port}`;
    let logs = '';
    const child = spawn(
      process.execPath,
      [
        'node_modules/next/dist/bin/next',
        'dev',
        '--webpack',
        '--hostname',
        '127.0.0.1',
        '--port',
        String(port),
      ],
      {
        cwd: app,
        env: {
          ...process.env,
          NEXT_PUBLIC_FIREBASE_API_KEY: 'synthetic-test-key',
          NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: 'synthetic.invalid',
          NEXT_PUBLIC_FIREBASE_PROJECT_ID: 'synthetic-share',
          NODE_OPTIONS: `${process.env.NODE_OPTIONS || ''} ${[
            '--no-experimental-strip-types',
            '--no-experimental-require-module',
          ]
            .filter((flag) => process.allowedNodeEnvironmentFlags.has(flag))
            .join(' ')}`,
          API_URL: `http://127.0.0.1:${backend.address().port}`,
          WEB_URL: base,
          NEXT_TELEMETRY_DISABLED: '1',
          NEXT_PUBLIC_POSTHOG_KEY: '',
          NEXT_FONT_GOOGLE_MOCKED_RESPONSES: fileURLToPath(
            new URL('./font-mock.cjs', import.meta.url),
          ),
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );
    child.stdout.on('data', (chunk) => {
      logs += chunk;
    });
    child.stderr.on('data', (chunk) => {
      logs += chunk;
    });
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(
          () => reject(new Error(`Next readiness timeout\n${logs}`)),
          60000,
        );
        child.once('exit', (code) => {
          clearTimeout(timer);
          reject(new Error(`Next exited ${code}\n${logs}`));
        });
        child.stdout.on('data', () => {
          if (logs.includes('Ready in')) {
            clearTimeout(timer);
            resolve();
          }
        });
      });
      const get = (path, accept) =>
        fetch(`${base}${path}`, {
          headers: accept ? { Accept: accept } : {},
          signal: AbortSignal.timeout(60000),
        });
      const path = `/conversations/${fixture.id}`;
      const html = await get(path);
      assert.equal(html.status, 200, logs);
      assert.match(html.headers.get('content-type'), /text\/html/);
      assert.match(html.headers.get('vary'), /accept/i);
      assert.match(html.headers.get('link'), /synthetic-share.md.*rel="alternate"/);
      const document = await html.text();
      for (const fact of [
        'Synthetic planning meeting',
        '1:30 PM UTC',
        '00:01:05',
        'Ada Example',
        'Owner:',
        'Due ',
        '4:00 PM UTC',
        'Unknown',
        'Example Labs',
        'Engineer',
        'Ship Thursday.',
        'Release review',
        '6:00 PM UTC',
      ])
        assert.ok(document.includes(fact), `${fact}\n${logs}`);
      // Next dev overwrites rendered HTML cache headers. Production dynamic
      // rendering follows the uncached fetch; reject a shared max-age either way.
      const htmlCache = html.headers.get('cache-control') || '';
      assert.doesNotMatch(htmlCache, /s-maxage=/);
      assert.doesNotMatch(htmlCache, /max-age=[1-9]/);
      assert.match(
        document,
        /<link[^>]+rel="alternate"[^>]+type="text\/markdown"[^>]+href="[^"]*synthetic-share.md"/,
      );
      assert.doesNotMatch(document, /@example\.com|>Owner<|>Speaker 0</);
      const md = await get(path, 'text/markdown');
      assert.equal(md.status, 200, logs);
      assert.equal(md.headers.get('content-type'), 'text/markdown; charset=utf-8');
      assert.match(md.headers.get('vary'), /accept/i);
      const markdown = await md.text();
      assert.doesNotMatch(markdown, /<!DOCTYPE/i);
      assert.match(markdown, /\[00:01:05\] Ada Example/);
      assert.match(markdown, /Owner: Ada Example/);
      assert.match(markdown, /2026-10-05T16:00:00.000Z/);
      assert.match(markdown, /Release review/);
      assert.match(markdown, /6:00 PM UTC/);
      assert.match(md.headers.get('cache-control') || '', /no-store/);
      const suffix = await get(`${path}.md`, 'text/html');
      assert.equal(suffix.headers.get('content-type'), 'text/markdown; charset=utf-8');
      assert.equal(await suffix.text(), markdown);
      for (const [url, accept] of [
        [path, 'application/json'],
        [`${path}.json`, 'text/html'],
      ]) {
        const json = await get(url, accept);
        assert.equal(json.status, 200, logs);
        assert.match(json.headers.get('content-type'), /application\/json/);
        assert.match(json.headers.get('vary'), /accept/i);
        assert.deepEqual(await json.json(), fixture);
        assert.match(json.headers.get('cache-control') || '', /no-store/);
      }
      const rejected = await get(path, 'text/html;q=0');
      assert.equal(rejected.status, 406, logs);
      assert.doesNotMatch(await rejected.text(), /I will send the plan/);
      const malformed = await get('/conversations/%');
      assert.equal(malformed.status, 400, logs);
      const discovery = await get('/llms.txt');
      assert.equal(discovery.status, 200);
      assert.match(await discovery.text(), /^# Omi shared conversations/);
      const legacy = await get(`/memories/${fixture.id}.md`);
      assert.equal(await legacy.text(), markdown);
      shared = false;
      for (const [url, accept] of [
        [path, 'text/markdown'],
        [`${path}.md`, 'text/html'],
        [path, 'application/json'],
      ]) {
        const missing = await get(url, accept);
        assert.equal(missing.status, 404, logs);
        assert.ok(!(await missing.text()).includes('I will send the plan.'));
      }
      // Next may have sent streaming HTML headers before notFound() runs.
      const revokedPage = await get(path, 'text/html');
      const revokedHtml = await revokedPage.text();
      for (const fact of [
        'I will send the plan.',
        'Discuss the release.',
        'Synthetic planning meeting',
        'Ship Thursday.',
        'Release review',
        'Walk the checklist.',
      ])
        assert.ok(!revokedHtml.includes(fact), fact);
      assert.match(revokedHtml, /Page not found|private or no longer available/);
    } catch (error) {
      console.error(logs);
      throw error;
    } finally {
      if (child.exitCode === null && child.signalCode === null) {
        child.kill('SIGTERM');
        await once(child, 'exit');
      }
      await new Promise((resolve) => backend.close(resolve));
      for (const [path, original] of generatedFiles) writeFileSync(path, original);
    }
  },
);
