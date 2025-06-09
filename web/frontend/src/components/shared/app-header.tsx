'use client';
import Image from 'next/image';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import ShareButton from '../memories/share-button';
import { useParams, usePathname, useRouter } from 'next/navigation';
import { useAuth } from '../../hooks/useAuth';

interface NavItem {
  href: string;
  label: string;
  target?: string;
  className?: string;
  icon?: React.ReactNode;
  onClick?: (e: React.MouseEvent) => Promise<void> | void;
  id?: string;
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

const LoadingSpinner = () => (
  <svg className="h-5 w-5 animate-spin text-white" viewBox="0 0 24 24">
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
      fill="none"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
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
  navItems: initialNavItems = [],
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
  const [isProcessingAuth, setIsProcessingAuth] = useState(false);
  const params = useParams();
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, signIn, signOut, isAuthenticated } = useAuth();

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

  const handleCreateAppAuth = async () => {
    if (loading || isProcessingAuth) {
      console.log('🔄 Auth state loading or processing, please wait...');
      return;
    }

    if (isAuthenticated) {
      console.log('✅ User is authenticated, redirecting to create app page');
      setIsProcessingAuth(true);
      router.push('/create-app');
      setTimeout(() => setIsProcessingAuth(false), 2000); 
    } else {
      console.log('🔑 User not authenticated, initiating Google sign-in...');
      setIsProcessingAuth(true);
      try {
        const signedInUser = await signIn();
        if (signedInUser) {
          console.log('🎉 Sign-in successful, redirecting to create app page');
          router.push('/create-app');
        } else {
          console.log('❌ Sign-in cancelled or failed');
        }
      } catch (error: any) {
        console.error('❌ Authentication failed:', error);
        if (error?.code === 'auth/popup-closed-by-user') {
          console.log('🚪 User cancelled sign-in');
        } else if (error?.code === 'auth/popup-blocked') {
          console.error('🚫 Popup blocked - please allow popups for this site');
        } else {
          console.error('⚠️ Unexpected error during sign-in:', error.message);
        }
      } finally {
        setIsProcessingAuth(false);
      }
    }
  };

  const defaultNavItems: NavItem[] = [
    {
      id: 'create-app-button',
      href: '#', 
      label: isAuthenticated ? 'Create App' : 'Sign in to Create App',
      onClick: handleCreateAppAuth,
      className: `px-4 py-2 rounded-[0.5rem] font-semibold text-sm transition-all duration-200 flex items-center justify-center ${
        isProcessingAuth 
          ? 'bg-gray-700 text-gray-400 cursor-not-allowed' 
          : 'bg-gradient-to-r from-blue-600 to-purple-600 text-white hover:from-blue-700 hover:to-purple-700 shadow-md hover:shadow-lg transform hover:-translate-y-px'
      }`,
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
  ];

  const navItems = [...defaultNavItems, ...initialNavItems.filter(item => !defaultNavItems.find(di => di.label === item.label))];

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

        <nav className="hidden items-center space-x-4 md:flex">
          {navItems.map((item) => (
            <button
              key={item.label}
              onClick={(e) => {
                if (item.onClick) {
                  item.onClick(e);
                } else if (item.href && item.href !== '#') {
                  if (item.target === '_blank') {
                    window.open(item.href, '_blank');
                  } else {
                    router.push(item.href);
                  }
                }
              }}
              disabled={item.id === 'create-app-button' && isProcessingAuth}
              className={item.className || 'text-white hover:text-gray-300'}
            >
              {item.id === 'create-app-button' && isProcessingAuth ? (
                <LoadingSpinner /> 
              ) : (
                <>
                  {item.icon && <span className="mr-1">{item.icon}</span>} 
                  {item.label}
                </>
              )}
            </button>
          ))}
        </nav>

        <div className="md:hidden">
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="text-white focus:outline-none"
            aria-controls={mobileMenuId}
            aria-expanded={isMobileMenuOpen}
          >
            {isMobileMenuOpen ? (
              <svg
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            ) : (
              <svg
                className="h-6 w-6"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
            )}
          </button>
        </div>
      </header>

      <div
        id={mobileMenuId}
        className={`fixed inset-x-0 top-16 z-40 transform bg-[#0A0E17] p-4 transition-transform duration-300 ease-in-out md:hidden ${
          isMobileMenuOpen ? 'translate-y-0' : '-translate-y-full'
        }`}
      >
        <nav className="space-y-3">
          {navItems.map((item) => (
            <button
              key={`mobile-${item.label}`}
              onClick={(e) => {
                if (item.onClick) {
                  item.onClick(e);
                } else if (item.href && item.href !== '#') {
                  if (item.target === '_blank') {
                    window.open(item.href, '_blank');
                  } else {
                    router.push(item.href);
                  }
                }
                setIsMobileMenuOpen(false);
              }}
              disabled={item.id === 'create-app-button' && isProcessingAuth}
              className={`flex w-full items-center justify-center space-x-2 rounded-md px-3 py-2.5 text-base font-medium ${item.className} ${
                item.id === 'create-app-button' ? '' : 'hover:bg-gray-700'
              }`}
            >
               {item.id === 'create-app-button' && isProcessingAuth ? (
                <LoadingSpinner />
              ) : (
                <>
                  {item.icon && <span className="mr-1">{item.icon}</span>} 
                  {item.label}
                </>
              )}
            </button>
          ))}
        </nav>
        {showShareButton && (
          <div className="mt-4 border-t border-gray-700 pt-4">
            <ShareButton />
          </div>
        )}
      </div>
    </>
  ) : null;
}