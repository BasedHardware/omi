import { motion } from "motion/react";

interface Props {
  /** Keys to display, e.g. ["Cmd", "Shift", "Space"]. Empty array shows a
   * placeholder prompting the user to press a combination. */
  keys: string[];
  /** Pulse the caps to indicate the input is active. */
  active?: boolean;
}

/** Visual key-cap row used by the shortcut-capture steps. Updates in
 * real-time as the user presses keys; modifiers and letters render with
 * the same styling so the row reads as a single chord. */
export function KeyCapDisplay({ keys, active = true }: Props) {
  if (keys.length === 0) {
    return (
      <motion.div
        className="text-[14px] text-white/45 px-4 py-3 rounded-xl border border-dashed border-white/15 bg-white/[0.02]"
        animate={active ? { opacity: [0.5, 1, 0.5] } : { opacity: 0.6 }}
        transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
      >
        Press the combination you want…
      </motion.div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {keys.map((k, i) => (
        <div key={`${k}-${i}`} className="flex items-center gap-2">
          <KeyCap label={k} />
          {i < keys.length - 1 ? (
            <span className="text-white/35 text-[13px]">+</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function KeyCap({ label }: { label: string }) {
  return (
    <motion.div
      initial={{ scale: 0.92, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 22 }}
      className="min-w-[44px] h-[44px] px-3 flex items-center justify-center rounded-lg bg-white/[0.08] border border-white/15 shadow-[0_2px_0_0_rgba(255,255,255,0.08),inset_0_-2px_0_0_rgba(0,0,0,0.35)] text-white text-[14px] font-semibold"
      style={{ fontFamily: "var(--font-display)" }}
    >
      {label}
    </motion.div>
  );
}
