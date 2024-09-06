import TrendingItem from './tendencies/trending-item';

export default function Tendencies() {
  return (
    <div className="top-24 mb-5 hidden sticky md:block w-[50rem] max-w-[352px] rounded-md border border-solid border-neutral-800 bg-gradient-to-r from-[#030710] to-[#401c1c8c] text-white shadow-md shadow-[#06060742] transition-colors hover:border-neutral-700">
      <h2 className="p-3 text-base hover:no-underline md:p-5 md:text-xl">
        What's trending now!
      </h2>
      <div className="p-3 md:p-5">
        <div className="flex w-full flex-col gap-2">
          <TrendingItem title="work" count={23} />
          <TrendingItem title="Business" count={6} />
          <TrendingItem title="Inspiration" count={6} />
          <TrendingItem title="Social" count={6} />
        </div>
      </div>
    </div>
  );
}
