import { useEffect, useState } from "react";
import { useAuthStore } from "@/stores/authStore";
import { useOnboardingStore } from "@/stores/onboardingStore";

/** Pick the greeting based on local time of day. */
function greetingFor(hour: number): string {
  if (hour < 5) return "Still up";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  if (hour < 22) return "Good evening";
  return "Good night";
}

/** Derive a friendly first name from the onboarding name or email. */
function friendlyName(preferred: string, email: string | null): string {
  const trimmed = preferred.trim();
  if (trimmed) {
    return trimmed.split(/\s+/)[0];
  }
  if (email) {
    const local = email.split("@")[0] ?? "";
    const first = local.split(/[._-]+/).filter(Boolean)[0] ?? local;
    if (first) {
      return first.charAt(0).toUpperCase() + first.slice(1);
    }
  }
  return "there";
}

function todayLabel(date: Date): string {
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

/** Top-of-dashboard greeting. Rolls over every minute so "Good morning" ages
 *  to "Good afternoon" without a refresh. */
export function GreetingHeader() {
  const preferredName = useOnboardingStore((s) => s.preferredName);
  const email = useAuthStore((s) => s.userEmail);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  const greeting = greetingFor(now.getHours());
  const name = friendlyName(preferredName, email);

  return (
    <header className="dashboard-greeting">
      <h1 className="dashboard-greeting-title">
        {greeting}, <span className="dashboard-greeting-name">{name}</span>
      </h1>
      <p className="dashboard-greeting-meta">{todayLabel(now)}</p>
    </header>
  );
}
