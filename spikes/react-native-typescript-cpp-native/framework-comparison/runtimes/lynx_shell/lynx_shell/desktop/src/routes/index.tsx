import type { CSSProperties } from 'react';

const page: CSSProperties = {
  minHeight: '100vh',
  boxSizing: 'border-box',
  padding: '40px 56px 72px',
  background: '#fff',
  color: '#111',
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
};

const card: CSSProperties = {
  border: '1px solid #e5e5e5',
  borderRadius: 18,
  padding: 24,
  background: '#fff',
};

export default function HomePage() {
  return (
    <main style={page}>
      <header style={{ maxWidth: 1080, margin: '0 auto 72px', display: 'flex', justifyContent: 'space-between' }}>
        <strong style={{ fontSize: 28, letterSpacing: -1 }}>omi</strong>
        <span style={{ color: '#777', fontSize: 13 }}>desktop spike · Moonshine</span>
      </header>

      <section style={{ maxWidth: 1080, margin: '0 auto' }}>
        <p style={{ margin: 0, color: '#777', fontSize: 14 }}>YOUR DAY</p>
        <h1 style={{ maxWidth: 640, margin: '14px 0 16px', fontSize: 58, lineHeight: 1.02, letterSpacing: -3 }}>
          A quiet place for the things you remember.
        </h1>
        <p style={{ maxWidth: 520, margin: 0, color: '#666', fontSize: 18, lineHeight: 1.45 }}>
          This desktop surface is ready for real Omi data. It does not invent a device, a recording, or a transcript.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.5fr) minmax(280px, 1fr)', gap: 16, marginTop: 48 }}>
          <article style={{ ...card, minHeight: 260 }}>
            <p style={{ margin: 0, fontWeight: 800, fontSize: 18 }}>Today</p>
            <p style={{ marginTop: 72, marginBottom: 0, fontSize: 42, fontWeight: 800 }}>—</p>
            <p style={{ margin: '8px 0 0', color: '#777', lineHeight: 1.4 }}>No moments yet. Connect a real Omi to begin.</p>
          </article>
          <article style={{ ...card, background: '#f7f7f7' }}>
            <p style={{ margin: 0, fontWeight: 800, fontSize: 18 }}>Device</p>
            <div style={{ marginTop: 36, width: 64, height: 64, border: '1px solid #111', borderRadius: '50%', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 900 }}>omi</div>
            <p style={{ margin: '24px 0 0', fontWeight: 800 }}>Bluetooth not connected</p>
            <p style={{ margin: '8px 0 0', color: '#777', lineHeight: 1.4 }}>The desktop adapter is intentionally not faked.</p>
          </article>
        </div>

        <article style={{ ...card, marginTop: 16, borderStyle: 'dashed' }}>
          <p style={{ margin: 0, fontWeight: 800, fontSize: 18 }}>What comes next</p>
          <p style={{ margin: '10px 0 0', color: '#666', lineHeight: 1.45 }}>Implement the real desktop BLE/native adapter, then connect this surface to the shared relay contract.</p>
        </article>
      </section>
    </main>
  );
}
