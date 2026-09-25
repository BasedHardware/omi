import SharedConversationInstallCta from '@/src/components/memories/shared-conversation-install-cta';
import './share-note.css';

/** Conversation-scoped not-found (only for /memories/[id], not the whole /memories group). */
export default function NotFound() {
  return (
    <div className="share-note">
      <section className="sn-page sn-notfound">
        <p className="sn-eyebrow">Shared from Omi</p>
        <h1 className="sn-title">This conversation isn&apos;t available</h1>
        <p className="sn-notfound-copy">
          The link may be private, expired, or removed. Download Omi to capture and share
          your own conversations.
        </p>
        <SharedConversationInstallCta openInOmiHref="https://omi.me" />
      </section>
    </div>
  );
}
