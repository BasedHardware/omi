import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { Button } from '@/src/components/ui/button';
import CodeBlock from './code-block';
import { boundsSummary, searchSnippet } from '../utils/snippets';

export default function LandingHero() {
  return (
    <section className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#b9f36b]">
          One memory layer / every interface
        </p>
        <h1 className="mt-5 text-4xl font-semibold leading-[1.05] tracking-tight text-white md:text-6xl">
          Memory that travels.
          <br />
          <span className="text-neutral-500">Authority that stays put.</span>
        </h1>
        <p className="mt-6 max-w-xl text-[17px] leading-8 text-neutral-400">
          Give your agents and products a durable, evidence-backed memory surface through
          Omi&apos;s backend. REST, MCP, local capture, and embeds all read from the same
          canonical ledger — and none of them become a second writer.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/memory-platform/docs">
              Read the docs
              <ArrowUpRight className="ml-1.5 h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/memory-platform/keys">Create an MCP key</Link>
          </Button>
          <Button asChild size="lg" variant="ghost">
            <Link href="/memory-platform/embed">Embed it</Link>
          </Button>
        </div>
        <p className="mt-6 font-mono text-xs text-neutral-600">{boundsSummary}</p>
      </div>

      <CodeBlock code={searchSnippet} caption="canonical request" />
    </section>
  );
}
