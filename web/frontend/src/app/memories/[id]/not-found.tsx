import SharedConversationInstallCta from '@/src/components/memories/shared-conversation-install-cta';

/** Conversation-scoped not-found (only for /memories/[id], not the whole /memories group). */
export default function NotFound() {
  return (
    <div className="font-system-ui min-h-screen bg-gradient-to-b from-[#1a0a1f] via-[#0a0a2f] to-black">
      <div className="absolute inset-0 bg-[radial-gradient(circle_500px_at_50%_200px,rgba(88,28,135,0.2),transparent)]" />
      <section className="relative mx-auto max-w-screen-md px-6 py-24 text-center md:px-12 md:py-32">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-white/55">
          Shared from Omi
        </p>
        <h1 className="text-2xl font-bold text-white sm:text-3xl">
          This conversation isn&apos;t available
        </h1>
        <p className="mx-auto mt-4 max-w-md text-base leading-7 text-gray-400">
          The link may be private, expired, or removed. Download Omi to capture and share
          your own conversations.
        </p>
        <SharedConversationInstallCta openInOmiHref="https://omi.me" />
      </section>
    </div>
  );
}
