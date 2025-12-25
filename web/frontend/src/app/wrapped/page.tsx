import { headers } from 'next/headers';
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Your 2025 Wrapped | Omi',
  description:
    'See your personalized Omi Wrapped for 2025. Discover your memories, conversations, and highlights from the year.',
  openGraph: {
    title: 'Your 2025 Wrapped | Omi',
    description: 'See your personalized Omi Wrapped for 2025.',
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

export default async function WrappedPage() {
  const userAgent = headers().get('user-agent') || '';
  const isMobile = isMobileDevice(userAgent);
  const appStoreLink = getAppStoreLink(userAgent);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0B0F17] px-4 text-center">
      <h1 className="mb-4 text-4xl font-bold text-white">Omi Wrapped 2025</h1>
      <p className="mb-8 max-w-md text-lg text-gray-400">
        View your personalized year in review in the Omi app.
      </p>

      {isMobile ? (
        <>
          <a
            href={appStoreLink}
            className="mb-4 rounded-xl bg-white px-8 py-4 text-lg font-semibold text-[#0B0F17] transition-all duration-300 hover:bg-gray-200"
          >
            Get the Omi App
          </a>
        </>
      ) : (
        <>
          <p className="mb-6 text-gray-400">
            Visit this page on your mobile device to see your Wrapped.
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
