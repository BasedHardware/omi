const onAuthStateChanged = (cb) => {
  // Web shim has no persistence: report signed-out immediately.
  try {
    cb(null);
  } catch (e) {
    // ignore
  }
  return () => {};
};

const authInstance = {
  onAuthStateChanged,
  signInWithCredential: async () => ({
    user: { uid: 'web', getIdToken: async () => 'web-token' },
  }),
  signOut: async () => {},
  currentUser: null,
};

function auth() {
  return authInstance;
}

const appInstance = { options: {}, name: 'web-shim' };
function app() {
  return appInstance;
}

const firebase = { app, auth };
export const initializeApp = app;
export const getAuth = auth;
export const getApp = app;
export const FirebaseAuthTypes = {};
export default auth;
