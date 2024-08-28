export default function LoadingMemory() {
  return (
    <div className="mx-3 my-10 max-w-screen-md rounded-2xl border border-solid border-zinc-800 py-6 text-white md:mx-auto md:my-28 md:py-12">
      <div className="px-4 md:px-12">
        <div className="line-clamp-2 w-[15rem] md:w-[30rem] h-[32px] md:h-[36px] rounded-lg font-bold bg-zinc-700 animate-pulse">
        </div>
        <p className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[18px] bg-gray-500 w-[30%] rounded-lg">
        </p>
        <div className="rounded-full bg-gray-700 px-3 py-1.5 text-xs md:text-sm h-[24px] w-[100px]">
        </div>
      </div>
      <div className="mt-8 flex border-y border-solid border-zinc-800 text-base md:mt-10 md:text-lg h-[52px]"></div>
      <div className="px-4 md:px-12 mt-10">
        <div className="w-[10rem] h-[28px] md:h-[30px] rounded-lg font-bold bg-zinc-700 animate-pulse">
        </div>
        <div className="h-[10px]"/>
        <div>
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[30%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[100%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[100%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[90%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[70%] rounded-lg" />
        </div>
        <div className="mt-9">
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[100%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[100%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[100%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[90%] rounded-lg" />
          <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[70%] rounded-lg" />
        </div>
      </div>
      <div className="px-4 md:px-12 mt-10">
        <div className="w-[10rem] h-[28px] md:h-[30px] rounded-lg font-bold bg-zinc-700 animate-pulse">
        </div>  
        <div className="h-[10px]"/>
        <div className="flex flex-col gap-4 mt-3">
          {[...Array(3)].map((_, i) => (

          <div className="flex gap-3 items-center w-full">
            <div className="min-h-[20px] min-w-[20px] rounded-full bg-gray-500"/>
            <div className="w-full">
              <div className="my-2 text-sm text-gray-500 md:text-base animate-pulse h-[10px] bg-gray-500 w-[100%] rounded-lg" />
            </div>
          </div>
          ))}
        </div>
      </div>
    </div>
  );
}
