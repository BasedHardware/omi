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
    <div className="mt-12 text-center md:mt-16">
      <a
        href={openInOmiHref}
        className="inline-block rounded-2xl bg-white px-10 py-4 text-lg font-semibold text-black transition-all duration-300 hover:translate-y-[-2px] hover:bg-gray-100"
      >
        Open in Omi
      </a>

      <div className="mt-6 flex items-center justify-center gap-4">
        <a
          href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
          target="_blank"
          rel="noopener noreferrer"
          className="transition-transform duration-300 hover:scale-105"
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
          className="transition-transform duration-300 hover:scale-105"
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
