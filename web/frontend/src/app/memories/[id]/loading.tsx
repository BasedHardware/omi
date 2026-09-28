import ShareThemeBoot from '@/src/components/memories/share/share-theme-boot';
import './share-note.css';

/** Placeholder in the note's own layout while the shared conversation loads. */
export default function Loading() {
  return (
    <>
      <ShareThemeBoot />
      <div className="share-note" aria-busy="true" aria-label="Loading shared note">
        <div className="sn-topbar" />
        <section className="sn-page">
          <div className="sn-skeleton" style={{ height: 14, width: 140 }} />
          <div
            className="sn-skeleton"
            style={{ height: 40, width: '80%', marginTop: 20 }}
          />
          <div
            className="sn-skeleton"
            style={{ height: 14, width: 220, marginTop: 18 }}
          />
          <div
            className="sn-skeleton"
            style={{ height: 44, width: 300, marginTop: 36, borderRadius: 999 }}
          />
          {[100, 94, 88, 60].map((width, index) => (
            <div
              key={index}
              className="sn-skeleton"
              style={{ height: 14, width: `${width}%`, marginTop: index === 0 ? 44 : 14 }}
            />
          ))}
        </section>
      </div>
    </>
  );
}
