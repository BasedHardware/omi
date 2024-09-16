'use client';
import { motion } from 'framer-motion';

export default function Animation({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      className="mx-auto mt-32 flex max-w-screen-sm flex-col gap-10"
      initial="hidden"
      animate="visible"
    >
      {children}
    </motion.div>
  );
}
