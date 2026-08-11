import Link from 'next/link';
import styles from './platform-page.module.css';

const requestSnippet = `curl https://api.omi.me/v1/memory/platform/search \\
  -H "Authorization: Bearer $OMI_SESSION" \\
  --get --data-urlencode "query=the next launch"`;

export default function PlatformPage() {
  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.masthead}>
          <Link href="/memory-platform" className={styles.wordmark}>
            <span className={styles.signal} aria-hidden="true" />
            Omi memory platform
          </Link>
          <nav className={styles.nav} aria-label="Memory platform navigation">
            <Link href="#authority">Authority</Link>
            <Link href="#surfaces">Surfaces</Link>
            <Link href="/memory-platform/docs">Docs</Link>
          </nav>
        </div>

        <section className={styles.hero}>
          <div>
            <div className={styles.eyebrow}>One memory layer / every interface</div>
            <h1 className={styles.headline}>
              Memory that can <em>travel.</em>
              <br />
              Authority that stays put.
            </h1>
            <p className={styles.lede}>
              Give your agents a durable, evidence-backed memory surface through
              Omi&apos;s backend. API, MCP, local capture, and embeds all read from the
              same canonical ledger.
            </p>
            <div className={styles.actions}>
              <Link href="/memory-platform/docs" className={styles.primary}>
                Read the docs <span aria-hidden="true">↗</span>
              </Link>
              <Link href="/memory-platform/embed" className={styles.secondary}>
                Make it embeddable <span aria-hidden="true">↗</span>
              </Link>
            </div>
          </div>

          <div className={styles.terminal} aria-label="Memory platform API example">
            <div className={styles.terminalBar}>
              <span>canonical request</span>
              <span className={styles.terminalDots} aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
            <pre className={styles.code}>
              <span className={styles.codeMuted}>$ </span>
              {requestSnippet}
              {'\n\n'}
              <span className={styles.codeAccent}>
                {'{'} authority: &apos;omi_backend&apos; {'}'}
              </span>
              {'\n'}
              <span className={styles.codeMuted}>
                {' '}
                source: memory_items / apply-control
              </span>
            </pre>
          </div>
        </section>

        <section id="authority" className={styles.section}>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>The ledger is the product.</h2>
            <span className={styles.sectionKicker}>01 / authority</span>
          </div>
          <div className={styles.grid}>
            <article className={styles.card}>
              <span className={styles.cardNumber}>01</span>
              <h3>Backend first</h3>
              <p>
                Omi assigns ordering, applies access policy, and owns the durable memory
                transition.
              </p>
            </article>
            <article className={styles.card}>
              <span className={styles.cardNumber}>02</span>
              <h3>Evidence stays attached</h3>
              <p>
                Agents receive scoped memory results while the canonical source and
                visibility rules remain server-side.
              </p>
            </article>
            <article className={styles.card}>
              <span className={styles.cardNumber}>03</span>
              <h3>Surfaces stay replaceable</h3>
              <p>
                Search indexes, MCP responses, local caches, and UI projections can be
                rebuilt without forking truth.
              </p>
            </article>
          </div>
        </section>

        <div className={styles.boundary}>
          <strong>zkr is the mirror.</strong>
          <p>
            zkr is a strong local evidence-backed replica: apply backend-acknowledged
            records, keep the stable cursor, and let local projections rebuild. It never
            becomes a second authority.
          </p>
        </div>

        <section id="surfaces" className={styles.section}>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>Meet memory where your product lives.</h2>
            <span className={styles.sectionKicker}>02 / surfaces</span>
          </div>
          <div className={styles.grid}>
            <article className={styles.card}>
              <span className={styles.cardNumber}>API</span>
              <h3>REST service</h3>
              <p>
                Search and ingest through authenticated canonical endpoints with bounded
                requests and explicit failure states.
              </p>
            </article>
            <article className={styles.card}>
              <span className={styles.cardNumber}>MCP</span>
              <h3>Agent-native</h3>
              <p>
                Expose memory to tools with the existing memories.read and memories.write
                scope boundary.
              </p>
            </article>
            <article className={styles.card}>
              <span className={styles.cardNumber}>LOCAL</span>
              <h3>Replica-ready</h3>
              <p>
                Keep capture fast and resilient locally, then promote through the backend
                before memory becomes authoritative.
              </p>
            </article>
          </div>
        </section>

        <section className={styles.embed}>
          <div>
            <div className={styles.eyebrow}>For product teams</div>
            <h3>Ship memory inside your own surface.</h3>
            <p>
              Use a same-origin proxy or a sandboxed iframe. Keep Omi credentials on a
              server, keep the embed narrow, and let the backend enforce the boundary.
            </p>
            <Link href="/memory-platform/embed" className={styles.primary}>
              Open embed guide <span aria-hidden="true">↗</span>
            </Link>
          </div>
          <pre className={styles.embedCode}>{`<iframe
  src="https://your-app.example/memory"
  title="Memory"
  loading="lazy"
  sandbox="allow-scripts"
/>`}</pre>
        </section>

        <div className={styles.footerLine}>
          <span>Omi / memory platform / v1</span>
          <span>Canonical memory, wherever it is useful.</span>
        </div>
      </div>
    </div>
  );
}
