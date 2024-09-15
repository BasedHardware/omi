import { Topic, Trend } from '@/src/types/trends/trends.types';
import capitalizeFirstLetter from '@/src/utils/capitalize-first-letter';

interface TrendTopicItemProps {
  topic: Topic;
  trend: Trend;
}

export default function TrendTopicItem({ topic, trend }: TrendTopicItemProps) {
  return (
    <div
      className={`items-center rounded-md border border-solid border-zinc-600 bg-white/5 p-3 text-white backdrop-blur-[4px] md:p-4 ${
        trend.topics.length > 1 ? '' : 'col-span-3'
      }`}
    >
      <p className="bg-gradient-to-b from-[#6d49a6] to-[#ffffff] bg-clip-text text-base text-transparent md:text-lg">
        {capitalizeFirstLetter(topic.topic)}
      </p>
      <div>
        <p className="text-sm text-zinc-400 md:text-base">
          {topic.memories_count} memories
        </p>
      </div>
    </div>
  );
}
