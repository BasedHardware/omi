import Link from 'next/link';

export default function RootNotFound() {
  return (
    <html lang="en">
      <body style={{ background: '#0F0F0F', color: '#fff', fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1.5rem' }}>
          <div style={{ textAlign: 'center', maxWidth: '28rem' }}>
            <h1 style={{ fontSize: '3rem', fontWeight: 700, color: '#3B82F6', marginBottom: '1rem' }}>404</h1>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.75rem' }}>Page not found</h2>
            <p style={{ color: '#888', fontSize: '0.875rem', marginBottom: '2rem' }}>The page you&apos;re looking for doesn&apos;t exist.</p>
            <a href="/" style={{ background: '#fff', color: '#000', fontSize: '0.875rem', fontWeight: 500, padding: '0.75rem 1.5rem', borderRadius: '9999px', textDecoration: 'none' }}>
              Go home
            </a>
          </div>
        </div>
      </body>
    </html>
  );
}
