export const mobileSetupSteps = [
  'consent',
  'language',
  'source',
  'permissions',
  'speech',
  'complete',
] as const;

export type MobileSetupStep = (typeof mobileSetupSteps)[number];
export type MobileOnboardingStep = 'welcome' | MobileSetupStep;

/**
 * Maps an OS locale identifier ("en_US", "pt-BR", "de") onto the short code
 * the language endpoints accept ("en", "pt", "de"). Unknown input yields 'en'
 * so onboarding always starts from a valid selection.
 */
export function normalizeDeviceLanguage(raw: unknown): string {
  if (typeof raw !== 'string' || raw.trim().length === 0) {
    return 'en';
  }
  const code = raw.trim().replace(/_/g, '-').split('-')[0].toLowerCase();
  return /^[a-z]{2,3}$/.test(code) ? code : 'en';
}

// Voice-print enrollment needs getUserMedia + AudioContext, which only exist
// in browsers: native phones cannot run the step, so their itinerary skips it.
export function mobileItinerary(
  nativePhone: boolean,
): readonly MobileSetupStep[] {
  return nativePhone
    ? mobileSetupSteps.filter(step => step !== 'speech')
    : mobileSetupSteps;
}

export const desktopOnboardingSteps = [
  'welcome',
  'value',
  'signIn',
  'permissions',
  'harnesses',
  'data',
  'tutorial',
  'finish',
] as const;

export type DesktopOnboardingStep = (typeof desktopOnboardingSteps)[number];

export function mobileSetupIndex(
  step: MobileOnboardingStep,
  steps: readonly MobileSetupStep[] = mobileSetupSteps,
): number {
  if (step === 'welcome') {
    return -1;
  }
  return steps.indexOf(step);
}

export function nextMobileSetupStep(
  step: MobileSetupStep,
  steps: readonly MobileSetupStep[] = mobileSetupSteps,
): MobileSetupStep | null {
  const index = steps.indexOf(step);
  return index >= 0 && index + 1 < steps.length ? steps[index + 1] : null;
}

export function previousMobileSetupStep(
  step: MobileSetupStep,
  steps: readonly MobileSetupStep[] = mobileSetupSteps,
): MobileSetupStep | null {
  const index = steps.indexOf(step);
  return index > 0 ? steps[index - 1] : null;
}

export function desktopItinerary(signedIn: boolean): DesktopOnboardingStep[] {
  return desktopOnboardingSteps.filter(step =>
    step === 'signIn' ? !signedIn : true,
  );
}

export function nextDesktopStep(
  step: DesktopOnboardingStep,
  signedIn: boolean,
): DesktopOnboardingStep | null {
  const itinerary = desktopItinerary(signedIn);
  const index = itinerary.indexOf(step);
  if (index >= 0) {
    return index + 1 < itinerary.length ? itinerary[index + 1] : null;
  }
  const rank = desktopOnboardingSteps.indexOf(step);
  return (
    itinerary.find(
      candidate => desktopOnboardingSteps.indexOf(candidate) > rank,
    ) ?? null
  );
}

export function previousDesktopStep(
  step: DesktopOnboardingStep,
  signedIn: boolean,
): DesktopOnboardingStep | null {
  switch (step) {
    case 'welcome':
    case 'permissions':
      return null;
    case 'harnesses':
      return 'permissions';
    case 'data':
      return 'harnesses';
    case 'tutorial':
      return 'data';
    case 'finish':
      return 'tutorial';
    case 'value':
      return 'welcome';
    case 'signIn':
      return signedIn ? null : 'value';
  }
}

export function desktopProgressSteps(
  _signedIn: boolean,
): DesktopOnboardingStep[] {
  return desktopOnboardingSteps.filter(step => step !== 'welcome');
}
