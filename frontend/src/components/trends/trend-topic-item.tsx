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
      className={`items-center relative rounded-md border border-solid border-zinc-600 bg-white/5 p-3 text-white backdrop-blur-[4px] md:p-4 ${
        numberOfTopics === 1  ? 'col-span-3' : ''
      }`}
    >
        {index <= 2 && (
          <span className={`text-black text-xs shadow-md rounded-md px-1.5 pt-0.5 absolute -top-1.5 -right-1.5 font-bold ${
            index === 0
              ? 'bg-yellow-400 text-black/60 shadow-yellow-600'
              : index === 1
              ? 'bg-gray-400 text-black/60'
              : 'bg-gray-500 text-black'
          }`}>
            {index + 1}
            <sup className="text-[10px]">st</sup>
          </span>
        )}
      <p className="bg-gradient-to-b from-[#6d49a6] line-clamp-1 to-[#ffffff] bg-clip-text text-base text-transparent md:text-lg">
        {capitalizeFirstLetter(topic.topic)}
      </p>
      <div>
        <p className="text-sm text-zinc-400 md:text-base">
          {topic.memories_count} {topic.memories_count > 1 ? 'memories' : 'memory'}
        </p>
      </div>
    </motion.div>
  );
}
