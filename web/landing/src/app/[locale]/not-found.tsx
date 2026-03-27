import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary px-6">
      <div className="text-center max-w-md">
        <h1 className="font-display font-bold text-6xl text-brand mb-4">404</h1>
        <h2 className="font-display font-bold text-2xl mb-3">Page not found</h2>
        <p className="text-text-tertiary text-sm mb-8">The page you're looking for doesn't exist or has been moved.</p>
        <Link
          href="/"
          className="inline-flex bg-white text-black text-sm font-medium px-6 py-3 rounded-full hover:bg-white/90 transition-colors"
        >
          Go home
        </Link>
      </div>
    </div>
  );
}
