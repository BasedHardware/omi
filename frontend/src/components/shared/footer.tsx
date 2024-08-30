import { Discord, Github, Instagram, Linkedin, Tiktok, X } from 'iconoir-react';
import Link from 'next/link';

export default function Footer() {
  return (
    <footer className="footer w-full border-t border-solid border-zinc-800 bg-black/5 px-4 py-12 text-white md:px-12">
      <div className="mx-auto flex max-w-screen-xl flex-wrap justify-between gap-12">
        <div>
          <h2 className="text-4xl font-semibold">Omi</h2>
          <p className="text-gray-500">San Fransisco</p>
          <Link href={'mailto:team@basedhardware.com>'} className="hover:underline">
            team@basedhardware.com
          </Link>
          <div className="mt-3 flex items-center gap-3">
            <Link
              href="https://x.com/based_hardware"
              target="_blank"
              rel="noopener noreferrer"
            >
              <X />
            </Link>
            <Link
              href="https://www.linkedin.com/company/omi-ai/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Linkedin />
            </Link>
            <Link
              href="https://github.com/BasedHardware"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Github />
            </Link>
            <Link
              href="https://www.tiktok.com/@based_hardware"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Tiktok />
            </Link>
            <Link
              href="https://www.instagram.com/based_hardware/"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Instagram />
            </Link>
            <Link
              href="https://discord.com/invite/ZutWMTJnwA"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Discord />
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-10 md:gap-20">
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Products</li>
            <li>
              <Link
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'https://www.omi.me/pages/openglass'}
                target="_blank"
              >
                OpenGlass
              </Link>
            </li>
            <li>
              <Link
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'https://www.omi.me/'}
                target="_blank"
              >
                Friend
              </Link>
            </li>
            <li>
              <Link
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'https://www.omi.me/pages/friend-dev'}
                target="_blank"
              >
                Friend DEV KIT
              </Link>
            </li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Other</li>
            <li>
              <Link
                href="https://airtable.com/appyGfrqMxoUaD1mg/shrswR2uD1LRoFkFX"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Residency
              </Link>
            </li>
            <li>
              <Link
                href="https://affiliate.basedhardware.com/"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Affiliate
              </Link>
            </li>
            <li>
              <Link
                href="https://www.omi.me/pages/privacy"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Privacy
              </Link>
            </li>
            <li>
              <Link
                href="https://coda.io/@kodjima33/customizations"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Customizations
              </Link>
            </li>
            <li>
              <Link
                href="https://discord.com/invite/8MP3b9ymvx"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Discord
              </Link>
            </li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Company</li>
            <li>
              <Link
                href={'https://www.omi.me/pages/about'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                About
              </Link>
            </li>
            <li>
              <Link
                href={'https://airtable.com/appyGfrqMxoUaD1mg/shrkALjXdq7mJMM1W'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Invest
              </Link>
            </li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
