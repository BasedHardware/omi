import Image from 'next/image';

/** Phone-only bar pinned to the bottom of a shared note (CSS hides it above 640px). */
export default function ShareInstallBar({ installHref }: { installHref: string }) {
  return (
    <aside className="sn-installbar" aria-label="Get the Omi app">
      <span className="sn-installbar-icon" aria-hidden="true">
        <Image src="/omi-white.webp" alt="" width={26} height={12} />
      </span>
      <span className="sn-installbar-text">
        <span className="sn-installbar-title">Notes for every conversation</span>
        <span className="sn-installbar-sub">Free on iPhone and Android</span>
      </span>
      <a href={installHref} className="sn-pill">
        Get Omi
      </a>
    </aside>
  );
}
