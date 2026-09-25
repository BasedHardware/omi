'use client';

import { ExternalData as ExternalDataType } from '@/src/types/memory.types';
import { CheckCircle, PasteClipboard } from 'iconoir-react';
import { useState } from 'react';

interface ExternalDataProps {
  externalData: ExternalDataType;
}

export default function ExternalData({ externalData }: ExternalDataProps) {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = () => {
    const text = externalData?.text ?? '';
    navigator.clipboard
      .writeText(text)
      .then(() => {
        console.log('URL copied to clipboard');
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 3000);
      })
      .catch((err) => {
        console.error('Failed to copy URL: ', err);
      });
  };

  return (
    <div>
      <div className="mt-10 flex items-center justify-between">
        <h2 className="sn-h3">External data</h2>
        <button
          onClick={handleCopy}
          className={`rounded-md border border-solid p-2 transition-colors ${
            isCopied
              ? '!border-gray-500 bg-gray-500'
              : 'border-zinc-800 hover:bg-zinc-900'
          }`}
        >
          {isCopied ? (
            <CheckCircle className={`text-xs`} />
          ) : (
            <PasteClipboard className="text-xs" />
          )}
        </button>
      </div>
      <span className="sn-muted text-sm md:text-base">Source: {externalData.source}</span>
      <div className="relative mt-4 line-clamp-[15] h-auto overflow-hidden rounded-md border border-solid border-gray-800 bg-zinc-900 text-sm text-gray-400">
        <p className="p-3">{externalData.text}</p>
      </div>
      <p className="sn-muted mt-2 text-center text-xs">…</p>
    </div>
  );
}
