'use client';

import { useState } from 'react';

/** Copies the page URL; the check mark confirms it for two seconds. */
export default function CopyLinkButton() {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      document.dispatchEvent(new Event('omi:share-link-copied'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard denied: nothing to confirm.
    }
  };

  return (
    <button
      type="button"
      className="sn-icon-btn"
      onClick={copy}
      aria-label={copied ? 'Link copied' : 'Copy link'}
      title={copied ? 'Link copied' : 'Copy link'}
    >
      {copied ? (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M5 12l5 5 9-10" />
        </svg>
      ) : (
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" />
          <path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" />
        </svg>
      )}
      <span className="sn-copied" role="status">
        {copied ? 'Link copied' : ''}
      </span>
    </button>
  );
}
