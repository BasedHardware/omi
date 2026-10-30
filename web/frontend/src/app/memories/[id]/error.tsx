'use client';

import './share-note.css';

/** A shared note that failed to render (network or server error, not a missing note). */
export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="share-note">
      <section className="sn-page sn-notfound">
        <p className="sn-eyebrow">Shared from Omi</p>
        <h1 className="sn-title">This note didn&apos;t load</h1>
        <p className="sn-notfound-copy">
          Something went wrong on our side. Try again in a moment.
        </p>
        <div
          style={{ marginTop: 28, display: 'flex', justifyContent: 'center', gap: 12 }}
        >
          <button type="button" className="sn-pill" onClick={() => reset()}>
            Try again
          </button>
          <a href="https://omi.me" className="sn-pill sn-pill-ghost">
            Go to omi.me
          </a>
        </div>
      </section>
    </div>
  );
}
