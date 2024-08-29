import { Discord, Github, Instagram, Linkedin, Tiktok, X } from "iconoir-react";
import Link from "next/link";

export default function Footer(){
  return (
    <footer className="footer text-white px-4 md:px-12 w-full bg-black/5 border-t border-solid border-zinc-800 py-12">
      <div className="mx-auto flex flex-wrap gap-12 justify-between max-w-screen-xl">
        <div>
          <h2 className="font-semibold text-4xl">Omi</h2>
          <p className="text-gray-500">San Fransisco</p>
          <Link href={'mailto:team@basedhardware.com>'} className="hover:underline">
            team@basedhardware.com
          </Link>

          <div className="flex gap-3 items-center mt-3">
            <Link href="https://www.x.com" target="_blank" rel="noopener noreferrer">
              <X />
            </Link>
            <Link href="https://www.linkedin.com" target="_blank" rel="noopener noreferrer">
              <Linkedin />
            </Link>
            <Link href="https://www.github.com" target="_blank" rel="noopener noreferrer">
              <Github />
            </Link>
            <Link href="https://www.tiktok.com" target="_blank" rel="noopener noreferrer">
              <Tiktok />
            </Link>
            <Link href="https://www.instagram.com" target="_blank" rel="noopener noreferrer">
              <Instagram />
            </Link>
            <Link href="https://www.discord.com" target="_blank" rel="noopener noreferrer">
              <Discord />
            </Link>
          </div>
        </div>

        <div className="grid gap-10 md:gap-20 grid-cols-3">
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Products</li>
            <li>
              <Link className="hover:underline md:text-base text-zinc-400 hover:text-white" href={'#'} target="_blank">
                OpenGlass
              </Link>
            </li>
            <li>
              <Link className="hover:underline md:text-base text-zinc-400 hover:text-white" href={'#'} target="_blank">
                Friend
              </Link>
            </li>
            <li>
              <Link className="hover:underline md:text-base text-zinc-400 hover:text-white" href={'#'} target="_blank">
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
                className="hover:underline md:text-base text-zinc-400 hover:text-white"
              >
                Residency
              </a>
            </li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="hover:underline md:text-base text-zinc-400 hover:text-white"
              >
                Affiliate
              </a>
            </li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="hover:underline md:text-base text-zinc-400 hover:text-white"
              >
                Privacy
              </a>
            </li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="hover:underline md:text-base text-zinc-400 hover:text-white"
              >
                Customizations
              </a>
            </li>
            <li>
              <a
                href="#"
                target={'_blank'}
                rel={'noreferrer'}
                className="hover:underline md:text-base text-zinc-400 hover:text-white"
              >
                Discord
              </a>
            </li>
          </ul>
          <ul className="flex flex-col gap-3">
            <li className="font-bold">Company</li>
            <li>
              <Link className="hover:underline md:text-base text-zinc-400 hover:text-white" href={'/public-trips'}>
                About
              </Link>
            </li>
            <li>
              <Link href={'#'} className="hover:underline md:text-base text-zinc-400 hover:text-white">
                Invest
              </Link>
            </li>
          </ul>
        </div>
      </div>
    </footer>
  )
}