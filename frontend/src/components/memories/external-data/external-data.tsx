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
    <div className="px-4 md:px-12">
      <div className="mt-10 flex items-center justify-between">
        <h3 className="text-xl font-semibold md:text-2xl">External data</h3>
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
      <span className="text-sm font-light text-gray-400 md:text-base">
        Source: {externalData.source}
      </span>
      <div className="relative mt-4 line-clamp-[15] h-auto rounded-md border border-solid border-gray-800 bg-zinc-900 text-sm text-gray-400">
        <p className="p-3">{externalData.text}</p>
        <div className="absolute bottom-0 flex h-[5rem] w-full items-end justify-center bg-gradient-to-t from-[#0f0f0fe6] to-transparent"></div>
      </div>
    </div>
  );
}
