'use client';

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary px-6">
      <div className="text-center max-w-md">
        <h1 className="font-display font-bold text-4xl mb-4">Something went wrong</h1>
        <p className="text-text-tertiary text-sm mb-8">{error.message || 'An unexpected error occurred.'}</p>
        <button
          onClick={reset}
          className="bg-brand hover:bg-brand-dark text-white text-sm font-medium px-6 py-3 rounded-full transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
