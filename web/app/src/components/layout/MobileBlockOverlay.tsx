'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import Image from 'next/image';

type Platform = 'ios' | 'android' | 'other';

// Paths that should bypass mobile detection (pop-out windows, etc.)
const BYPASS_MOBILE_CHECK_PATHS = [
  '/record/popout',
  '/record/popout/transcript',
];

const APP_STORE_URL = 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163';
const PLAY_STORE_URL = 'https://play.google.com/store/apps/details?id=com.friend.ios';

function AppleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
    </svg>
  );
}

function PlayStoreIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M3,20.5V3.5C3,2.91 3.34,2.39 3.84,2.15L13.69,12L3.84,21.85C3.34,21.6 3,21.09 3,20.5M16.81,15.12L6.05,21.34L14.54,12.85L16.81,15.12M20.16,10.81C20.5,11.08 20.75,11.5 20.75,12C20.75,12.5 20.53,12.9 20.18,13.18L17.89,14.5L15.39,12L17.89,9.5L20.16,10.81M6.05,2.66L16.81,8.88L14.54,11.15L6.05,2.66Z" />
    </svg>
  );
}

export function MobileBlockOverlay() {
  const pathname = usePathname();
  const [isMobile, setIsMobile] = useState(false);
  const [platform, setPlatform] = useState<Platform>('other');
  const [mounted, setMounted] = useState(false);

  // Check if current path should bypass mobile detection
  const shouldBypass = BYPASS_MOBILE_CHECK_PATHS.some(path => pathname?.startsWith(path));

  useEffect(() => {
    setMounted(true);

    // Check viewport width
    const checkMobile = () => setIsMobile(window.innerWidth < 1024);
    checkMobile();
    window.addEventListener('resize', checkMobile);

    // Detect platform via user agent
    const ua = navigator.userAgent.toLowerCase();
    if (/iphone|ipad|ipod/.test(ua)) {
      setPlatform('ios');
    } else if (/android/.test(ua)) {
      setPlatform('android');
    }

    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Don't render anything on server, if not mobile, or if on bypass path
  if (!mounted || !isMobile || shouldBypass) return null;

  const storeUrl = platform === 'android' ? PLAY_STORE_URL : APP_STORE_URL;
  const storeName = platform === 'android' ? 'Google Play' : 'App Store';
  const StoreIcon = platform === 'android' ? PlayStoreIcon : AppleIcon;

  return (
    <div className="fixed inset-0 z-[9999] bg-bg-primary flex flex-col items-center justify-center p-6">
      {/* Beta badge - top right corner */}
      <a
        href="https://feedback.omi.me"
        target="_blank"
        rel="noopener noreferrer"
        className="absolute top-4 right-4 z-20 px-3 py-1 bg-purple-primary/20 text-purple-primary text-xs font-semibold uppercase tracking-wider rounded-full border border-purple-primary/30 hover:bg-purple-primary/30 transition-colors"
      >
        Beta
      </a>

      {/* Background gradient effect - matches login page */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-purple-primary/5 rounded-full blur-[120px]" />
      </div>

      {/* Main content container */}
      <div className="relative z-10 flex flex-col items-center justify-center flex-1 max-w-sm text-center">
        {/* Round logo with breathing glow */}
        <div className="relative mb-8">
          {/* Breathing glow effect - matches login page style */}
          <div
            className="absolute inset-0 rounded-full bg-purple-primary/20 blur-xl animate-pulse"
            style={{ animationDuration: '3s' }}
          />
          <div className="w-28 h-28 relative">
            <Image
              src="/logo.png"
              alt="Omi"
              fill
              className="object-contain relative z-10 drop-shadow-[0_0_15px_rgba(139,92,246,0.3)]"
              priority
            />
          </div>
        </div>

        {/* Message */}
        <h1 className="text-2xl font-semibold text-text-primary mb-3">
          Omi Web is optimized for desktop.
        </h1>
        <p className="text-text-tertiary mb-8">
          For the best mobile experience, download the Omi app.
        </p>

        {/* App Store Button */}
        <a
          href={storeUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-3 bg-white text-black px-6 py-3 rounded-xl font-medium hover:bg-gray-100 transition-colors"
        >
          <StoreIcon className="w-6 h-6" />
          <span>Download on {storeName}</span>
        </a>
      </div>

      {/* Bottom section with logo and links */}
      <div className="relative z-10 pb-8 flex flex-col items-center gap-4">
        <Image
          src="/omi-white.webp"
          alt="Omi"
          width={60}
          height={24}
          priority
        />
        <div className="flex items-center gap-4 text-sm text-text-quaternary">
          <a
            href="https://www.omi.me/"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-text-tertiary transition-colors"
          >
            About
          </a>
          <span>·</span>
          <a
            href="https://www.omi.me/pages/privacy"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-text-tertiary transition-colors"
          >
            Privacy
          </a>
          <span>·</span>
          <a
            href="https://help.omi.me/"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-text-tertiary transition-colors"
          >
            Help
          </a>
        </div>
      </div>
    </div>
  );
}
