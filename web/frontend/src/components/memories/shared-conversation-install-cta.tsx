import Image from 'next/image';
import { getConversationSharePlatformLink } from '@/src/lib/conversation-share-platform-link.mjs';

export { getConversationSharePlatformLink };

interface SharedConversationInstallCtaProps {
  openInOmiHref: string;
}

/** Install / open funnel matching chat + tasks share pages. */
export default function SharedConversationInstallCta({
  openInOmiHref,
}: SharedConversationInstallCtaProps) {
  return (
    <section className="sn-cta" aria-label="Get Omi">
      <div>
        <h2 className="sn-cta-title">Notes like this, from every conversation.</h2>
        <p className="sn-cta-copy">
          Omi listens, writes the notes, and remembers — on your phone, your Mac, or the
          Omi wearable.
        </p>
      </div>
      <div className="sn-cta-actions">
        <a href={openInOmiHref} className="sn-cta-button">
          Open in Omi
        </a>
        <div className="sn-cta-badges">
          <a
            href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
            target="_blank"
            rel="noopener noreferrer"
          >
            <Image
              src="/app-store-badge.svg"
              alt="Download on the App Store"
              className="h-[40px]"
              width={120}
              height={40}
            />
          </a>
          <a
            href="https://play.google.com/store/apps/details?id=com.friend.ios"
            target="_blank"
            rel="noopener noreferrer"
          >
            <Image
              src="/google-play-badge.png"
              alt="Get it on Google Play"
              className="h-[40px]"
              width={135}
              height={40}
            />
          </a>
        </div>
      </div>
    </section>
  );
}
