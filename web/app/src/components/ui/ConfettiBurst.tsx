'use client';

import { motion } from 'framer-motion';
import { useMemo } from 'react';
import { confettiParticles } from '@/lib/confetti';
import { cn } from '@/lib/utils';

/**
 * A one-shot confetti burst, for the moment something is dismissed for good.
 *
 * Hand-rolled rather than pulled from a package: this needs a couple of dozen
 * divs on one spring, and a canvas library would ship a renderer and a physics
 * loop to draw them. It is also the only way the pieces can inherit the
 * surface's own palette instead of arriving in someone else's brand colours.
 */

interface ConfettiBurstProps {
  /** Stable per burst — pieces are laid out from it, so it must not change mid-flight. */
  seed?: number;
  count?: number;
  className?: string;
}

export function ConfettiBurst({ seed = 0, count = 22, className }: ConfettiBurstProps) {
  const pieces = useMemo(() => confettiParticles(count, seed), [count, seed]);

  return (
    <div
      aria-hidden="true"
      className={cn(
        'pointer-events-none absolute inset-0 overflow-visible',
        // motion-reduce: a burst is decoration by definition, so it is the
        // first thing to go rather than something to slow down.
        'motion-reduce:hidden',
        className,
      )}
    >
      {pieces.map((piece, index) => (
        <motion.span
          key={index}
          initial={{ x: '-50%', y: '-50%', scale: 0, opacity: 1, rotate: 0 }}
          animate={{
            x: `calc(-50% + ${piece.x}px)`,
            y: `calc(-50% + ${piece.y}px)`,
            scale: [0, 1, 0.9, 0],
            opacity: [1, 1, 1, 0],
            rotate: piece.rotate,
          }}
          transition={{
            duration: piece.duration,
            ease: 'easeOut',
            times: [0, 0.2, 0.7, 1],
          }}
          className="absolute left-1/2 top-1/2 block rounded-[1px]"
          style={{
            width: piece.size,
            height: piece.size * piece.aspect,
            backgroundColor: piece.color,
          }}
        />
      ))}
    </div>
  );
}
