'use client';
import Image from 'next/image';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import ShareButton from '../memories/share-button';
import { useParams, usePathname } from 'next/navigation';

export default function AppHeader() {
  const [scrollPosition, setScrollPosition] = useState(0);
  const params = useParams();
  const pathname = usePathname();

  const dreamforcePage = pathname.includes('dreamforce');

  useEffect(() => {
    const handleScroll = () => {
      setScrollPosition(window.scrollY);
    };

    window.addEventListener('scroll', handleScroll);

    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  return !dreamforcePage ? (
    <>
      <header
        className={`fixed top-0 z-30 flex w-full items-center justify-between bg-black/40 p-4 px-4 text-white transition-all duration-500 md:bg-transparent md:px-12 ${
          scrollPosition > 100 ? 'backdrop-blur-md md:!bg-black md:!bg-opacity-10' : ''
        }`}
      >
        <h1 className="flex items-center gap-2 text-xl">
          <Image
            src={'/omi-white.webp'}
            alt="Based Hardware Logo"
            width={146}
            height={64}
            className="h-auto w-[50px]"
          />
        </h1>
        <nav>
          <ul className="flex gap-3 text-sm md:gap-4 md:text-base">
            {params.id && (
              <li>
                <ShareButton />
              </li>
            )}
            <li>
              <Link
                href={`https://basedhardware.com/`}
                target="_blank"
                className="flex items-center gap-2 rounded-md bg-white/90 p-1.5 px-3.5 text-black transition-colors hover:bg-white"
              >
                Order now
              </Link>
            </li>
            <li>
              <Link
                href={`https://docs.omi.me/developer/plugins/Introduction`}
                target="_blank"
                className="flex items-center gap-2 rounded-md bg-white/90 p-1.5 px-3.5 text-black transition-colors hover:bg-white"
              >
                Build App
              </Link>
            </li>
          </ul>
        </nav>
      </header>
      <div className="fixed top-16 z-30 w-full bg-blue-500 p-2 text-center text-white">
        <span>Submit your own App by November 30th and get a free trip to OMI HQ in San Francisco</span>
        <Link
          href="https://discord.gg/omi"
          target="_blank"
          className="ml-4 inline-block rounded-md bg-white px-3 py-1 text-blue-500 hover:bg-blue-100"
        >
          Join Hackathon
        </Link>
      </div>
    </>
  ) : null;
}
