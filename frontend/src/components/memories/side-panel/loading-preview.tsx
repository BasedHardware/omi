export default function LoadingPreview() {
  return (
    <div className="">
      <div className="px-4 py-6 md:px-12">
        <div className="line-clamp-2 h-[32px] w-[15rem] animate-pulse rounded-lg bg-zinc-700 font-bold md:h-[36px] md:w-[30rem]"></div>
        <p className="my-2 h-[18px] w-[30%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base"></p>
        <div className="h-[24px] w-[100px] rounded-full bg-gray-700 px-3 py-1.5 text-xs md:text-sm"></div>
      </div>
      <div className="mt-8 flex h-[52px] border-y border-solid border-zinc-800 text-base md:mt-10 md:text-lg"></div>
      <div className="mt-10 px-4 md:px-12">
        <div className="h-[28px] w-[10rem] animate-pulse rounded-lg bg-zinc-700 font-bold md:h-[30px]"></div>
        <div className="h-[10px]" />
        <div>
          <div className="my-2 h-[10px] w-[30%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[100%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[100%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[90%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[70%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
        </div>
        <div className="mt-9">
          <div className="my-2 h-[10px] w-[100%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[100%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[100%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[90%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
          <div className="my-2 h-[10px] w-[70%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
        </div>
      </div>
      <div className="mt-10 px-4 md:px-12">
        <div className="h-[28px] w-[10rem] animate-pulse rounded-lg bg-zinc-700 font-bold md:h-[30px]"></div>
        <div className="h-[10px]" />
        <div className="mt-3 flex flex-col gap-4">
          {[...Array(3)].map((_, index) => (
            <div className="flex w-full items-center gap-3" key={index}>
              <div className="min-h-[20px] min-w-[20px] rounded-full bg-gray-500" />
              <div className="w-full">
                <div className="my-2 h-[10px] w-[100%] animate-pulse rounded-lg bg-gray-500 text-sm text-gray-500 md:text-base" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
