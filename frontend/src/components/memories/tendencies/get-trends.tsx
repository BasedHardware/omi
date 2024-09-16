import getTrends from '@/src/actions/trends/get-trends';
import TrendingItem from './trending-item';
import Link from 'next/link';

export default async function GetTrends() {
  const trends = await getTrends();
  return (
    <div className="flex w-full flex-col divide-slate-800">
      {trends.slice(0, 3).map((trend, idx) => (
        <TrendingItem trend={trend} index={idx} />
      ))}
      <Link href={'/dreamforce'} className='px-5 py-4 hover:underline'>
        Show more
      </Link>
    </div>
  );
}
