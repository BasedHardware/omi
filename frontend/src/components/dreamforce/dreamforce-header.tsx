'use client';
import Image from 'next/image';
import { useParams } from 'next/navigation';

export default function DreamforceHeader() {
  const params = useParams();

  return (
    <header
      className={`fixed top-0 z-30 flex w-full items-center justify-between bg-black/40 bg-white p-4 px-4 text-white transition-all duration-500 md:bg-transparent md:px-12`}
    >
      <div className="flex items-center gap-2 text-xl">
        <Image
          src={'/omi-black.webp'}
          alt="Based Hardware Logo"
          width={146}
          height={64}
          className="h-auto w-[50px]"
        />
      </div>
      <nav>
        <ul className="flex gap-3 text-sm md:gap-4 md:text-base">
          <li>
            <Image
              src={'/df-logo.webp'}
              alt="Dreamforce Logo"
              width={700}
              height={188}
              className="h-auto w-[118px]"
            />
          </li>
        </ul>
      </nav>
    </header>
  );
}
