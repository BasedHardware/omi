import { OnboardingChat } from "./chatFlow/OnboardingChat";

interface Props {
  onComplete: () => void;
}

/** Thin wrapper around the chat-driven onboarding. The legacy two-column
 *  shell (fixed header, progress bar, fixed footer, split panes) is gone;
 *  the chat itself is the entire onboarding UI. Kept as a named shell so
 *  callers in App.tsx don't need to change imports. */
export function OnboardingShell({ onComplete }: Props) {
  return <OnboardingChat onComplete={onComplete} />;
}
