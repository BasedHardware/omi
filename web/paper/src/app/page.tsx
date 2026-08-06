const BLOCKS = [
  ['Yesterday', 'Where the day went, and what you decided.'],
  ['Today', 'What is on you, before anyone asks.'],
  ['Newsletters', 'Everything you subscribed to, one line per story.'],
  ['For you', 'The papers and tools that move what you are working on.'],
  ['The photo', 'One moment from yesterday, drawn.'],
];

const SIGNUP =
  'mailto:paper@omi.me?subject=Tomorrow%27s%20edition&body=Send%20me%20tomorrow%27s%20edition.';

export default function Home() {
  return (
    <main className="wrap top">
      <h1 className="masthead">PAPER</h1>
      <p className="dateline">One page &middot; Once a day &middot; Then it ends</p>

      <p className="claim">
        Every news app reads what you click.
        <br />
        This one reads what you lived.
      </p>

      <p className="sub">
        No topics to pick. It builds each morning from what you actually talked about —
        the questions you left open, the people you stopped mentioning, the position you
        keep taking without arguing the other side.
      </p>

      <div className="actions">
        <a className="cta" href={SIGNUP}>
          Get tomorrow&rsquo;s edition
        </a>
        <a className="cta-secondary" href="#edition">
          See what&rsquo;s in one &darr;
        </a>
      </div>

      <section id="edition">
        <span className="label">What&rsquo;s in one</span>
        <p className="stat">
          It ends. <span>That is the feature.</span>
        </p>
        <ul className="blocks">
          {BLOCKS.map(([name, what]) => (
            <li key={name}>
              <span className="name">{name}</span>
              <span className="what">{what}</span>
            </li>
          ))}
        </ul>
        <p className="fine">
          Then it prints <em>End of edition</em>. Nothing loads when you reach the bottom.
        </p>
      </section>

      <section>
        <span className="label">Price</span>
        <p className="stat">$12 a month.</p>
        <p className="fine">
          The free tier prints yesterday. Paying reads the outside world through your own
          context — your newsletters, your papers, your day ahead. Cancel whenever; there
          is no lifetime plan.
        </p>
        <div className="actions">
          <a className="cta" href={SIGNUP}>
            Get tomorrow&rsquo;s edition
          </a>
        </div>
      </section>

      <footer>Built on Omi</footer>
    </main>
  );
}
