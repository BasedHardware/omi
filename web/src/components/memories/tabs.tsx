'use client';

interface TabsProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
}

export default function Tabs({ currentTab, setCurrentTab }: TabsProps) {
  return (
    <div className="mt-8 flex border-y border-solid border-zinc-800 text-base md:mt-10 md:text-lg">
      <button
        onClick={() => setCurrentTab('trs')}
        className={`${
          currentTab === 'trs' ? 'bg-zinc-800' : 'hover:bg-zinc-900'
        } w-full py-3 text-center transition-colors`}
      >
        Transcript
      </button>
      <button
        onClick={() => setCurrentTab('sum')}
        className={`${
          currentTab === 'sum' ? 'bg-zinc-800' : 'hover:bg-zinc-900'
        } w-full py-3 text-center transition-colors`}
      >
        Summary
      </button>
    </div>
  );
}
