export default {
  signInAsync: async () => {
    throw new Error('Apple auth unavailable on web');
  },
  isAvailableAsync: async () => false,
  SignInError: class SignInError extends Error {},
};
export const AppleButton = null;
