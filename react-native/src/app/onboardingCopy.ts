export const SESSION_UNREACHABLE_COPY =
  "Couldn't reach Omi to check your session. Try Sign in again when you are online.";

export const PRIVACY_URL = 'https://www.omi.me/pages/privacy';
export const TERMS_URL = 'https://www.omi.me/pages/terms-of-service';

export const PRIMARY_LANGUAGES = [
  {code: 'en', name: 'English'},
  {code: 'en-US', name: 'English (US)'},
  {code: 'es', name: 'Spanish'},
  {code: 'zh', name: 'Chinese (Mandarin, Simplified)'},
  {code: 'hi', name: 'Hindi'},
  {code: 'pt', name: 'Portuguese'},
  {code: 'ja', name: 'Japanese'},
  {code: 'de', name: 'German'},
  {code: 'fr', name: 'French'},
  {code: 'ko', name: 'Korean'},
  {code: 'ar', name: 'Arabic'},
  {code: 'it', name: 'Italian'},
  {code: 'vi', name: 'Vietnamese'},
] as const;

export const ACQUISITION_SOURCES = [
  'TikTok',
  'YouTube',
  'Instagram',
  'X (Twitter)',
  'Reddit',
  'LinkedIn',
  'Friend',
  'Coworker',
  'Event',
  'App Store',
  'Google Search',
  'Other',
] as const;

export const DESKTOP_VALUE_CLAIMS = [
  'I watch your screen — the frames, and the text in your windows.',
  'I listen — your microphone, and the audio of your calls.',
  'It lands in your Omi account, and you read it back from Home.',
] as const;
