/**
 * Jest config.
 *
 * This file did not exist: `jest` had been running on defaults, which happens to
 * work for the pure-logic tests because they never import React Native or a
 * stylesheet. Mounting a component needs three things the defaults do not
 * provide:
 *
 *   - jest-expo's preset, for the RN/Expo transform pipeline;
 *   - a CSS stub, because constants/theme.ts imports '@/global.css' at module
 *     scope. Nothing consumes it at runtime, so a proxy object is enough;
 *   - the '@/...' alias, matching the module-resolver alias in babel.config.js,
 *     so tests and app code resolve imports identically.
 */
module.exports = {
  preset: 'jest-expo',
  moduleNameMapper: {
    '\\.css$': 'identity-obj-proxy',
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
};
