import {
  clock,
  dateline,
  degradedSources,
  hours,
  isEmptyEdition,
  isForYouEmpty,
  isPhotoPrintable,
  isTodayClear,
  type Edition,
} from '@/lib/edition';

/**
 * One day's paper, printed.
 *
 * Section order is fixed — yesterday, today, newsletters, for you, the photo —
 * and every section is skipped when it is absent rather than filled with
 * something. The markup follows `backend/templates/paper.html`; the two render
 * the same edition.
 */
export function EditionView({ edition }: { edition: Edition }) {
  const today = edition.today;
  const forYou = edition.for_you;
  const degraded = degradedSources(edition);

  return (
    <>
      <p className="dateline">
        {dateline(edition.date)}
        {edition.issue_number ? ` · No. ${edition.issue_number}` : ''}
      </p>

      {edition.cover?.thesis && (
        <div className="lede">
          <p>{edition.cover.thesis}</p>
          {edition.cover.standfirst && (
            <p className="standfirst">{edition.cover.standfirst}</p>
          )}
        </div>
      )}

      {edition.yesterday && (
        <section>
          <h2>Yesterday</h2>
          {edition.yesterday.headline && <h1>{edition.yesterday.headline}</h1>}
          {edition.yesterday.story && <p>{edition.yesterday.story}</p>}

          {!!edition.yesterday.focus?.length && (
            <div className="focus">
              {edition.yesterday.focus.map((block, i) => (
                <span key={`${block.label}-${i}`} className="stamp">
                  {block.label} {hours(block.minutes ?? 0)}
                </span>
              ))}
            </div>
          )}

          {!!edition.yesterday.decisions?.length && (
            <ul>
              {edition.yesterday.decisions.map((decision, i) => (
                <li key={`${decision}-${i}`}>{decision}</li>
              ))}
            </ul>
          )}

          {edition.yesterday.unacted && (
            <p>
              <span className="stamp">Still open</span>
              <br />
              {edition.yesterday.unacted}
            </p>
          )}
        </section>
      )}

      {today && (
        <section>
          <h2>Today</h2>
          {isTodayClear(today) ? (
            <p className="quiet">Nothing scheduled.</p>
          ) : (
            <>
              {today.note && <p>{today.note}</p>}
              {!!today.events?.length && (
                <ul className="agenda">
                  {today.events.map((event, i) => (
                    <li key={`${event.title}-${i}`}>
                      <time>{clock(event.start)}</time>
                      <span>
                        {event.title}
                        {!!event.attendees?.length && (
                          <span className="sources">
                            {' '}
                            with {event.attendees.join(', ')}
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {!!today.commitments?.length && (
                <ul>
                  {today.commitments.map((commitment, i) => (
                    <li key={`${commitment.text}-${i}`}>
                      {commitment.text}
                      {commitment.due && (
                        <span className="sources"> due {commitment.due}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      )}

      {!!edition.newsletters?.length && (
        <section>
          <h2>Newsletters</h2>
          <ul>
            {edition.newsletters.map((story, i) => (
              <li key={`${story.summary}-${i}`}>
                {story.summary}
                {!!story.sources?.length && (
                  <span className="sources">
                    {' '}
                    ({story.sources.map((source) => source.name).join(', ')})
                  </span>
                )}
                {story.why && (
                  <>
                    <br />
                    <span className="why">{story.why}</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!isForYouEmpty(forYou) && (
        <section>
          <h2>For you</h2>
          {forYou?.papers?.map((item, i) => (
            <div key={`${item.title}-${i}`}>
              <h3>
                {item.url ? (
                  <a href={item.url} rel="noreferrer noopener" target="_blank">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </h3>
              {(item.identifier || item.authors) && (
                <p className="stamp">
                  {item.identifier}
                  {item.authors ? ` · ${item.authors}` : ''}
                </p>
              )}
              {item.what_it_says && <p>{item.what_it_says}</p>}
              {item.why_it_matters && <p className="why">{item.why_it_matters}</p>}
              {item.experiment && (
                <p>
                  <span className="stamp">Try</span>
                  <br />
                  {item.experiment}
                </p>
              )}
            </div>
          ))}
          {!!forYou?.tools?.length && (
            <ul>
              {forYou.tools.map((tool, i) => (
                <li key={`${tool.name}-${i}`}>
                  <b>{tool.name}</b> {tool.what}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {isPhotoPrintable(edition.photo) && (
        <section>
          <h2>Yesterday, drawn</h2>
          <figure>
            {/* A data URI, so next/image would add a proxy hop for no benefit. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              alt={edition.photo?.moment ?? ''}
              src={`data:image/png;base64,${edition.photo?.image_b64}`}
            />
            <figcaption>{edition.photo?.caption || edition.photo?.moment}</figcaption>
          </figure>
        </section>
      )}

      {/* A source that failed is printed. Silent degradation reads as a quiet day. */}
      {!!degraded.length && (
        <section className="degraded">
          <h2>Sources</h2>
          <ul>
            {degraded.map((health, i) => (
              <li key={`${health.source}-${i}`}>
                {health.source} unavailable{health.note ? ` — ${health.note}` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* A quiet day is a real result, not a failure — and never something to pad. */}
      {isEmptyEdition(edition) && <p className="quiet">Nothing to print today.</p>}

      <div className="end">End of edition</div>
    </>
  );
}
