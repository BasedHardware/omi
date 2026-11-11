// Standalone jest harness for the issue #12979 regression tests.
// The SDK's package.json jest key points at the react-native preset, but the
// preset requires @react-native/babel-preset (not installed) and its setup
// files ship Flow types that babel cannot parse without that preset. This
// scoped config keeps the new tests independent of the preset.

module.exports = {
  testEnvironment: 'node',
  testMatch: ['<rootDir>/src/__tests__/**/*.test.ts'],
  transform: {
    '^.+\\.[jt]sx?$': [
      'babel-jest',
      {
        configFile: false,
        babelrc: false,
        presets: [
          ['@babel/preset-env', { targets: { node: 'current' } }],
          '@babel/preset-typescript',
        ],
      },
    ],
  },
};
