export function readDurationToken(name: string, fallbackMs: number): number {
  if (typeof document === 'undefined') return fallbackMs;
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name);
  const parsed = parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : fallbackMs;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function replayErrorShake(input: HTMLElement): () => void {
  if (prefersReducedMotion()) return () => {};
  input.classList.remove('is-shaking');
  void input.offsetWidth;
  input.classList.add('is-shaking');
  const shakeMs =
    readDurationToken('--shake-dur-a', 80) * 2 + readDurationToken('--shake-dur-b', 60) * 2;
  const timer = window.setTimeout(() => input.classList.remove('is-shaking'), shakeMs + 20);
  return () => {
    window.clearTimeout(timer);
    input.classList.remove('is-shaking');
  };
}
