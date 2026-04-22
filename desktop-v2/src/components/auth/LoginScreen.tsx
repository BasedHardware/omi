import { motion, useReducedMotion } from "motion/react";
import { Apple, ArrowRight } from "lucide-react";
import { Button } from "../ui/button";
import { useAuthStore } from "../../stores/authStore";
import { OrbIndicator } from "../feedback/OrbIndicator";

const GoogleLogo = () => (
  <svg viewBox="0 0 48 48" className="size-[18px]">
    <path
      fill="#FFC107"
      d="M43.6 20.5H42V20H24v8h11.3c-1.7 4.8-6.3 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.3-.4-3.5z"
    />
    <path
      fill="#FF3D00"
      d="M6.3 14.7l6.6 4.8C14.6 16 18.9 13 24 13c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.6 8.3 6.3 14.7z"
    />
    <path
      fill="#4CAF50"
      d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-1.8 1.3-4.2 2.4-7.2 2.4-5 0-9.5-3.2-11.2-7.8l-6.5 5C9.5 39.6 16.2 44 24 44z"
    />
    <path
      fill="#1976D2"
      d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.3-4.2 5.6l6.2 5.2c-.4.4 6.7-4.9 6.7-14.8 0-1.3-.1-2.3-.4-3.5z"
    />
  </svg>
);

export function LoginScreen() {
  const { signIn, isSigningIn, error } = useAuthStore();
  const reduceMotion = useReducedMotion();

  const line1 = "Personal intelligence that turns";
  const italic = "thought to action";

  const entry = reduceMotion
    ? { opacity: 1, y: 0, filter: "blur(0px)" }
    : { opacity: 1, y: 0, filter: "blur(0px)" };
  const entryInit = reduceMotion
    ? { opacity: 0 }
    : { opacity: 0, y: 14, filter: "blur(10px)" };

  // Intentionally dark regardless of app theme — the hero image, drop
  // shadows, and gradient-clipped text are designed against a dark
  // backdrop. A light-mode login would be a separate design exercise.
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-[#08080a] text-white">
      {/* Hero background — matches web landing */}
      <div className="absolute inset-0 z-0">
        <img
          src="/hero-bg.png"
          alt=""
          className="absolute inset-0 w-full h-full object-cover object-center opacity-90"
        />
        {/* Dark overlay for legibility */}
        <div className="absolute inset-0 bg-black/40" />
        {/* Bottom fade into app background */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#08080a]" />
        {/* Soft brand glow center */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-blue-500/[0.04] blur-[150px]" />
      </div>

      <main className="relative z-10 flex flex-col items-center justify-center h-full px-6">
        {/* Persona hero */}
        <motion.div
          initial={entryInit}
          animate={entry}
          transition={{ duration: 1.1, delay: 0.05, ease: [0.2, 0.7, 0.2, 1] }}
          className="mb-10"
        >
          <OrbIndicator state="idle" variant="halo" size="xl" />
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={entryInit}
          animate={entry}
          transition={{ duration: 1.1, delay: 0.2, ease: [0.2, 0.7, 0.2, 1] }}
          className="text-[clamp(2rem,4.2vw,3.8rem)] text-center leading-[1.05] tracking-tight mb-6 max-w-3xl drop-shadow-[0_2px_30px_rgba(0,0,0,0.8)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          <span className="font-semibold text-white/95">{line1}</span>{" "}
          <span
            className="italic"
            style={{
              fontFamily: "var(--font-serif)",
              fontWeight: 500,
              background:
                "linear-gradient(135deg, #ffffff 0%, #c7d2fe 50%, #93c5fd 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            {italic}
          </span>
          <span className="text-white/95">.</span>
        </motion.h1>

        <motion.p
          initial={entryInit}
          animate={entry}
          transition={{ duration: 1.0, delay: 0.35, ease: [0.2, 0.7, 0.2, 1] }}
          className="text-center text-white/85 text-base sm:text-lg max-w-xl mb-10 leading-relaxed drop-shadow-[0_1px_15px_rgba(0,0,0,0.7)]"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Nooto captures your meetings and conversations, then turns them into
          summaries, tasks, and memories — across every device you own.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={entryInit}
          animate={entry}
          transition={{ duration: 0.9, delay: 0.5, ease: [0.2, 0.7, 0.2, 1] }}
          className="flex flex-col items-center gap-3 w-full max-w-[280px]"
        >
          <Button
            size="lg"
            onClick={() => signIn("google")}
            disabled={isSigningIn}
            className="w-full gap-3 bg-white text-black hover:bg-white/90 rounded-full h-12 text-[14px] font-medium shadow-lg shadow-black/30"
          >
            <GoogleLogo />
            {isSigningIn ? "Waiting for browser…" : "Continue with Google"}
          </Button>
          <Button
            size="lg"
            variant="outline"
            onClick={() => signIn("apple")}
            disabled={isSigningIn}
            className="w-full gap-3 rounded-full h-12 text-[14px] font-medium border-white/15 bg-white/5 backdrop-blur-md hover:bg-white/10 hover:border-white/25 text-white shadow-lg shadow-black/30"
          >
            <Apple className="size-[18px]" />
            {isSigningIn ? "Waiting for browser…" : "Continue with Apple"}
          </Button>

          {isSigningIn ? (
            <div className="text-[12px] text-white/50 text-center mt-3 flex items-center gap-2">
              <ArrowRight className="size-3 animate-pulse" />
              Complete sign-in in your browser, then return here.
            </div>
          ) : null}
          {error ? (
            <div className="text-[12px] text-red-400/90 text-center mt-2">
              {error}
            </div>
          ) : null}
        </motion.div>

        {/* Subtle footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.9 }}
          className="absolute bottom-8 text-[11px] text-white/35 tracking-wide"
          style={{ fontFamily: "var(--font-display)" }}
        >
          by continuing you agree to our Terms & Privacy Policy
        </motion.div>
      </main>
    </div>
  );
}
