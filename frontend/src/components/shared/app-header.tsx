'use client';

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
      className={`sticky top-0 flex items-center justify-between p-4 text-white backdrop-blur-md transition-all duration-500 ${
        scrollPosition > 100 ? 'bg-black bg-opacity-10' : ''
      }`}
    >
      <h1 className="text-xl">Base Hardware</h1>
      <nav>
        <ul className="flex space-x-4">
          <li>
            <a href="/" className="hover:underline">
              Home
            </a>
          </li>
          <li>
            <a href="/memories" className="hover:underline">
              Memories
            </a>
          </li>
        </ul>
      </nav>
    </header>
  );
}
