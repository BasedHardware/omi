/**
 * @fileoverview Header Component for OMI Personas
 * @description Renders the application header with logo and CTA button
 * @author HarshithSunku
 * @license MIT
 */
import Link from 'next/link';

/**
 * Header Component
 * 
 * @component
 * @description Renders the main navigation header with OMI logo and call-to-action button
 * @returns {JSX.Element} Rendered Header component
 */
export const Header = () => (
  <div className="p-4 border-b border-zinc-800">
    <div className="flex items-center justify-between max-w-3xl mx-auto">
      <Link href="https://www.omi.me/products/friend-dev-kit-2?ref=personas&utm_source=personas.omi.me&utm_campaign=personas_top_banner" target="_blank">
        <img src="/omilogo.png" alt="Logo" className="h-6" />
      </Link>
      <Link
        href="https://www.omi.me/products/friend-dev-kit-2?ref=personas&utm_source=personas.omi.me&utm_campaign=personas_top_banner"
        target="_blank"
        className="bg-white hover:bg-gray-200 text-black px-4 py-2 rounded-full flex items-center"
      >
        <span className="mr-1">Take AI personas with you</span>
        <span className="text-lg">↗</span>
      </Link>
    </div>
  </div>
);
