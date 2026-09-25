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
    <div className="sn-cta">
      <p className="sn-cta-copy">
        This conversation was captured with Omi — the wearable that remembers everything
        for you.
      </p>
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
  );
}
