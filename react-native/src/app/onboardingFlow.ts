export const mobileSetupSteps = [
  'consent',
  'name',
  'language',
  'source',
  'permissions',
  'speech',
  'knowledge',
  'complete',
] as const;

export type MobileSetupStep = (typeof mobileSetupSteps)[number];
export type MobileOnboardingStep = 'welcome' | MobileSetupStep;

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

export function mobileSetupIndex(step: MobileOnboardingStep): number {
  if (step === 'welcome') {
    return -1;
  }
  return mobileSetupSteps.indexOf(step);
}

export function nextMobileSetupStep(
  step: MobileSetupStep,
): MobileSetupStep | null {
  const index = mobileSetupSteps.indexOf(step);
  return index >= 0 && index + 1 < mobileSetupSteps.length
    ? mobileSetupSteps[index + 1]
    : null;
}

export function previousMobileSetupStep(
  step: MobileSetupStep,
): MobileSetupStep | null {
  const index = mobileSetupSteps.indexOf(step);
  return index > 0 ? mobileSetupSteps[index - 1] : null;
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
