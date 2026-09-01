import {
  desktopGlassCornerRadius,
  desktopMotion,
  desktopNavItems,
  desktopSearchPlaceholder,
  desktopSettingsPanes,
  desktopStageFade,
  desktopSystemFontFamily,
  desktopTrafficLightRowWidth,
  isShippingDesktopNav,
  visibleChatError,
} from './desktopChrome';
import {
  glassMotionDuration,
  listInsertMotionDuration,
  motionDuration,
  navMotionDuration,
  overlayMotionDuration,
  searchExpandMotionDuration,
  stepMotionDuration,
} from './desktopMotion';
import {
  CLOUD_BACKEND_ORIGIN,
  parseSoftwarePlane,
  resolveNativeRequestOrigin,
} from '../v5BackendOrigin';

const workerOrigin = 'https://omi-v5-backend-staging.example.workers.dev';

test('desktop chrome uses the shipping Home Library IA', () => {
  expect(desktopNavItems).toEqual([
    'Home',
    'Library',
    'Tasks',
    'Rewind',
    'Apps',
  ]);
  expect(isShippingDesktopNav('Home')).toBe(true);
  expect(isShippingDesktopNav('Chat')).toBe(false);
  expect(isShippingDesktopNav('Memories')).toBe(false);
  expect(desktopSearchPlaceholder).toBe("Search what you've seen and heard…");
  expect(desktopSystemFontFamily).toBe('System');
  expect(desktopGlassCornerRadius).toBe(22);
  expect(desktopTrafficLightRowWidth).toBeGreaterThan(70);
  expect(desktopMotion.navMs).toBe(80);
  expect(desktopMotion.pressMs).toBe(90);
  expect(desktopMotion.stepMs).toBe(240);
  expect(desktopMotion.settleMs).toBe(280);
  expect(desktopMotion.overlayMs).toBe(300);
  expect(desktopMotion.checkboxMs).toBe(180);
  expect(desktopMotion.searchExpandMs).toBe(160);
  expect(desktopMotion.listInsertMs).toBe(0);
  expect(desktopMotion.glassMs).toBe(0);
  expect(desktopStageFade.hubOffsetY).toBe(14);
  expect(desktopStageFade.chatRiseY).toBe(54);
  expect(desktopStageFade.dropScale).toBe(0.98);
  expect(motionDuration(desktopMotion.pressMs, true)).toBe(0);
  expect(motionDuration(desktopMotion.pressMs, false)).toBe(90);
  expect(navMotionDuration(true)).toBe(0);
  expect(stepMotionDuration(true)).toBe(0);
  expect(searchExpandMotionDuration(true)).toBe(0);
  expect(overlayMotionDuration(true)).toBe(0);
  expect(listInsertMotionDuration(false)).toBe(0);
  expect(glassMotionDuration(false)).toBe(0);
  expect(navMotionDuration(false)).toBe(80);
  expect(stepMotionDuration(false)).toBe(240);
  expect(searchExpandMotionDuration(false)).toBe(160);
});

test('settings IA includes shipping panes plus Advanced backend', () => {
  expect(desktopSettingsPanes).toEqual([
    'General',
    'Account & Plan',
    'Transcription',
    'Rewind',
    'Floating Bar',
    'Alerts & Privacy',
    'Permissions',
    'Shortcuts',
    'AI & Automation',
    'About',
  ]);
});

test('signed-out and probing first paint hide chat transport errors', () => {
  expect(
    visibleChatError('signed-out', 'Chat is temporarily unavailable.'),
  ).toBeNull();
  expect(
    visibleChatError('probing', 'Chat is temporarily unavailable.'),
  ).toBeNull();
  expect(visibleChatError('ready', 'Chat is temporarily unavailable.')).toBe(
    'Chat is temporarily unavailable.',
  );
  expect(visibleChatError('ready', null)).toBeNull();
});

test('software plane defaults to production until Advanced is flipped', () => {
  expect(parseSoftwarePlane(undefined)).toBe('old');
  expect(parseSoftwarePlane('old')).toBe('old');
  expect(parseSoftwarePlane('new')).toBe('new');
  expect(parseSoftwarePlane('unexpected')).toBe('old');
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/chat-messages',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/conversations',
      softwarePlane: 'new',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: workerOrigin});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/chat-messages',
      softwarePlane: 'new',
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
});
