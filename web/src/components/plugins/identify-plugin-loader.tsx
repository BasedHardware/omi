import { OnePointCircle } from 'iconoir-react';

export default function IdentifyPluginLoader() {
  return (
    <div className="sticky top-[4rem] z-[50] flex h-[69px] items-center gap-2 border-b border-solid border-zinc-900 bg-[#0f0f0f] bg-opacity-90 px-4 py-3 shadow-sm backdrop-blur-sm md:h-[73px] md:px-12">
      <div className="grid h-[36px] w-[36px] place-items-center rounded-full bg-zinc-800">
        <OnePointCircle className="animate-spin text-xs" />
      </div>
      <div>
        <h3 className="h-[13px] w-[150px] animate-pulse rounded-sm bg-gray-600 text-base font-semibold md:text-base"></h3>
        <p className="mt-2 line-clamp-1 h-[10px] w-[200px] animate-pulse rounded-sm bg-gray-800 text-sm text-gray-500 md:text-base"></p>
      </div>
    </div>
  );
}
