import { CheckCircle, ShareIos } from 'iconoir-react';
import { useState } from 'react';

export default function ShareButton() {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = () => {
    const url = window.location.href;
    navigator.clipboard
      .writeText(url)
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
    <button
      onClick={handleCopy}
      className={`flex items-center gap-2 rounded-md border border-solid border-zinc-600 p-1.5 transition-all duration-300 ${
        isCopied
          ? '!border-green-500 bg-green-500 p-1.5 px-3.5'
          : 'p-1.5 hover:bg-zinc-800'
      } md:p-1.5 md:px-3.5`}
    >
      {isCopied ? (
        <CheckCircle className={`text-xs`} />
      ) : (
        <ShareIos className="text-xs" />
      )}
      <span className={`${isCopied ? '' : 'hidden md:inline'}`}>
        {isCopied ? 'Link Copied!' : 'Share'}
      </span>
    </button>
  );
}
