import Image from 'next/image';
import CopyLinkButton from './copy-link-button';
import ShareThemeToggle from './share-theme-toggle';

interface ShareTopbarProps {
  installHref: string;
  showCopyLink?: boolean;
}

/** The share page's own header; the marketplace header is hidden on share routes. */
export default function ShareTopbar({
  installHref,
  showCopyLink = true,
}: ShareTopbarProps) {
  return (
    <header className="sn-topbar">
      <a href="https://omi.me" className="sn-logo" aria-label="Omi home">
        <Image
          className="sn-only-light"
          src="/omi-black.webp"
          alt=""
          width={50}
          height={22}
          priority
        />
        <Image
          className="sn-only-dark"
          src="/omi-white.webp"
          alt=""
          width={50}
          height={22}
          priority
        />
      </a>
      <div className="sn-topbar-actions">
        {showCopyLink ? <CopyLinkButton /> : null}
        <ShareThemeToggle />
        <a href={installHref} className="sn-pill">
          Get Omi
        </a>
      </div>
    </header>
  );
}
