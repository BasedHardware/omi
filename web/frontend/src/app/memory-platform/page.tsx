import type { Metadata } from 'next';
import Link from 'next/link';
import { Button } from '@/src/components/ui/button';
import PlatformShell from './components/platform-shell';
import LandingHero from './components/landing-hero';
import CodeBlock from './components/code-block';
import { HairlineCard, Section } from './components/section';
import { iframeSnippet, mcpClientSnippet } from './utils/snippets';
import {
  buildPlatformMetadata,
  generateBreadcrumbSchema,
  generateSoftwareApplicationSchema,
} from './utils/metadata';

export async function generateMetadata(): Promise<Metadata> {
  return buildPlatformMetadata({
    title: 'Memory Platform — backend-authoritative memory for agents and products',
    description:
      'Search, ingest, and embed Omi memory through one canonical service. REST, MCP, local replicas, and embeddable widgets read from the same ledger.',
    path: '/memory-platform',
  });
}

export default function MemoryPlatformPage() {
  const schema = [
    generateSoftwareApplicationSchema(),
    generateBreadcrumbSchema([
      { name: 'Omi', path: '' },
      { name: 'Memory Platform', path: '/memory-platform' },
    ]),
  ];

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />
      <PlatformShell active="/memory-platform">
        <LandingHero />

        <Section
          id="authority"
          eyebrow="01 / authority"
          title="The ledger is the product."
          description="Omi assigns ordering, applies access policy, and owns the durable memory transition. Everything else is a projection you can rebuild."
        >
          <div className="grid gap-4 md:grid-cols-3">
            <HairlineCard eyebrow="01" title="Backend first">
              Canonical writes go through MemoryService. If canonical mode is unavailable,
              ingest returns 503 instead of forking into a second store.
            </HairlineCard>
            <HairlineCard eyebrow="02" title="Evidence stays attached">
              Agents receive scoped results while the canonical source, visibility rules,
              and rollout policy stay server-side.
            </HairlineCard>
            <HairlineCard eyebrow="03" title="Surfaces stay replaceable">
              Search indexes, MCP responses, local caches, and UI projections can be
              rebuilt without forking truth.
            </HairlineCard>
          </div>
        </Section>

        <Section
          id="surfaces"
          eyebrow="02 / surfaces"
          title="Meet memory where your product lives."
        >
          <div className="grid gap-4 md:grid-cols-3">
            <HairlineCard eyebrow="rest" title="Canonical API">
              Bounded search and explicit ingest with typed failure states.{' '}
              <Link href="/memory-platform/docs" className="text-white underline">
                API reference
              </Link>
              .
            </HairlineCard>
            <HairlineCard eyebrow="mcp" title="Agent-native">
              Scoped MCP keys expose memory to tools. Default to{' '}
              <code className="font-mono text-neutral-300">memories.read</code>.{' '}
              <Link href="/memory-platform/keys" className="text-white underline">
                Manage keys
              </Link>
              .
            </HairlineCard>
            <HairlineCard eyebrow="embed" title="Embeddable">
              A small memory widget you can frame inside your product, backed by a
              server-side proxy.{' '}
              <Link href="/memory-platform/embed" className="text-white underline">
                Embed guide
              </Link>
              .
            </HairlineCard>
          </div>
        </Section>

        <Section
          eyebrow="03 / mcp"
          title="Point your agent at Omi."
          description="Create a scoped MCP key, drop it in your client config, and the agent reads the same canonical memory your product does."
        >
          <CodeBlock
            code={mcpClientSnippet}
            caption="mcp client config"
            language="json"
          />
        </Section>

        <Section
          eyebrow="04 / embed"
          title="Ship memory inside your own surface."
          description="Host the UI on your origin, authenticate there, and frame it with a sandbox the framed document cannot remove."
        >
          <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
            <CodeBlock code={iframeSnippet} caption="iframe" language="html" />
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
              <p className="text-sm leading-7 text-neutral-400">
                Never pair <code className="font-mono">allow-scripts</code> with{' '}
                <code className="font-mono">allow-same-origin</code>: a framed document
                granted both can remove its own sandbox attribute. Keep credentials on
                your server, and set <code className="font-mono">frame-ancestors</code> to
                the exact parent origins you control.
              </p>
              <Button asChild className="mt-5" variant="outline">
                <Link href="/memory-platform/embed">Open the embed guide</Link>
              </Button>
            </div>
          </div>
        </Section>

        <Section
          eyebrow="05 / boundary"
          title="zkr is the mirror, not a second authority."
          description="zkr is a strong local evidence-backed replica: apply backend-acknowledged records, keep the stable cursor, and let local projections rebuild. A local commit is not authoritative until it has passed backend ingestion and canonical apply."
        />
      </PlatformShell>
    </>
  );
}
