'use client';

import { ExternalData as ExternalDataType } from "@/src/types/memory.types";
import { CheckCircle, PasteClipboard } from "iconoir-react";
import { useState } from "react";

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
        <div className='flex justify-between items-center mt-10'>
        <h3 className="text-xl font-semibold md:text-2xl">External data</h3>
        <button onClick={handleCopy} className={`p-2 border border-solid transition-colors rounded-md ${isCopied ? "!border-gray-500 bg-gray-500": "border-zinc-800 hover:bg-zinc-900"}`}>
          {isCopied ?(
            <CheckCircle className={`text-xs`} />
          ) : (
            <PasteClipboard className='text-xs'/>

          )

          }
        </button>
        </div>
        <span className="text-sm font-light text-gray-400 md:text-base">
          Source: {externalData.source}
        </span>
        <div className="mt-4 text-gray-400 text-sm bg-zinc-900 rounded-md border border-solid border-gray-800 line-clamp-[15] h-auto relative">
          <p className='p-3'>
          {externalData.text}
          </p>
          <div className='absolute bottom-0 bg-gradient-to-t to-transparent from-[#0f0f0fe6] w-full h-[5rem] flex justify-center items-end'>
          </div>
        </div>
      </div>
  )
}