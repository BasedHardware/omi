'use client';

import { Twitter, Linkedin, Github } from 'lucide-react';
import Image from 'next/image';

export function Footer() {
  return (
    <footer className="w-full border-t border-solid border-zinc-800 bg-[#0B0F17] px-4 py-12 text-white md:px-12">
      <div className="mx-auto flex max-w-screen-xl flex-wrap justify-between gap-12">
        <div>
          <Image
            src="/omi-white.webp"
            alt="Omi Logo"
            width={146}
            height={64}
            className="h-auto w-[70px]"
          />
          <p className="mt-1 text-gray-500">Made in San Francisco</p>
          <a href="mailto:team@basedhardware.com" className="hover:underline">
            team@basedhardware.com
          </a>
          <div className="mt-3 flex items-center gap-3">
            <a
              href="https://x.com/based_hardware"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-white transition-colors"
            >
              <Twitter className="h-5 w-5" />
            </a>
            <a
              href="https://www.linkedin.com/company/omi-ai/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-white transition-colors"
            >
              <Linkedin className="h-5 w-5" />
            </a>
            <a
              href="https://github.com/BasedHardware"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-400 hover:text-white transition-colors"
            >
              <Github className="h-5 w-5" />
            </a>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-10 md:gap-20">
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Products</li>
            <li>
              <a
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href="https://www.omi.me/pages/openglass"
                target="_blank"
                rel="noreferrer"
              >
                OpenGlass
              </a>
            </li>
            <li>
              <a
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href="https://www.omi.me/"
                target="_blank"
                rel="noreferrer"
              >
                Omi AI
              </a>
            </li>
            <li>
              <a
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href="https://www.omi.me/products/omi-dev-kit-2"
                target="_blank"
                rel="noreferrer"
              >
                Omi DEV KIT 2
              </a>
            </li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Other</li>
            <li>
              <a
                href="https://airtable.com/appyGfrqMxoUaD1mg/shrswR2uD1LRoFkFX"
                target="_blank"
                rel="noreferrer"
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Residency
              </a>
            </li>
            <li>
              <a
                href="https://affiliate.basedhardware.com/"
                target="_blank"
                rel="noreferrer"
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Affiliate
              </a>
            </li>
            <li>
              <a
                href="https://www.omi.me/pages/privacy"
                target="_blank"
                rel="noreferrer"
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Privacy
              </a>
            </li>
            <li>
              <a
                href="https://discord.com/invite/8MP3b9ymvx"
                target="_blank"
                rel="noreferrer"
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Discord
              </a>
            </li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Company</li>
            <li>
              <a
                href="https://www.omi.me/pages/about"
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                About
              </a>
            </li>
            <li>
              <a
                href="https://airtable.com/appyGfrqMxoUaD1mg/shrkALjXdq7mJMM1W"
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Invest
              </a>
            </li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
