import TrendItem from './trend-item';
import Animation from './animation';
import getTrends from '@/src/actions/trends/get-trends';

const trendMock = [
  {
    create_at: new Date(),
    category: 'Dreamforce',
    id: '1',
    topics: [
      {
        id: '1',
        topic: 'Salesforce',
        memories_count: 100,
      },
      {
        id: '2',
        topic: 'Trailhead',
        memories_count: 50,
      },
      {
        id: '3',
        topic: 'Dreamforce',
        memories_count: 10,
      },
    ],
  },
  {
    create_at: new Date(),
    category: 'Investment',
    id: '2',
    topics: [
      {
        id: '1',
        topic: 'Investors',
        memories_count: 4,
      },
      {
        id: '2',
        topic: 'Trailhead',
        memories_count: 32,
      },
    ],
  },
];

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
