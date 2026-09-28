import {PRIMARY_LANGUAGES} from './onboardingCopy';

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

// Script aliases from the desktop app's normalizer: locales whose language
// root is not itself a supported code (zh has no bare entry).
const DEVICE_LANGUAGE_ALIASES: Record<string, string> = {
  zh: 'zh-CN',
  'zh-hans': 'zh-CN',
  'zh-hant': 'zh-TW',
};

/**
 * Maps an OS locale identifier ("en_US", "pt-BR", "zh-Hans-CN", "de") onto a
 * supported language code. Like the main app's picker, the full locale wins
 * when it exists ("pt-BR" → "pt-BR"), then the language root ("zh-Hans-CN" →
 * "zh-CN"). Unknown input yields 'en' so onboarding always starts from a
 * valid selection.
 */
export function normalizeDeviceLanguage(
  raw: unknown,
  supported: readonly {code: string}[] = PRIMARY_LANGUAGES,
): string {
  if (typeof raw !== 'string' || raw.trim().length === 0) {
    return 'en';
  }
  const normalized = raw.trim().replace(/_/g, '-').toLowerCase();
  const aliased = DEVICE_LANGUAGE_ALIASES[normalized];
  if (aliased != null && supported.some(item => item.code === aliased)) {
    return aliased;
  }
  const parts = normalized.split('-');
  const language = parts[0];
  if (!/^[a-z]{2,3}$/.test(language)) {
    return 'en';
  }
  const region = parts.length > 1 ? parts[parts.length - 1].toUpperCase() : '';
  if (region.length === 2 || region.length === 3) {
    const regional = `${language}-${region}`;
    if (supported.some(item => item.code === regional)) {
      return regional;
    }
  }
  return supported.some(item => item.code === language) ? language : 'en';
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
