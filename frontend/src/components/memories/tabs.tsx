import Link from 'next/link';

export default function Tabs({ currentTab }: { currentTab: string }) {
  return (
    <div className="mt-10 flex border-y border-solid border-zinc-800 text-lg">
      <Link
        href="?tab=sum"
        className={`${currentTab === 'sum' ? 'bg-zinc-800' : 'hover:bg-zinc-900'} w-full py-3 text-center transition-colors`}
      >
        Summary
      </Link>
      <Link
        href="?tab=trs"
        className={`${currentTab === 'trs' ? 'bg-zinc-800' : 'hover:bg-zinc-900'} w-full py-3 text-center transition-colors`}
      >
        Transcript
      </Link>
    </div>
  );
}
