import TrendItem from './trend-item';
import Animation from './animation';
import getTrends from '@/src/actions/trends/get-trends';
import envConfig from '@/src/constants/envConfig';

export default async function GetTrendsMainPage() {
  console.log('URL FROM PAGE:', `${envConfig.API_URL}/v1/trends`);
  const trends = await getTrends();
  return (
    <Animation>
      {trends.map((trend, index) => (
        <TrendItem key={index} trend={trend} />
      ))}
    </Animation>
  );
}
