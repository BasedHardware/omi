import mixpanel from 'mixpanel-browser';

// Initialize mixpanel with project token
mixpanel.init(process.env.NEXT_PUBLIC_MIXPANEL_TOKEN!, {
  debug: true,
  track_pageview: true,
  persistence: 'localStorage',
  api_host: 'https://api.mixpanel.com',
  ignore_dnt: true,
  loaded: (mixpanel) => {
    console.log('Mixpanel loaded successfully');
  }
});

// Generate a unique anonymous ID if one doesn't exist
const getOrCreateAnonymousId = () => {
  let anonymousId = localStorage.getItem('mp_anonymous_id');
  if (!anonymousId) {
    anonymousId = 'anon-' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('mp_anonymous_id', anonymousId);
  }
  return anonymousId;
};

// Helper functions
export const Mixpanel = {
  identify: (id?: string) => {
    const anonymousId = id || getOrCreateAnonymousId();
    mixpanel.identify(anonymousId);
    console.log('Identified user:', anonymousId);
  },
  
  track: (name: string, props?: any) => {
    try {
      const anonymousId = getOrCreateAnonymousId();
      const eventProps = {
        distinct_id: anonymousId,
        ...props
      };
      console.log('Tracking event:', name, eventProps);
      mixpanel.track(name, eventProps);
    } catch (e) {
      console.error('Mixpanel error:', e);
    }
  }
};