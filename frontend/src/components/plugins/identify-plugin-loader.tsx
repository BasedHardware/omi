import { OnePointCircle } from "iconoir-react";

export default function IdentifyPluginLoader(){
  return(
        <div className="flex gap-2 items-center sticky top-[4rem] px-4 md:px-12 bg-[#0f0f0f] backdrop-blur-sm bg-opacity-90 z-[50] py-3 shadow-sm border-b border-solid border-zinc-900">
      <div className='w-9 h-9 bg-zinc-800 rounded-full grid place-items-center'>
        <OnePointCircle className='text-xs animate-spin'/>
      </div>
      <div>
        <h3 className="text-base font-semibold md:text-base h-[13px] animate-pulse rounded-sm w-[150px] bg-gray-600"></h3>
        <p className="text-gray-500 md:text-base text-sm h-[10px] mt-2 bg-gray-800 animate-pulse rounded-sm w-[200px] line-clamp-1"></p>
      </div>
    </div>
  )
}