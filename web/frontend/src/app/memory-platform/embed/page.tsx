import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Embed Omi Memory',
  description: 'Safely embed an Omi memory surface inside your product.',
};

const iframeExample = `<iframe
  src="https://your-app.example/omi-memory"
  title="Omi memory"
  loading="lazy"
  referrerpolicy="strict-origin-when-cross-origin"
  sandbox="allow-scripts"
  style="width:100%;height:560px;border:0"
></iframe>`;

const proxyExample = `export async function GET(request: Request) {
  // 1. Authenticate the visitor against your own session, never the client header.
  const session = await getSession(request);
  if (!session) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  // 2. Resolve the Omi session token for that tenant from your server-side store.
  const omiToken = await getOmiTokenForTenant(session.tenantId);
  if (!omiToken) {
    return Response.json({ error: "forbidden" }, { status: 403 });
  }

  // 3. Forward only bounded parameters you validated yourself.
  const params = new URL(request.url).searchParams;
  const query = (params.get("q") ?? "").slice(0, 500);
  const limit = Math.min(Math.max(Number(params.get("limit") ?? 20), 1), 500);

  const upstream = await fetch(
    "https://api.omi.me/v1/memory/platform/search?" +
      new URLSearchParams({ query, limit: String(limit) }),
    { headers: { Authorization: \`Bearer \${omiToken}\` } },
  );

  return Response.json(await upstream.json(), { status: upstream.status });
}`;

export default function MemoryPlatformEmbedPage() {
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
            Embeddable by design
          </p>
          <h1 className="mt-4 font-serif text-5xl font-normal tracking-[-0.06em] md:text-7xl">
            Put memory in the room.
          </h1>
          <p className="mt-6 text-lg leading-8 text-[#f4f1e8]/65">
            The safest embed is a surface you own, backed by a server-side proxy. Keep
            tokens out of browser bundles, keep the frame narrow, and let Omi&apos;s
            backend remain the only authority.
          </p>
        </div>

        <section className="mt-16 grid gap-4 md:grid-cols-3">
          {[
            [
              '1',
              'Proxy',
              'Call Omi from your server or same-origin route. Never ship a durable API key to the browser.',
            ],
            [
              '2',
              'Frame',
              'Render your memory UI in an iframe with a strict sandbox and explicit frame policy.',
            ],
            [
              '3',
              'Message',
              'Use postMessage only for short-lived UI events, not raw credentials or unrestricted memory writes.',
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
        </section>

        <section className="mt-20 border-t border-[#f4f1e8]/15 pt-8">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#b9f36b]">
            Option A / iframe
          </p>
          <h2 className="mt-3 font-serif text-4xl font-normal tracking-[-0.05em]">
            Embed your own memory surface
          </h2>
          <p className="mt-4 max-w-2xl leading-7 text-[#f4f1e8]/60">
            Host the UI on your origin, authenticate there, and point the iframe at it.
            This keeps cookies and API credentials inside your product boundary.
          </p>
          <pre className="mt-6 overflow-x-auto border-l-4 border-[#b9f36b] bg-[#111715] p-5 text-sm leading-7 text-[#f4f1e8]/85">
            {iframeExample}
          </pre>
        </section>

        <section className="mt-16 border-t border-[#f4f1e8]/15 pt-8">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#b9f36b]">
            Option B / server proxy
          </p>
          <h2 className="mt-3 font-serif text-4xl font-normal tracking-[-0.05em]">
            Keep Omi behind your origin
          </h2>
          <p className="mt-4 max-w-2xl leading-7 text-[#f4f1e8]/60">
            Your server validates the visitor&apos;s session, resolves that tenant&apos;s
            Omi token from your own server-side store, forwards only bounded search
            parameters, and returns the response. Never forward the caller&apos;s
            Authorization header upstream, and apply the same tenant checks before
            forwarding any write.
          </p>
          <pre className="mt-6 overflow-x-auto border-l-4 border-[#a7d8ff] bg-[#111715] p-5 text-sm leading-7 text-[#f4f1e8]/85">
            {proxyExample}
          </pre>
        </section>

        <section className="mt-16 border-t border-[#f4f1e8]/15 pt-8">
          <h2 className="font-serif text-4xl font-normal tracking-[-0.05em]">
            Security checklist
          </h2>
          <ul className="mt-6 grid gap-3 text-[#f4f1e8]/65 md:grid-cols-2">
            {[
              'Use a server-side proxy or a short-lived, narrowly scoped session.',
              'Never place Omi API keys in source, localStorage, or public environment variables.',
              'Validate origin on every postMessage event and send only typed UI events.',
              'Set frame-ancestors to the exact parent origins you control.',
              'Keep writes explicit and user-initiated; default to memories.read.',
              'Treat local zkr or SQLite as a cache or pending buffer, never as authority.',
            ].map((item) => (
              <li key={item} className="border-l-2 border-[#ff806a] pl-4 leading-7">
                {item}
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-20 flex flex-wrap gap-4 border-t border-[#f4f1e8]/15 pt-8">
          <Link
            href="/memory-platform/docs"
            className="bg-[#b9f36b] px-5 py-3 text-xs font-bold uppercase tracking-[0.12em] text-[#0b0f0e]"
          >
            API reference ↗
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
