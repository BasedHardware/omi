export const GoogleSignin = {
  configure() {},
  signIn: async () => {
    throw new Error('Google sign-in unavailable on web');
  },
  signInSilently: async () => ({ data: null }),
  getTokens: async () => ({ idToken: null }),
  hasPreviousSignIn: () => false,
  getCurrentUser: () => null,
};
export default GoogleSignin;
