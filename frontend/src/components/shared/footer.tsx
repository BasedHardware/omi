import { Discord, Github, Instagram, Linkedin, Tiktok, X } from 'iconoir-react';
import Image from 'next/image';

export default function Footer() {
  return (
    <footer className="footer w-full border-t border-solid border-zinc-800 bg-black/5 px-4 py-12 text-white md:px-12">
      <div className="mx-auto flex max-w-screen-xl flex-wrap justify-between gap-12">
        <div>
          <Image
            src={'/omi-white.webp'}
            alt="Based Hardware Logo"
            width={146}
            height={64}
            className="h-auto w-[70px]"
          />
          <p className="mt-1 text-gray-500">Made in San Fransisco</p>
          <a href={'mailto:team@basedhardware.com>'} className="hover:underline">
            team@basedhardware.com
          </a>
          <div className="mt-3 flex items-center gap-3">
            <a
              href="https://x.com/based_hardware"
              target="_blank"
              rel="noopener noreferrer"
            >
              <X />
            </a>
            <a
              href="https://www.linkedin.com/company/omi-ai/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Linkedin />
            </a>
            <a
              href="https://github.com/BasedHardware"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Github />
            </a>
            <a
              href="https://www.tiktok.com/@based_hardware"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Tiktok />
            </a>
            <a
              href="https://www.instagram.com/based_hardware/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Instagram />
            </a>
            <a
              href="https://discord.com/invite/ZutWMTJnwA"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Discord />
            </a>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-10 md:gap-20">
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Products</li>
            <li>
              <a
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'https://www.omi.me/pages/openglass'}
                target="_blank"
              >
                OpenGlass
              </a>
            </li>
            <li>
              <a
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'https://www.omi.me/'}
                target="_blank"
              >
                Friend
              </a>
            </li>
            <li>
              <a
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'https://www.omi.me/pages/friend-dev'}
                target="_blank"
              >
                Friend DEV KIT
              </a>
            </li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Other</li>
            <li>
              <a
                href="https://airtable.com/appyGfrqMxoUaD1mg/shrswR2uD1LRoFkFX"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Residency
              </a>
            </li>
            <li>
              <a
                href="https://affiliate.basedhardware.com/"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Affiliate
              </a>
            </li>
            <li>
              <a
                href="https://www.omi.me/pages/privacy"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Privacy
              </a>
            </li>
            <li>
              <a
                href="https://coda.io/@kodjima33/customizations"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Customizations
              </a>
            </li>
            <li>
              <a
                href="https://discord.com/invite/8MP3b9ymvx"
                target={'_blank'}
                rel={'noreferrer'}
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
                href={'https://www.omi.me/pages/about'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                About
              </a>
            </li>
            <li>
              <a
                href={'https://airtable.com/appyGfrqMxoUaD1mg/shrkALjXdq7mJMM1W'}
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
