import { Topic, Trend } from '@/src/types/trends/trends.types';
import capitalizeFirstLetter from '@/src/utils/capitalize-first-letter';
import { motion } from 'framer-motion';

interface TrendTopicItemProps {
  topic: Topic;
  trend: Trend;
  variants: any;
  index: number;
}

export default function TrendTopicItem({ topic, trend, variants, index }: TrendTopicItemProps) {
  const numberOfTopics = trend.topics.length;
  return (
    <motion.div
      variants={variants}
      className={`items-center relative rounded-md border border-solid border-zinc-300 bg-white p-3 text-white backdrop-blur-[4px] md:p-4 ${
        numberOfTopics === 1  ? 'col-span-3' : ''
      }`}
    >
        {index <= 2 && (
          <span className={`text-black text-xs shadow-md rounded-md px-1.5 pt-0.5 absolute -top-1.5 -right-1.5 font-bold ${
            index === 0
              ? 'bg-yellow-400 text-black/60 shadow-yellow-600'
              : index === 1
              ? 'bg-gray-400 text-black/60'
              : 'bg-gray-500 text-white'
          }`}>
            {index + 1}
            <sup className="text-[10px]">st</sup>
          </span>
        )}
      <p className="bg-gradient-to-b from-[#000da1] line-clamp-1 to-[#849fd9] bg-clip-text text-base text-transparent md:text-lg">
        {capitalizeFirstLetter(topic.topic)}
      </p>
      <div>
        <p className="text-sm text-zinc-700 md:text-base">
          {topic.memories_count} {topic.memories_count > 1 ? 'memories' : 'memory'}
        </p>
      </div>
    </motion.div>
  );
}
