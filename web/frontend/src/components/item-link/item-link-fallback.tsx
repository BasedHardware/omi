import { headers } from 'next/headers';
import { notFound } from 'next/navigation';
import {
  getOmiInstallLink,
  getOmiPlatformDeepLink,
} from '@/src/lib/conversation-share-platform-link.mjs';
import { isItemLinkId, itemLinkWebHandoff } from '@/src/lib/item-link.mjs';

const APP_STORE = 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163';
const PLAY_STORE = 'https://play.google.com/store/apps/details?id=com.friend.ios';

/**
 * What h.omi.me/<kind>/<id> shows when the Omi app did not open the link.
 * Deliberately content-free: it never reads the item, so nobody sees private
 * data without signing in, and link-preview crawlers see only the Omi brand.
 */
export async function ItemLinkFallback({
  kind,
  id,
}: {
  kind: 'conversation' | 'task' | 'memory';
  id: string;
}) {
  if (!isItemLinkId(id)) notFound();

  const userAgent = (await headers()).get('user-agent') || '';
  const isMobile = /android|iphone|ipad|ipod/i.test(userAgent);
  const openInApp = getOmiPlatformDeepLink(userAgent, `${kind}/${id}`);
  const install = getOmiInstallLink(userAgent);
  const webHandoff = itemLinkWebHandoff(kind, id);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0B0F17] px-4 py-24 text-center">
      <h1 className="mb-3 text-3xl font-bold text-white sm:text-4xl">
        Open in the Omi app
      </h1>
      <p className="mb-8 max-w-md text-base text-gray-400 sm:text-lg">
        This link opens in Omi. Sign in to see it.
      </p>

      <div className="flex w-full max-w-xs flex-col gap-3">
        {isMobile ? (
          <>
            <a
              href={openInApp}
              data-testid="item-link-open-app"
              className="rounded-xl bg-white px-6 py-3 font-semibold text-[#0B0F17] transition-colors hover:bg-gray-200"
            >
              Open in the Omi App
            </a>
            <a
              href={install}
              data-testid="item-link-install"
              className="rounded-xl border border-white/20 px-6 py-3 font-semibold text-white transition-colors hover:bg-white/10"
            >
              {/android/i.test(userAgent)
                ? 'Get It on Google Play'
                : 'Download on the App Store'}
            </a>
          </>
        ) : (
          <>
            <a
              href={APP_STORE}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl bg-white px-6 py-3 font-semibold text-[#0B0F17] transition-colors hover:bg-gray-200"
            >
              Download on the App Store
            </a>
            <a
              href={PLAY_STORE}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl border border-white/20 px-6 py-3 font-semibold text-white transition-colors hover:bg-white/10"
            >
              Get It on Google Play
            </a>
          </>
        )}
        <a
          href={webHandoff}
          data-testid="item-link-web-handoff"
          className="mt-2 text-sm text-gray-400 underline hover:text-white"
        >
          Sign in on the web
        </a>
      </div>
    </div>
  );
}
