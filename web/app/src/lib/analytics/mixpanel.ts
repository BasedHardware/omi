import mixpanel from 'mixpanel-browser';

const MIXPANEL_TOKEN = process.env.NEXT_PUBLIC_MIXPANEL_TOKEN;

let isInitialized = false;

export const MixpanelManager = {
  init() {
    if (isInitialized || !MIXPANEL_TOKEN) {
      return;
    }

    mixpanel.init(MIXPANEL_TOKEN, {
      track_pageview: false,
      persistence: 'localStorage',
    });

    isInitialized = true;
  },

  identify(userId: string, properties?: { name?: string; email?: string }) {
    if (!isInitialized) return;

    mixpanel.identify(userId);

    if (properties) {
      const userProps: Record<string, string> = {
        Platform: 'web',
      };
      if (properties.name) userProps['$name'] = properties.name;
      if (properties.email) userProps['$email'] = properties.email;

      mixpanel.people.set(userProps);
    }
  },

  track(event: string, properties?: Record<string, unknown>) {
    if (!isInitialized) return;

    mixpanel.track(event, properties);
  },

  pageView(pageName: string) {
    this.track(`${pageName} Page Viewed`);
  },

  reset() {
    if (!isInitialized) return;

    mixpanel.reset();
  },

  setUserProperty(key: string, value: unknown) {
    if (!isInitialized) return;

    mixpanel.people.set({ [key]: value });
  },
};
