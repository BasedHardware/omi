import { ShareIos } from 'iconoir-react';

export default function ShareButton() {
  const handleCopy = () => {
    const url = window.location.href;
    navigator.clipboard
      .writeText(url)
      .then(() => {
        console.log('URL copied to clipboard');
      })
      .catch((err) => {
        console.error('Failed to copy URL: ', err);
      });
  };

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-2 rounded-md border border-solid border-zinc-600 p-1.5 transition-colors hover:bg-zinc-800 md:p-1.5 md:px-3.5"
    >
      <ShareIos className="text-xs" />
      <span className="hidden md:inline">Share</span>
    </button>
  );
}
