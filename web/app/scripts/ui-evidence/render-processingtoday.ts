// Run from web/app with PLAYWRIGHT_MODULE pointing to a task-local install.
// No service credentials, application server, Firebase, or remote requests.
import { resolve } from 'node:path';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';

const output = resolve('../../.agent-artifacts/ui-evidence/processingtoday');
const build = await mkdtemp(resolve(tmpdir(), 'omi-processing-render-'));
const playwrightModule = process.env.PLAYWRIGHT_MODULE;
if (!playwrightModule)
  throw new Error('PLAYWRIGHT_MODULE must point to a local playwright install');
const { chromium } = await import(playwrightModule);
const result = await Bun.build({
  entrypoints: ['scripts/ui-evidence/processingtoday.tsx'],
  outdir: build,
  target: 'browser',
  plugins: [
    {
      name: 'hermetic-evidence',
      setup(builder) {
        builder.onResolve(
          { filter: /^@\/lib\/(api|analytics\/posthog)$/ },
          ({ path }) => ({ path, namespace: 'fixture' }),
        );
        builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
          loader: 'js',
          contents: path.endsWith('/api')
            ? `export async function reprocessConversation(id) { return {id, home_step:'done', status:'completed', created_at:'2026-11-10T13:00:00Z', transcript_segments:[], structured:{title:'Unfinished planning',overview:'',action_items:[],events:[]}}; }
export async function getAttentionItems() { const value=new URLSearchParams(location.search).get('notes'); return {items: value ? [{id:'notes-case-'+value,kind:'conversation_notes_failed_with_outputs',conversation_id:'kept-outputs',title:['Planning follow-up','Actions captured','Meeting scheduled'][Number(value)-10],retryable:true,retry:{state:'none',operation_id:null}}] : []}; }
export async function retryAttentionItem(id,key) { if(!id.startsWith('notes-case-') || !key) throw new Error('Wrong retry contract'); return {operation_id:'op',state:'in_progress'}; }`
            : 'export const PostHogManager = {track() {}};',
        }));
      },
    },
  ],
});
if (!result.success) throw new Error(result.logs.join('\n'));
const css = Bun.spawnSync([
  'bunx',
  'tailwindcss',
  '-i',
  'src/app/globals.css',
  '-o',
  `${build}/styles.css`,
  '--minify',
]);
if (css.exitCode !== 0) throw new Error(css.stderr.toString());
const styles =
  (await readFile(`${build}/styles.css`, 'utf8')).replace(/@import\s+url\([^;]+;/g, '') +
  '\n@font-face{font-family:EvidenceSF;src:url(/font.otf)}body{font-family:EvidenceSF,system-ui;background:#0f0f0f;color:white}.font-body,.font-display{font-family:EvidenceSF,system-ui}';
const server = Bun.serve({
  hostname: '127.0.0.1',
  port: 0,
  fetch(request) {
    const path = new URL(request.url).pathname;
    if (path === '/fixture.js')
      return new Response(Bun.file(`${build}/processingtoday.js`));
    if (path === '/styles.css')
      return new Response(styles, { headers: { 'content-type': 'text/css' } });
    if (path === '/font.otf')
      return new Response(Bun.file('../../app/test/fonts/SFPRODISPLAYREGULAR.OTF'));
    return new Response(
      '<!doctype html><html><head><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script type="module" src="/fixture.js"></script></body></html>',
      { headers: { 'content-type': 'text/html' } },
    );
  },
});
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    timezoneId: 'America/New_York',
  });
  const origin = `http://127.0.0.1:${server.port}`;
  await page.route('**/*', (route: any) =>
    new URL(route.request().url()).origin === origin ? route.continue() : route.abort(),
  );
  await page.goto(origin);
  // Capture the selected tab at rest rather than between its color transitions.
  await page.addStyleTag({
    content: '*,*::before,*::after{transition:none!important;animation:none!important}',
  });
  await page.getByText('Coffee with Alex', { exact: true }).waitFor();
  await page.evaluate(() => document.fonts.ready);
  if (await page.getByText('Unfinished planning', { exact: true }).count())
    throw new Error('Failed row leaked onto Home');
  await page.screenshot({ path: `${output}/015-web-home-failed-after.png` });
  await page.getByRole('button', { name: 'Activity', exact: true }).click();
  await page.getByRole('button', { name: 'Retry', exact: true }).waitFor();
  await page.screenshot({ path: `${output}/016-web-activity-failed-after.png` });
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await page
    .getByRole('button', { name: 'Retry', exact: true })
    .waitFor({ state: 'detached' });
  await page.goto(`${origin}?rollback=1`);
  await page.getByRole('button', { name: 'Retry', exact: true }).waitFor();
  if (await page.getByRole('button', { name: 'Activity', exact: true }).count())
    throw new Error('Rollback left Activity enabled');
  for (let index = 0; index < 3; index++) {
    const caseNumber = `0${10 + index}`;
    const title = ['Planning follow-up', 'Actions captured', 'Meeting scheduled'][index];
    await page.goto(`${origin}?notes=${caseNumber}`);
    await page.addStyleTag({
      content: '*,*::before,*::after{transition:none!important;animation:none!important}',
    });
    await page.getByText('Coffee with Alex', { exact: true }).waitFor();
    if (await page.getByText(title, { exact: true }).count())
      throw new Error('Notes failure leaked onto Home');
    const before = await page.evaluate(() => (window as any).savedOutputs);
    await page.getByRole('button', { name: 'Activity', exact: true }).click();
    await page.getByRole('button', { name: 'Re-run notes', exact: true }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    if ((await page.getByText(title, { exact: true }).count()) !== 1)
      throw new Error('Duplicate attention row');
    await page.screenshot({
      path: `${output}/0${22 + index}-web-notes-case-${caseNumber}.png`,
    });
    await page.getByRole('button', { name: 'Re-run notes', exact: true }).click();
    await page.getByText(title, { exact: true }).waitFor({ state: 'detached' });
    if ((await page.evaluate(() => (window as any).savedOutputs)) !== before)
      throw new Error('Saved outputs changed');
  }
  console.log(
    'Web Home/Activity/retry/rollback and notes 010/011/012 assertions passed; external requests blocked.',
  );
} finally {
  await browser?.close();
  server.stop(true);
  await rm(build, { recursive: true, force: true });
}
