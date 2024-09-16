import TrendItem from './trend-item';
import Animation from './animation';
import getTrends from '@/src/actions/trends/get-trends';

export default async function GetTrendsMainPage() {
  const trends = await getTrends();
  return (
    <Animation>
      {trends.map((trend, index) => (
        <TrendItem key={index} trend={trend} />
      ))}
    </Animation>
  );
}
