import { motion, useReducedMotion } from "motion/react";

interface Props {
  /** 0..1 fill ratio. If undefined, the ring spins indeterminately. */
  progress?: number;
  size?: number;
  label?: string;
  sublabel?: string;
}

/** Pulsing/spinning progress ring used during file-scan-style steps. Mirrors
 * Swift's OnboardingLoadingAnimation. */
export function LoadingRing({ progress, size = 96, label, sublabel }: Props) {
  const reduceMotion = useReducedMotion();
  const stroke = 5;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const ratio = progress != null ? Math.max(0, Math.min(1, progress)) : null;
  const dash = ratio != null ? c * ratio : c * 0.28;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        {/* Outer halo */}
        <motion.div
          className="absolute inset-0 rounded-full"
          style={{
            background:
              "radial-gradient(closest-side, rgba(96,165,250,0.35), transparent 70%)",
            filter: "blur(8px)",
          }}
          animate={
            reduceMotion ? { opacity: 0.6 } : { opacity: [0.45, 0.85, 0.45] }
          }
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        />

        <svg width={size} height={size} className="relative">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={stroke}
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="white"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${c}`}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            animate={
              ratio != null || reduceMotion
                ? {}
                : { rotate: [0, 360] }
            }
            transition={
              ratio != null || reduceMotion
                ? {}
                : { duration: 1.6, repeat: Infinity, ease: "linear" }
            }
            style={{
              transformOrigin: `${size / 2}px ${size / 2}px`,
            }}
          />
        </svg>
      </div>

      {label ? (
        <div className="text-center">
          <div className="text-[14px] font-semibold text-white">{label}</div>
          {sublabel ? (
            <div className="text-[12px] text-white/55 mt-0.5 font-mono tabular-nums">
              {sublabel}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
