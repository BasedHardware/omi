// Render exact fictional server output JSON, not an app or a recreated client screen.
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = dirname(fileURLToPath(import.meta.url));
const snapshots = join(root, '../../../backend/tests/unit/fixtures/speaker_abstention_snapshots');
const cases = ['one-voice', 'two-voices', 'wearer', 'mixed-epochs', 'point-keys', 'historical-fallback'];
const titles = ['One voice + two uncovered gaps', 'Two voices + separate unknown speech', 'Manual wearer receipt + two gaps', 'Mixed capture epochs', 'Zero-duration point keys', 'Historical fallback IDs'];
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const browser = await chromium.launch({ headless: true });
const images = [];
try {
  for (const [index, name] of cases.entries()) {
    const snapshot = JSON.parse(await readFile(join(snapshots, `${name}.json`), 'utf8'));
    const column = (state, title) => {
      const output = snapshot[state];
      const rows = output.api.transcript_segments;
      const lines = rows.map(r => `<div class="turn"><b>${escape(r.speaker_name)}</b><span>${escape(r.text)}</span><small>${escape(r.id)} · stored speaker_id ${r.speaker_id}</small></div>`).join('');
      const excerpt = output.review.speaker.context.map(r => `<div class="quote"><b>${escape(r.speaker_label)}:</b> ${escape(r.text)}</div>`).join('');
      return `<section><div class="state ${state}">${title}</div><div class="metric">Label / participant delta <strong>${output.label_participant_delta}</strong> · stored gap keys <strong>${output.inventory.abstention_keys.length}</strong></div><article><h2>Conversation API · speaker_name</h2>${lines}</article><article><h2>Server review excerpt</h2>${excerpt}</article><article><h2>MCP transcript search · first exact hit</h2><pre>${escape(output.mcp_search[0].text)}</pre></article><article><h2>LLM transcript input · plain text</h2><pre>${escape(output.llm_plain)}</pre></article></section>`;
    };
    const html = `<!doctype html><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;background:#eef2f6;color:#172332;font:18px system-ui,sans-serif;padding:40px}
      .kicker{font-size:14px;letter-spacing:2px;color:#52657c;font-weight:700}h1{font-size:34px;margin:12px 0 10px}.intro{color:#52657c;margin:0 0 26px;line-height:1.5}
      main{display:grid;grid-template-columns:1fr 1fr;gap:24px}section{min-width:0}.state{padding:16px 20px;border-radius:12px 12px 0 0;font-weight:750;background:#d7dfe9}.after{background:#bfe7db;color:#174d40}
      .metric{background:#fff;padding:12px 20px;font-size:15px;border-bottom:1px solid #e5e9ef}article{padding:18px 20px;background:white;border-bottom:1px solid #e5e9ef}h2{font-size:14px;margin:0 0 15px;text-transform:uppercase;letter-spacing:.7px;color:#52657c}
      .turn{display:grid;grid-template-columns:170px 1fr;gap:3px 12px;padding:10px 0;border-top:1px solid #edf0f4;font-size:17px}.turn:first-of-type{border:0}small{grid-column:2;font-size:12px;color:#68798a}.quote{font-size:16px;line-height:1.5;padding:5px 0}
      pre{font:15px/1.6 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}footer{font-size:14px;line-height:1.6;margin-top:24px;color:#52657c}
      </style><div class="kicker">STAGE 1 · SERVER OUTPUT · FICTIONAL FIXTURES</div><h1>${titles[index]}</h1><p class="intro">UI label: Unknown speaker. Model input: unassigned speech, with distinct citation keys.<br>Before = kill switch off (previous labels). After = default-on behavior.</p><main>${column('before','BEFORE · existing labels')}${column('after','AFTER · abstention presentation')}</main><footer>Exact source: ${name}.json · Calls real server formatters with offline data adapters. No account or provider data.<br>Mobile, macOS and web client naming/count formatters remain stage 2. This is server text evidence, not a client screenshot. Renders pending David.</footer>`;
    const page = await browser.newPage({ viewport: {width:1500,height:1000}, deviceScaleFactor:1 });
    // No network requests are permitted for the evidence page.
    await page.route('**/*', route => route.abort());
    await page.setContent(html);
    const file = `${String(index+1).padStart(3,'0')}-web-${name}-before-after.png`;
    await page.screenshot({path:join(root,file),fullPage:true});
    await page.close();
    images.push({file, platform:'web', description:`Server API/review/MCP/LLM text output before/after: ${titles[index]}. Fictional fixture; not a client screen.`,captured_by:'agent',source:'visual-audit'});
  }
  await writeFile(join(root,'evidence.json'), JSON.stringify({version:1,images}, null, 2)+'\n');
} finally { await browser.close(); }
