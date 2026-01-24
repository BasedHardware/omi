import { headers } from 'next/headers';
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Omi Unlimited | Omi',
  description:
    'Unlock the full potential with Unlimited. Get advanced AI capabilities, longer memory retention, and more.',
  openGraph: {
    title: 'Omi Unlimited | Omi',
    description: 'Unlock the full potential with Unlimited.',
    type: 'website',
  },
};

function isMobileDevice(userAgent: string): boolean {
  return /android|iphone|ipad|ipod|mobile/i.test(userAgent);
}

function getAppStoreLink(userAgent: string): string {
  const isAndroid = /android/i.test(userAgent);
  return isAndroid
    ? 'https://play.google.com/store/apps/details?id=com.friend.ios'
    : 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163';
}

export default async function UnlimitedPage() {
  const userAgent = headers().get('user-agent') || '';
  const isMobile = isMobileDevice(userAgent);
  const appStoreLink = getAppStoreLink(userAgent);
  const deepLink = 'omi://h.omi.me/unlimited';

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0B0F17] px-4 text-center">
      <h1 className="mb-4 text-4xl font-bold text-white">Omi Unlimited</h1>
      <p className="mb-8 max-w-md text-lg text-gray-400">
        Unlock the full potential with Omi Unlimited.
      </p>

      {isMobile ? (
        <div className="flex flex-col gap-4">
          <a
            href={deepLink}
            className="rounded-xl bg-white px-8 py-4 text-lg font-semibold text-[#0B0F17] transition-all duration-300 hover:bg-gray-200"
          >
            Open in App
          </a>
          <a
            href={appStoreLink}
            className="text-gray-400 underline hover:text-white"
          >
            Don't have the app? Download here
          </a>
        </div>
      ) : (
        <>
          <p className="mb-6 text-gray-400">
            Visit this page on your mobile device to upgrade.
          </p>
          <div className="flex gap-4">
            <a
              href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl bg-white px-6 py-3 font-semibold text-[#0B0F17] transition-all duration-300 hover:bg-gray-200"
            >
              Download for iOS
            </a>
            <a
              href="https://play.google.com/store/apps/details?id=com.friend.ios"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-xl bg-white px-6 py-3 font-semibold text-[#0B0F17] transition-all duration-300 hover:bg-gray-200"
            >
              Download for Android
            </a>
          </div>
        </>
      )}
    </div>
  );
}
