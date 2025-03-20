'use client';
import Image from 'next/image';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import ShareButton from '../memories/share-button';
import { useParams, usePathname } from 'next/navigation';

interface NavItem {
  href: string;
  label: string;
  target?: string;
  className?: string;
  icon?: React.ReactNode;
}

interface AppHeaderProps {
  navItems?: NavItem[];
  showShareButton?: boolean;
  mobileMenuId?: string;
  customLogo?: {
    src: string;
    alt: string;
  };
  className?: string;
}

const DiscordIcon = () => (
  <svg className="h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
    <path
      fill="currentColor"
      d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"
    />
  </svg>
);

const GithubIcon = () => (
  <svg className="h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">
    <path
      fill="currentColor"
      d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
    />
  </svg>
);

const ZapIcon = () => (
  <svg
    className="h-4 w-4"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="M13 3L4 14H12L11 21L20 10H12L13 3Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const CartIcon = () => (
  <div className="relative">
    <svg
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M5.41442 6H3.75V4.5H6.58558L7.33558 7.5H18.935L17.2321 15.1627L16.5 15.75H8.25L7.51786 15.1627L6.02 8.42233L5.41442 6ZM7.68496 9L8.85163 14.25H15.8984L17.065 9H7.68496ZM10.5 18C10.5 18.8284 9.82843 19.5 9 19.5C8.17157 19.5 7.5 18.8284 7.5 18C7.5 17.1716 8.17157 16.5 9 16.5C9.82843 16.5 10.5 17.1716 10.5 18ZM15 19.5C15.8284 19.5 16.5 18.8284 16.5 18C16.5 17.1716 15.8284 16.5 15 16.5C14.1716 16.5 13.5 17.1716 13.5 18C13.5 18.8284 14.1716 19.5 15 19.5Z"
        fill="currentColor"
      />
    </svg>
    <div className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-red-500"></div>
  </div>
);

export default function AppHeader({
  navItems = [
    {
      href: 'https://rebrand.ly/discord-invite-a2a451',
      label: '6.7k+ Join Discord',
      icon: <DiscordIcon />,
      className: 'flex items-center space-x-2 text-white hover:text-gray-300',
    },
    {
      href: 'https://github.com/BasedHardware/Omi',
      label: '4.4K Github',
      icon: <GithubIcon />,
      className: 'flex items-center space-x-2 text-white hover:text-gray-300',
    },
    {
      href: 'https://docs.omi.me',
      label: 'Docs',
      className: 'text-white hover:text-gray-300',
    },
    {
      href: 'https://www.omi.me/help',
      label: 'Help center',
      className: 'text-white hover:text-gray-300',
    },
    {
      href: 'https://docs.omi.me/docs/developer/apps/Introduction',
      label: 'Start Building',
      icon: <ZapIcon />,
      className: 'flex items-center space-x-2 rounded-full bg-[#6C2BD9] px-3 py-1 text-white transition-colors hover:bg-[#5A1CB8]',
      target: '_blank',
    },
    {
      href: 'https://www.omi.me/products/omi-dev-kit-2',
      label: 'Order Now',
      className: 'text-white hover:text-gray-300',
    },
    {
      href: 'https://omi.me/cart',
      label: 'Cart',
      icon: <CartIcon />,
      className: 'flex items-center space-x-2 text-white hover:text-gray-300',
    },
  ],
  showShareButton = false,
  mobileMenuId = 'mobile-menu',
  customLogo = {
    src: '/omi-white.webp',
    alt: 'Based Hardware Logo',
  },
  className = '',
}: AppHeaderProps) {
  const [scrollPosition, setScrollPosition] = useState(0);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
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
        className={`fixed top-0 z-50 flex w-full items-center justify-between bg-[#0B0F17] p-4 px-4 text-white transition-all duration-500 md:px-12 ${
          scrollPosition > 100 ? 'backdrop-blur-md md:!bg-black/40' : ''
        } ${className}`}
      >
        <h1 className="flex items-center gap-2 text-xl">
          <Link href="/" className="text-2xl font-bold text-white">
            <Image
              src={customLogo.src}
              alt={customLogo.alt}
              width={146}
              height={64}
              className="h-auto w-[50px]"
            />
          </Link>
        </h1>

        <nav className="flex items-center">
          {/* Mobile Menu Toggle */}
          <button
            className="rounded-md p-2 text-white hover:bg-white/10 md:hidden"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            aria-label="Toggle mobile menu"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
              />
            </svg>
          </button>

          {/* Desktop Navigation */}
          <ul className="hidden items-center gap-3 text-sm md:flex md:gap-4 md:text-base">
            {showShareButton && params.id && (
              <li>
                <ShareButton />
              </li>
            )}
            {navItems.map((item, index) => {
              // Special styling for Start Building button
              if (item.label === 'Start Building') {
                return (
                  <li key={index} className="ml-1">
                    <Link href={item.href} target={item.target} className={item.className}>
                      {item.icon && <span className="flex-shrink-0">{item.icon}</span>}
                      <span>{item.label}</span>
                    </Link>
                  </li>
                );
              }
              
              return (
                <li key={index}>
                  <Link href={item.href} target={item.target} className={item.className}>
                    {item.icon && <span className="flex-shrink-0">{item.icon}</span>}
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>
      <div className="h-px w-full bg-white/5"></div>

      {/* Mobile Menu Panel - Moved outside header */}
      <div
        className={`
          fixed inset-0 z-[100] bg-[#0B0F17] transition-transform duration-300
          ${isMobileMenuOpen ? 'translate-x-0' : 'translate-x-full'}
          md:hidden
        `}
      >
        <div className="flex h-20 items-center justify-between border-b border-white/10 px-6">
          <Link href="/" className="text-2xl font-bold text-white">
            <Image
              src={customLogo.src}
              alt={customLogo.alt}
              width={146}
              height={64}
              className="h-auto w-[50px]"
            />
          </Link>
          <button
            className="rounded-md p-2 text-white hover:bg-white/10"
            onClick={() => setIsMobileMenuOpen(false)}
          >
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="1.5"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <div className="px-6 py-4">
          <ul className="flex flex-col gap-4">
            {navItems.map((item, index) => (
              <li key={index}>
                <Link
                  href={item.href}
                  target={item.target}
                  className={item.className}
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  {item.icon && <span className="flex-shrink-0">{item.icon}</span>}
                  <span>{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  ) : null;
}
