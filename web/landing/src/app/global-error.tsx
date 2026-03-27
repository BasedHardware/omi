'use client';

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ background: '#0F0F0F', color: '#fff', fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1.5rem' }}>
          <div style={{ textAlign: 'center', maxWidth: '28rem' }}>
            <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '1rem' }}>Something went wrong</h1>
            <p style={{ color: '#888', fontSize: '0.875rem', marginBottom: '2rem' }}>{error.message || 'An unexpected error occurred.'}</p>
            <button
              onClick={reset}
              style={{ background: '#3B82F6', color: '#fff', fontSize: '0.875rem', fontWeight: 500, padding: '0.75rem 1.5rem', borderRadius: '9999px', border: 'none', cursor: 'pointer' }}
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
