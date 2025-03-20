'use client';

import { Trend } from '@/src/types/trends/trends.types';
import capitalizeFirstLetter from '@/src/utils/capitalize-first-letter';
import TrendTopicItem from './trend-topic-item';
import { motion } from 'framer-motion';

const container = {
  hidden: { opacity: 1, scale: 0 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: {
      delayChildren: 0.3,
      staggerChildren: 0.2,
    },
  },
};

const item = {
  hidden: { y: 20, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
  },
};

const visible = { opacity: 1, y: 0, transition: { duration: 0.8 } };

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible,
};

export default function TrendItem({ trend }: { trend: Trend }) {
  return (
    <motion.div className="mt-10" variants={itemVariants}>
      <h2 className="text-center text-2xl font-semibold text-[#5867e8] md:text-4xl">
        {capitalizeFirstLetter(trend.category)}
      </h2>
      <motion.div
        variants={container}
        initial="hidden"
        animate="visible"
        className={`mt-5 grid grid-cols-1 gap-3 md:gap-5`}
      >
        {trend.topics.map((topic, index) => (
          <TrendTopicItem
            key={index}
            topic={topic}
            trend={trend}
            variants={item}
            index={index}
          />
        ))}
      </motion.div>
    </motion.div>
  );
}
