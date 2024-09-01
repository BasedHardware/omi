'use client';
import { Puzzle } from 'iconoir-react';

export default function ErrorIdentifyPlugin() {
  return (
    <div>
      <div className="sticky top-[4rem] z-[50] mb-3 flex items-center gap-2 border-b border-solid border-zinc-900 bg-[#0f0f0f] bg-opacity-90 px-4 py-3 shadow-sm backdrop-blur-sm md:px-12">
        <div className="grid h-9 w-9 min-w-[36px] place-items-center rounded-full bg-zinc-700">
          <Puzzle className="text-xs" />
        </div>
        <div>
          <h3 className="text-base font-semibold md:text-base">Plugin name not found</h3>
        </div>
      </div>
    </div>
  );
}
