import { Trend } from '@/src/types/trends/trends.types';
import capitalizeFirstLetter from '@/src/utils/capitalize-first-letter';
import TrendTopicItem from './trend-topic-item';

export default function TrendItem({ trend }: { trend: Trend }) {
  return (
    <div className="mt-10">
      <h2 className="text-center text-2xl font-light text-white md:text-4xl">
        {capitalizeFirstLetter(trend.category)}
      </h2>
      <div className={`mt-5 grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-5`}>
        {trend.topics.map((topic, index) => (
          <TrendTopicItem key={index} topic={topic} trend={trend} />
        ))}
      </div>
    </div>
  );
}
