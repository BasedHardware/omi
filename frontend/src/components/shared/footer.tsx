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
            <Link href="https://www.x.com" target="_blank" rel="noopener noreferrer">
              <X />
            </Link>
            <Link
              href="https://www.linkedin.com"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Linkedin />
            </Link>
            <Link href="https://www.github.com" target="_blank" rel="noopener noreferrer">
              <Github />
            </Link>
            <Link href="https://www.tiktok.com" target="_blank" rel="noopener noreferrer">
              <Tiktok />
            </Link>
            <Link
              href="https://www.instagram.com"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Instagram />
            </Link>
            <Link
              href="https://www.discord.com"
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
                href={'#'}
                target="_blank"
              >
                OpenGlass
              </Link>
            </li>
            <li>
              <Link
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'#'}
                target="_blank"
              >
                Friend
              </Link>
            </li>
            <li>
              <Link
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'#'}
                target="_blank"
              >
                Friend DEV KIT
              </Link>
            </li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Other</li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Residency
              </a>
            </li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Affiliate
              </a>
            </li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Privacy
              </a>
            </li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
              >
                Customizations
              </a>
            </li>
            <li>
              <a
                href="#"
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
              <Link
                className="text-zinc-400 hover:text-white hover:underline md:text-base"
                href={'/public-trips'}
              >
                About
              </Link>
            </li>
            <li>
              <Link
                href={'#'}
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
