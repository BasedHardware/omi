import type { Metadata } from 'next';
import PlatformShell from '../components/platform-shell';
import CodeBlock from '../components/code-block';
import EmbedPreview from '../components/embed-preview';
import { HairlineCard, Section } from '../components/section';
import {
  cspSnippet,
  iframeSnippet,
  postMessageSnippet,
  proxySnippet,
  securityChecklist,
} from '../utils/snippets';
import { buildPlatformMetadata, generateBreadcrumbSchema } from '../utils/metadata';

export async function generateMetadata(): Promise<Metadata> {
  return buildPlatformMetadata({
    title: 'Embed Omi Memory',
    description:
      'Drop a small, sandboxed memory widget into your product, backed by a server-side proxy that keeps Omi credentials off the browser.',
    path: '/memory-platform/embed',
  });
}

export default function MemoryPlatformEmbedPage() {
  const schema = generateBreadcrumbSchema([
    { name: 'Omi', path: '' },
    { name: 'Memory Platform', path: '/memory-platform' },
    { name: 'Embed', path: '/memory-platform/embed' },
  ]);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />
      <PlatformShell active="/memory-platform/embed">
        <div className="max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#b9f36b]">
            Embeddable by design
          </p>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-white md:text-5xl">
            Put memory in the room.
          </h1>
          <p className="mt-5 text-[17px] leading-8 text-neutral-400">
            The safest embed is a surface you own, backed by a server-side proxy. Keep
            tokens out of browser bundles, keep the frame narrow, and let Omi&apos;s
            backend remain the only authority.
          </p>
        </div>

        <Section
          eyebrow="live"
          title="The widget, actually rendering."
          description="Below is the real widget component, rendering. It runs in preview mode: sample records, no network call, no session required — and it emits the same typed UI events a framed instance emits."
        >
          <div className="grid gap-6 lg:grid-cols-[1fr_0.9fr] lg:items-start">
            <EmbedPreview />
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 text-sm leading-7 text-neutral-400">
              <p>
                When you frame it, sandbox it with{' '}
                <code className="font-mono">allow-scripts</code> and deliberately{' '}
                <strong className="text-neutral-200">without</strong>{' '}
                <code className="font-mono">allow-same-origin</code>. A document granted
                both can rewrite its own sandbox attribute and escape the restriction.
              </p>
              <p className="mt-4">
                The widget posts only typed, credential-free UI events (
                <code className="font-mono">omi.memory.embed.ready</code>,{' '}
                <code className="font-mono">omi.memory.embed.resize</code>). The parent
                validates the origin and the message source before acting on them.
              </p>
            </div>
          </div>
        </Section>

        <Section eyebrow="architecture" title="Three moving parts.">
          <div className="grid gap-4 md:grid-cols-3">
            <HairlineCard eyebrow="1" title="Proxy">
              Call Omi from your server or a same-origin route. Never ship a durable API
              key to the browser.
            </HairlineCard>
            <HairlineCard eyebrow="2" title="Frame">
              Render the memory UI in an iframe with a strict sandbox and an explicit
              frame-ancestors policy.
            </HairlineCard>
            <HairlineCard eyebrow="3" title="Message">
              Use postMessage for short-lived UI events only — never raw credentials or
              unrestricted memory writes.
            </HairlineCard>
          </div>
        </Section>

        <Section
          eyebrow="option a / iframe"
          title="Embed your own memory surface"
          description="Host the UI on your origin, authenticate there, and point the iframe at it. Cookies and API credentials stay inside your product boundary."
        >
          <CodeBlock code={iframeSnippet} caption="iframe" language="html" />
          <div className="mt-4">
            <CodeBlock code={cspSnippet} caption="response header" language="http" />
          </div>
        </Section>

        <Section
          eyebrow="option b / server proxy"
          title="Keep Omi behind your origin"
          description="Your server validates the visitor, forwards only bounded search parameters, and passes the response through. Apply your own tenant checks before forwarding any write."
        >
          <CodeBlock code={proxySnippet} caption="next.js route handler" language="ts" />
        </Section>

        <Section
          eyebrow="messaging"
          title="Typed events, validated origin"
          description="The parent must check event.origin on every message. A sandboxed frame without allow-same-origin posts from the opaque origin 'null'."
        >
          <CodeBlock code={postMessageSnippet} caption="parent listener" language="ts" />
        </Section>

        <Section eyebrow="security" title="Checklist">
          <ul className="grid gap-3 md:grid-cols-2">
            {securityChecklist.map((item) => (
              <li
                key={item}
                className="rounded-lg border border-white/10 bg-white/[0.02] p-4 text-sm leading-6 text-neutral-300"
              >
                {item}
              </li>
            ))}
          </ul>
        </Section>
      </PlatformShell>
    </>
  );
}
