import {
  desktopGlassCornerRadius,
  desktopMotion,
  desktopNavBarHeight,
  desktopOmnibarHeight,
  desktopNavItems,
  desktopSearchPlaceholder,
  desktopSettingsPanes,
  desktopStageFade,
  desktopSystemFontFamily,
  desktopTrafficLightButton,
  desktopTrafficLightClusterWidth,
  desktopTrafficLightRowWidth,
  desktopTrafficLightSpacing,
  desktopTrafficLightTrailing,
  desktopWindowInset,
  isShippingDesktopNav,
  navFrameMoved,
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

test('desktop chrome uses the shipping Home Conversations IA', () => {
  expect(desktopNavItems).toEqual(['Home', 'Conversations', 'Tasks', 'Apps']);
  expect(isShippingDesktopNav('Home')).toBe(true);
  expect(isShippingDesktopNav('Conversations')).toBe(true);
  expect(isShippingDesktopNav('Chat')).toBe(false);
  expect(isShippingDesktopNav('Library')).toBe(false);
  expect(isShippingDesktopNav('Memories')).toBe(false);
  expect(desktopSearchPlaceholder).toBe("Search what you've seen and heard…");
  expect(desktopSystemFontFamily).toBe('System');
  expect(desktopGlassCornerRadius).toBe(22);
  expect(desktopNavBarHeight).toBe(52);
});

test('window chrome geometry is one even inset with an inline light cluster', () => {
  expect(desktopWindowInset).toBe(12);
  expect(desktopTrafficLightButton).toBe(14);
  expect(desktopTrafficLightSpacing).toBe(8);
  expect(desktopTrafficLightTrailing).toBe(16);
  expect(desktopTrafficLightClusterWidth).toBe(
    3 * desktopTrafficLightButton + 2 * desktopTrafficLightSpacing,
  );
  expect(desktopTrafficLightClusterWidth).toBe(58);
  expect(desktopTrafficLightRowWidth).toBe(
    desktopTrafficLightClusterWidth + desktopTrafficLightTrailing,
  );
  expect(desktopTrafficLightRowWidth).toBe(74);
});

test('shipping motion constants follow the transitions.dev token scale', () => {
  expect(desktopMotion.staggerMs).toBe(40);
  expect(desktopMotion.microMs).toBe(80);
  expect(desktopMotion.quickMs).toBe(150);
  expect(desktopMotion.fastMs).toBe(250);
  expect(desktopMotion.mediumMs).toBe(350);
  expect(desktopMotion.slowMs).toBe(400);
  expect(desktopMotion.verySlowMs).toBe(500);
  expect(desktopMotion.navMs).toBe(desktopMotion.fastMs);
  expect(desktopMotion.pressMs).toBe(desktopMotion.microMs);
  expect(desktopMotion.stepMs).toBe(desktopMotion.fastMs);
  expect(desktopMotion.settleMs).toBe(desktopMotion.mediumMs);
  expect(desktopMotion.overlayMs).toBe(desktopMotion.slowMs);
  expect(desktopMotion.checkboxMs).toBe(desktopMotion.quickMs);
  expect(desktopMotion.searchExpandMs).toBe(desktopMotion.quickMs);
  expect(desktopMotion.listInsertMs).toBe(0);
  expect(desktopMotion.glassMs).toBe(0);
  expect(desktopStageFade.hubOffsetY).toBe(14);
  expect(desktopStageFade.chatRiseY).toBe(54);
  expect(desktopStageFade.dropScale).toBe(0.98);
  expect(motionDuration(desktopMotion.pressMs, true)).toBe(0);
  expect(motionDuration(desktopMotion.pressMs, false)).toBe(80);
  expect(navMotionDuration(true)).toBe(0);
  expect(stepMotionDuration(true)).toBe(0);
  expect(searchExpandMotionDuration(true)).toBe(0);
  expect(overlayMotionDuration(true)).toBe(0);
  expect(listInsertMotionDuration(false)).toBe(0);
  expect(glassMotionDuration(false)).toBe(0);
  expect(navMotionDuration(false)).toBe(250);
  expect(stepMotionDuration(false)).toBe(250);
  expect(searchExpandMotionDuration(false)).toBe(150);
});

test('settings IA keeps wired panes and drops no-op duplicates', () => {
  expect(desktopSettingsPanes).toEqual([
    'General',
    'Account & Plan',
    'Transcription',
    'Rewind',
    'Alerts & Privacy',
    'AI & Automation',
    'About',
  ]);
  expect(desktopSettingsPanes).not.toContain('Floating Bar');
  expect(desktopSettingsPanes).not.toContain('Permissions');
  expect(desktopSettingsPanes).not.toContain('Shortcuts');
});

test('omnibar sits on its own row under the nav', () => {
  expect(desktopOmnibarHeight).toBe(40);
  expect(desktopNavBarHeight).toBe(52);
});

test('nav pill frames ignore sub-point jitter', () => {
  expect(navFrameMoved(undefined, {x: 10, width: 80})).toBe(true);
  expect(navFrameMoved({x: 10, width: 80}, {x: 10, width: 80})).toBe(false);
  expect(navFrameMoved({x: 10, width: 80}, {x: 10.4, width: 80.2})).toBe(false);
  expect(navFrameMoved({x: 10, width: 80}, {x: 10.6, width: 80})).toBe(true);
  expect(navFrameMoved({x: 10, width: 80}, {x: 10, width: 80.6})).toBe(true);
});

test('chat transport errors surface only for ready sessions', () => {
  expect(
    visibleChatError('signed-out', 'Chat is temporarily unavailable.'),
  ).toBeNull();
  expect(
    visibleChatError('probing', 'Chat is temporarily unavailable.'),
  ).toBeNull();
  expect(visibleChatError('ready', null)).toBeNull();
  expect(visibleChatError('ready', '')).toBeNull();
  expect(visibleChatError('ready', 'Chat is temporarily unavailable.')).toBe(
    'Chat is temporarily unavailable.',
  );
});

test('a valid stamped origin defaults fresh installs to the new plane', () => {
  expect(parseSoftwarePlane(undefined)).toBe('old');
  expect(parseSoftwarePlane('old')).toBe('old');
  expect(parseSoftwarePlane('new')).toBe('new');
  expect(parseSoftwarePlane('unexpected')).toBe('old');
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/chat-messages',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: workerOrigin});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: workerOrigin});
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
