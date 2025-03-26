'use client';

import { Fragment } from 'react';
import { motion } from 'framer-motion';

const visible = { opacity: 1, y: 0, transition: { duration: 0.5 } };

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible,
};

interface TrendsTitleProps {
  children: React.ReactNode;
}

export default function TrendsTitle({ children }: TrendsTitleProps) {
  return (
    <Fragment>
      <motion.div
        initial="hidden"
        animate="visible"
        exit={{ opacity: 0, transition: { duration: 1 } }}
      >
        <motion.h1
          variants={{
            hidden: { opacity: 0, y: -20 },
            visible,
          }}
          className="text-center text-4xl font-semibold text-[#393939] md:text-7xl"
        >
          Voices of Now: What the World is Talking About
        </motion.h1>
        <div className="relative mx-auto mt-10 max-w-screen-lg text-center text-sm text-black md:mt-12 md:text-base">
          <motion.p variants={itemVariants}>
            From everyday moments to world-shaping debates, here you'll find the shared
            memories that define today.
          </motion.p>
          <div className="absolute top-3 aspect-video h-32 w-full bg-[#aab8fe38] blur-[120px]"></div>
        </div>
        {children}
      </motion.div>
    </Fragment>
  );
}
