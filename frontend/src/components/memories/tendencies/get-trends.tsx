import getTrends from '@/src/actions/trends/getTrends';

export default async function GetTrends() {
  const trends = await getTrends();

  return (
    <div className="flex w-full flex-col divide-slate-800">
      {/* {trends.map((trend) => (
        <TrendingItem trend={trend} />
      ))} */}
    </div>
  );
}
