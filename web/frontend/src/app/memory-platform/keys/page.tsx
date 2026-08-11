import type { Metadata } from 'next';
import PlatformShell from '../components/platform-shell';
import KeysManager from '../components/keys-manager';
import CodeBlock from '../components/code-block';
import { Section } from '../components/section';
import { mcpClientSnippet } from '../utils/snippets';
import { buildPlatformMetadata } from '../utils/metadata';

export async function generateMetadata(): Promise<Metadata> {
  return buildPlatformMetadata({
    title: 'MCP API keys',
    description:
      'Create, rotate, and revoke scoped MCP keys for the Omi memory platform. Raw keys are shown once.',
    path: '/memory-platform/keys',
    noIndex: true,
  });
}

export default function MemoryPlatformKeysPage() {
  return (
    <PlatformShell active="/memory-platform/keys">
      <div className="max-w-3xl">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[#b9f36b]">
          Credentials
        </p>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight text-white md:text-5xl">
          MCP keys.
        </h1>
        <p className="mt-5 text-[17px] leading-8 text-neutral-400">
          A key is shown in full exactly once, at creation or rotation. After that only
          its prefix, creation time, and last-used time are visible — Omi stores a hash,
          not the key. Keep keys on a server; never place them in source, browser storage,
          or a public environment variable.
        </p>
      </div>

      <div className="mt-10">
        <KeysManager />
      </div>

      <Section
        eyebrow="usage"
        title="Point a client at the key"
        description="Store the key in your client's secret store or an environment variable that never reaches a browser bundle."
      >
        <CodeBlock code={mcpClientSnippet} caption="mcp client config" language="json" />
      </Section>
    </PlatformShell>
  );
}
