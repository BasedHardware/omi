import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Memory Platform API',
  description: 'Build against Omi memory through the canonical REST and MCP surfaces.',
};

const searchExample = `curl "https://api.omi.me/v1/memory/platform/search?query=launch&limit=20" \\
  -H "Authorization: Bearer $OMI_SESSION"`;

const ingestExample = `curl -X POST https://api.omi.me/v1/memory/platform/ingest \\
  -H "Authorization: Bearer $OMI_SESSION" \\
  -H "Content-Type: application/json" \\
  -d '{"content":"The next launch is Thursday","category":"manual"}'`;

export default function MemoryPlatformDocsPage() {
  return (
    <main className="min-h-screen bg-[#0b0f0e] px-5 pb-24 pt-32 text-[#f4f1e8] md:px-12">
      <div className="mx-auto max-w-5xl">
        <Link
          href="/memory-platform"
          className="text-xs font-bold uppercase tracking-[0.18em] text-[#b9f36b]"
        >
          ← Memory platform
        </Link>
        <div className="mt-12 max-w-3xl">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#ff806a]">
            Developer surface / v1
          </p>
          <h1 className="mt-4 font-serif text-5xl font-normal tracking-[-0.06em] md:text-7xl">
            Build on the ledger.
          </h1>
          <p className="mt-6 text-lg leading-8 text-[#f4f1e8]/65">
            Omi&apos;s backend is the authority. Your app can search and ingest through
            the canonical REST service or expose the same memory through MCP. Local
            databases and UI caches are replicas, never competing writers.
          </p>
        </div>

        <div className="mt-16 grid gap-4 md:grid-cols-3">
          {[
            [
              '01',
              'Discover',
              'GET /v1/memory/platform returns the authority and replica contract.',
            ],
            ['02', 'Read', 'Search default-visible memory with bounded pagination.'],
            [
              '03',
              'Write',
              'Ingest through MemoryService; the backend decides whether it can commit.',
            ],
          ].map(([number, title, copy]) => (
            <article
              key={number}
              className="border border-[#f4f1e8]/15 bg-[#f4f1e8]/[0.04] p-5"
            >
              <span className="font-mono text-xs text-[#ff806a]">{number}</span>
              <h2 className="mt-12 font-serif text-3xl font-normal tracking-[-0.04em]">
                {title}
              </h2>
              <p className="mt-3 leading-7 text-[#f4f1e8]/55">{copy}</p>
            </article>
          ))}
        </div>

        <section className="mt-20 border-t border-[#f4f1e8]/15 pt-8">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#b9f36b]">
            REST / authenticated
          </p>
          <h2 className="mt-3 font-serif text-4xl font-normal tracking-[-0.05em]">
            Search canonical memory
          </h2>
          <p className="mt-4 max-w-2xl leading-7 text-[#f4f1e8]/60">
            Use the user session accepted by Omi. Results are scoped to the authenticated
            user and pass through the same visibility and rollout policy as the product
            surface.
          </p>
          <pre className="mt-6 overflow-x-auto border-l-4 border-[#a7d8ff] bg-[#111715] p-5 text-sm leading-7 text-[#f4f1e8]/85">
            {searchExample}
          </pre>
          <p className="mt-4 text-sm text-[#f4f1e8]/50">
            Limits: query ≤ 500 characters, limit 1–100, offset 0–100,000.
          </p>
        </section>

        <section className="mt-16 border-t border-[#f4f1e8]/15 pt-8">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#b9f36b]">
            REST / canonical ingest
          </p>
          <h2 className="mt-3 font-serif text-4xl font-normal tracking-[-0.05em]">
            Promote a memory through Omi
          </h2>
          <p className="mt-4 max-w-2xl leading-7 text-[#f4f1e8]/60">
            Ingest only through the platform endpoint. It rejects writes while canonical
            mode is unavailable and never exposes direct Firestore writes to clients.
          </p>
          <pre className="mt-6 overflow-x-auto border-l-4 border-[#ff806a] bg-[#111715] p-5 text-sm leading-7 text-[#f4f1e8]/85">
            {ingestExample}
          </pre>
        </section>

        <section className="mt-16 grid gap-8 border-t border-[#f4f1e8]/15 pt-8 md:grid-cols-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#b9f36b]">
              MCP
            </p>
            <h2 className="mt-3 font-serif text-4xl font-normal tracking-[-0.05em]">
              Agent-native access
            </h2>
            <p className="mt-4 leading-7 text-[#f4f1e8]/60">
              Connect to the hosted MCP server with a key granted memories.read or
              memories.write. The memory_platform tool is discovery-only; memory reads and
              writes stay on the scoped memory tools.
            </p>
          </div>
          <div className="border border-[#f4f1e8]/15 bg-[#f4f1e8]/[0.04] p-5">
            <p className="font-mono text-xs text-[#a7d8ff]">memory_platform</p>
            <p className="mt-4 text-sm leading-7 text-[#f4f1e8]/65">
              Returns authority = omi_backend, the canonical Firestore collection, API/MCP
              surfaces, and zkr mirror compatibility. It returns no memory content or
              credentials.
            </p>
          </div>
        </section>

        <div className="mt-20 flex flex-wrap gap-4 border-t border-[#f4f1e8]/15 pt-8">
          <Link
            href="/memory-platform/embed"
            className="bg-[#b9f36b] px-5 py-3 text-xs font-bold uppercase tracking-[0.12em] text-[#0b0f0e]"
          >
            Read the embed guide ↗
          </Link>
          <Link
            href="/memory-platform"
            className="border border-[#f4f1e8]/20 px-5 py-3 text-xs font-bold uppercase tracking-[0.12em] text-[#f4f1e8]"
          >
            Back to platform
          </Link>
        </div>
      </div>
    </main>
  );
}
