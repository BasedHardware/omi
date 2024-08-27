'use client';

import { ShareIos } from 'iconoir-react';
import Image from 'next/image';
import Link from 'next/link';
import { useEffect, useState } from 'react';

export default function AppHeader() {
  const [scrollPosition, setScrollPosition] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      setScrollPosition(window.scrollY);
    };

    window.addEventListener('scroll', handleScroll);

    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  return (
    <header
      className={`sticky top-0 flex items-center justify-between p-4 text-white backdrop-blur-md transition-all duration-500 px-12 ${
        scrollPosition > 100 ? 'bg-black bg-opacity-10' : ''
      }`}
    >
      <h1 className="text-xl flex gap-2 items-center">
        <Image src={'/logo.webp'} alt="Based Hardware Logo" width={25} height={30} />
        Based Hardware</h1>
      <nav>
        <ul className="flex space-x-4">
          <li>
            <button className='flex gap-2 items-center border border-solid border-zinc-600 p-1.5 px-3.5 rounded-md hover:bg-zinc-800 transition-colors'>
              <ShareIos className='text-xs'/>
              Share
            </button>
          </li>
          <li>
            <Link href={`https://basedhardware.com/`} target='_blank' className='flex gap-2 items-center p-1.5 px-3.5 rounded-md bg-white/90 hover:bg-white text-black transition-colors'>
              Order now
            </Link>
          </li>
        </ul>
      </nav>
    </header>
  );
}
