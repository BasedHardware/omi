import { NavArrowRight } from 'iconoir-react';
import Link from 'next/link';

export default function Tendencies() {
  return (
    <div className="group sticky top-24 mb-5 hidden w-[50rem] max-w-[352px] rounded-md border border-solid border-neutral-900 bg-gradient-to-r from-[#030710] to-[#0000006c] text-white shadow-md shadow-[#06060742] transition-colors hover:border-neutral-800 md:block">
      <Link href={'/dreamforce'} className="flex items-center justify-between p-3 md:p-5">
        <h2 className=" text-base hover:underline md:text-xl">What's trending now!</h2>
        <div className="grid h-8 w-8 place-items-center rounded-full transition-colors group-hover:bg-zinc-900">
          <NavArrowRight className="text-sm text-neutral-400 group-hover:text-neutral-300" />
        </div>
      </Link>
      {/* <Suspense fallback={null}>
        <GetTrends />
      </Suspense> */}
      {/* <div className="py-3 md:py-5">
        <div className="flex w-full flex-col divide-slate-800">
          <TrendingItem title="Work" count={23} raking={1} />
          <TrendingItem title="Business" count={6} raking={2} />
          <TrendingItem title="Inspiration" count={6} raking={3} />
          <TrendingItem title="Social" count={6} />
        </div>
      </div> */}
    </div>
  );
}
