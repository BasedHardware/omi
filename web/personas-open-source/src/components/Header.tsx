/**
 * @fileoverview Header Component for OMI Personas
 * @description Renders the application header with logo and CTA button
 * @author HarshithSunku
 * @license MIT
 */
import { useState } from 'react';
import Link from 'next/link';
import { LoginButton } from '@/components/LoginButton';
import { auth } from '@/lib/firebase';

// Define props interface
interface HeaderProps {
  uid: string | null;
}

/**
 * Header Component
 * 
 * @component
 * @description Renders the main navigation header with OMI logo and call-to-action button
 * @param {HeaderProps} props - Component props
 * @param {string | null} props.uid - The current user ID, or null if not available.
 * @returns {JSX.Element} Rendered Header component
 */
export const Header = ({ uid }: HeaderProps) => {
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const addToolsUrl = uid ? `https://veyrax.com/user/omi/auth?omi_user_id=${encodeURIComponent(uid)}` : '#';

  const handleLoadingChange = (isLoading: boolean) => {
    setIsAuthLoading(isLoading);
  };

  return (
    <div className="p-4 border-b border-zinc-800">
      {/* Keep items justified between on all screen sizes */}
      <div className="flex items-center justify-between max-w-3xl mx-auto">
        <Link href="https://omi.me" target="_blank">
          <img src="/omilogo.png" alt="Logo" className="h-6" />
        </Link>
        {/* Ensure right-side items stay together */}
        <div className="flex items-center gap-4"> {/* Keep gap for items within this group if needed in future */}
          {(isAuthLoading || !uid || (uid && auth.currentUser?.isAnonymous)) && (
            <LoginButton 
              onLoadingChange={handleLoadingChange}
            />
          )}
          <Link
            href="https://www.omi.me/pages/product?ref=personas"
            target="_blank"
            className="bg-white hover:bg-gray-200 text-black px-3 py-1.5 md:px-4 md:py-2 rounded-full flex items-center whitespace-nowrap"
          >
            <span className="mr-1 text-xs md:text-sm">Train AI on your real life</span>
            <span className="text-base md:text-lg">↗</span>
          </Link>
        </div>
      </div>
    </div>
  );
};
