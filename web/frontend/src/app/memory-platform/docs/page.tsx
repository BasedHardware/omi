import type { Metadata } from 'next';
import Link from 'next/link';
import { MEMORY_PLATFORM_LIMITS } from '@/src/lib/api/memory-platform';
import { MCP_SCOPES } from '@/src/lib/api/mcp-keys';
import PlatformShell from '../components/platform-shell';
import CodeBlock from '../components/code-block';
import { HairlineCard, Section } from '../components/section';
import {
  boundsSummary,
  capabilitySnippet,
  ingestSnippet,
  mcpClientSnippet,
  searchSnippet,
} from '../utils/snippets';
import { buildPlatformMetadata, generateBreadcrumbSchema } from '../utils/metadata';

export async function generateMetadata(): Promise<Metadata> {
  return buildPlatformMetadata({
    title: 'Memory Platform API reference',
    description:
      'REST and MCP reference for Omi memory: capability discovery, bounded search, canonical ingest, and scoped keys.',
    path: '/memory-platform/docs',
  });
}

export default function MemoryPlatformDocsPage() {
  const schema = generateBreadcrumbSchema([
    { name: 'Omi', path: '' },
    { name: 'Memory Platform', path: '/memory-platform' },
    { name: 'Docs', path: '/memory-platform/docs' },
  ]);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />
      <PlatformShell active="/memory-platform/docs">
        <div className="max-w-3xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#b9f36b]">
            Developer surface / v1
          </p>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-white md:text-5xl">
            Build on the ledger.
          </h1>
          <p className="mt-5 text-[17px] leading-8 text-neutral-400">
            Omi&apos;s backend is the authority. Your app can search and ingest through
            the canonical REST service or expose the same memory through MCP. Local
            databases and UI caches are replicas, never competing writers.
          </p>
          <p className="mt-5 font-mono text-xs text-neutral-600">{boundsSummary}</p>
        </div>

        <Section eyebrow="discover" title="GET /v1/memory/platform">
          <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
            <CodeBlock code={capabilitySnippet} caption="capability contract" />
            <p className="text-sm leading-7 text-neutral-400">
              The response identifies <code className="font-mono">omi_backend</code> as
              the authority, the canonical <code className="font-mono">memory_items</code>{' '}
              collection, the apply-control chain, the REST and MCP surfaces, and the zkr
              mirror boundary. It returns no memory content and no credentials.
            </p>
          </div>
        </Section>

        <Section
          eyebrow="read"
          title="GET /v1/memory/platform/search"
          description={
            <>
              Accepts <code className="font-mono">query</code>,{' '}
              <code className="font-mono">limit</code>, and{' '}
              <code className="font-mono">offset</code>. The authenticated session
              determines the tenant. Results pass through the same visibility and rollout
              policy as the product surface; archive is not default-visible.
            </>
          }
        >
          <CodeBlock code={searchSnippet} caption="bounded search" />
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <HairlineCard
              eyebrow="query"
              title={`≤ ${MEMORY_PLATFORM_LIMITS.maxQueryLength} chars`}
            >
              Longer queries are rejected with 400.
            </HairlineCard>
            <HairlineCard
              eyebrow="limit"
              title={`${MEMORY_PLATFORM_LIMITS.minLimit}–${MEMORY_PLATFORM_LIMITS.maxLimit}`}
            >
              Defaults to {MEMORY_PLATFORM_LIMITS.defaultLimit}. This is the bound the
              read service actually enforces.
            </HairlineCard>
            <HairlineCard
              eyebrow="offset"
              title={`0–${MEMORY_PLATFORM_LIMITS.maxOffset.toLocaleString('en-US')}`}
            >
              Page with offset; deep pagination is bounded on purpose.
            </HairlineCard>
          </div>
        </Section>

        <Section
          eyebrow="write"
          title="POST /v1/memory/platform/ingest"
          description="Ingest only through the platform endpoint. It promotes the memory through MemoryService, and returns 503 while canonical writes are unavailable rather than falling back to an independent store."
        >
          <CodeBlock code={ingestSnippet} caption="canonical ingest" />
        </Section>

        <Section
          eyebrow="mcp"
          title="Agent-native access"
          description={
            <>
              Connect to the hosted MCP server with a scoped key. The{' '}
              <code className="font-mono">memory_platform</code> tool is discovery-only;
              memory reads and writes stay on the scoped memory tools.{' '}
              <Link href="/memory-platform/keys" className="text-white underline">
                Create a key
              </Link>
              .
            </>
          }
        >
          <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
            <CodeBlock
              code={mcpClientSnippet}
              caption="mcp client config"
              language="json"
            />
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
              <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-neutral-500">
                available scopes
              </p>
              <ul className="mt-3 grid gap-1.5 font-mono text-[12px] text-neutral-300">
                {MCP_SCOPES.map((scope) => (
                  <li key={scope}>{scope}</li>
                ))}
              </ul>
              <p className="mt-4 text-sm leading-6 text-neutral-500">
                Default to <code className="font-mono">memories.read</code>. Grant a write
                scope only when the integration writes.
              </p>
            </div>
          </div>
        </Section>

        <Section
          eyebrow="replicas"
          title="zkr and local state"
          description="Keep the export high-water mark stable, apply only backend-acknowledged records, and rebuild local projections. A local zkr commit is not authoritative until it has passed backend ingestion and canonical apply."
        />
      </PlatformShell>
    </>
  );
}
