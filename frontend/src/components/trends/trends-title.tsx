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
          className="text-center text-4xl font-semibold text-white md:text-7xl"
        >
          What's trending
        </motion.h1>
        <div className="relative mx-auto mt-10 max-w-screen-lg text-center text-sm text-white md:mt-16 md:text-base">
          <motion.p variants={itemVariants}>
            Lorem ipsum dolor sit amet consectetur adipisicing elit. Consequatur aliquid
            ullam, illum reprehenderit adipisci quae molestiae ea a aspernatur modi
            suscipit cupiditate ratione excepturi? Harum dolores voluptatem deserunt sequi
            veritatis.
          </motion.p>
          <div className="absolute top-3 aspect-video h-32 w-full bg-[#dbaafe38] blur-[120px]"></div>
        </div>
        {children}
      </motion.div>
    </Fragment>
  );
}
