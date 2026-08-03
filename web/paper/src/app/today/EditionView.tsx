import { age, dateline, isEmptyEdition, silence, type Edition } from '@/lib/edition';

/**
 * One day's paper, printed.
 *
 * Block order is fixed — lede, open loops, counterpoint, the desk, the margin — and
 * every block is skipped when it is absent rather than filled with something. The
 * markup follows `backend/templates/paper.html`; the two render the same edition.
 */
export function EditionView({ edition }: { edition: Edition }) {
  return (
    <>
      <p className="dateline">
        {dateline(edition.date)}
        {edition.issue_number ? ` · No. ${edition.issue_number}` : ''}
      </p>

      {edition.lede && (
        <div className="lede">
          <h1>{edition.lede.headline}</h1>
          {edition.lede.body && <p>{edition.lede.body}</p>}
        </div>
      )}

      {!!edition.open_loops?.length && (
        <section>
          <h2>Open Loops</h2>
          {edition.open_loops.map((loop, i) => (
            <div className="loop" key={`${loop.question}-${i}`}>
              <p>{loop.question}</p>
              <span className="stamp">{age(loop.days_open ?? 0)}</span>
            </div>
          ))}
        </section>
      )}

      {edition.counterpoint && (
        <section>
          <h2>Counterpoint</h2>
          <span className="stamp">
            Your position, {edition.counterpoint.days_asserted ?? 0} separate days
          </span>
          <blockquote>{edition.counterpoint.position}</blockquote>
          <p>{edition.counterpoint.argument}</p>
        </section>
      )}

      {!!edition.desk?.length && (
        <section>
          <h2>The Desk</h2>
          {edition.desk.map((item, i) => (
            <div className="desk-item" key={`${item.name}-${i}`}>
              <p className="desk-name">{item.name}</p>
              <span className="stamp">{silence(item.days_since ?? 0)}</span>
              {item.context && <p>{item.context}</p>}
            </div>
          ))}
        </section>
      )}

      {edition.margin && (
        <section>
          <h2>The Margin</h2>
          <p className="margin-note">{edition.margin.insight}</p>
        </section>
      )}

      {/* A quiet day is a real result, not a failure — and never something to pad. */}
      {isEmptyEdition(edition) && <p className="quiet">Nothing to print today.</p>}

      <div className="end">End of edition</div>
    </>
  );
}
