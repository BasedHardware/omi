export default function MemoryListLoader() {
  return [...Array(15)].map((_, index) => (
    <div
      key={index}
      className="group flex w-full items-start gap-4 border-b border-solid border-gray-700 pb-8 last:border-transparent md:gap-7"
    >
      <div className="h-[40px] min-w-[38px] rounded-md bg-zinc-800 p-2.5 text-sm transition-colors group-hover:bg-zinc-700 md:h-[56px] md:min-w-[52px] md:p-4 md:text-base"></div>
      <div className="w-full">
        <div className="h-[15px] w-[70%] animate-pulse rounded-md bg-zinc-700 md:h-[20px]"></div>
        <div className="mt-3 flex flex-col gap-2">
          <div className="h-[7px] w-full animate-pulse rounded-md bg-zinc-800"></div>
          <div className="h-[7px] w-[80%] animate-pulse rounded-md bg-zinc-800"></div>
        </div>
        <div className="mt-8 flex items-center justify-start gap-1.5 text-xs text-zinc-400 md:text-sm">
          <div className="h-[7px] w-[60px] animate-pulse rounded-md bg-zinc-800 md:w-[100px]"></div>
          <div className="text-xs">•</div>
          <div className="h-[7px] w-[30px] animate-pulse rounded-md bg-zinc-800 md:w-[70px]"></div>
        </div>
      </div>
    </div>
  ));
}
