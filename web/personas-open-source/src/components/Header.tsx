/**
 * @fileoverview Header Component for OMI Personas
 * @description Renders the application header with logo and CTA button
 * @author HarshithSunku
 * @license MIT
 */
import Link from 'next/link';

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
  const addToolsUrl = uid ? `https://veyrax.com/user/omi/auth?omi_user_id=${encodeURIComponent(uid)}` : '#';

  return (
    <div className="p-4 border-b border-zinc-800">
      <div className="flex items-center justify-between max-w-3xl mx-auto">
        <Link href="https://omi.me" target="_blank">
          <img src="/omilogo.png" alt="Logo" className="h-6" />
        </Link>
        <div className="flex items-center"> {/* Wrap right-side elements */}
          {/* Conditional "Add more tools" link */}
          {uid && (
            <a 
              href={addToolsUrl}
              target="_blank" 
              rel="noopener noreferrer"
              className="text-sm text-white hover:text-zinc-300 hover:underline mr-4"
            >
              Add more tools
            </a>
          )}
          {/* Existing "Train AI" link */}
          <Link
            href="https://www.omi.me/pages/product?ref=personas"
            target="_blank"
            className="bg-white hover:bg-gray-200 text-black px-4 py-2 rounded-full flex items-center"
          >
            <span className="mr-1 text-sm">Train AI on your real life</span> {/* Added text-sm */}
            <span className="text-lg">↗</span>
          </Link>
        </div>
      </div>
    </div>
  );
};
