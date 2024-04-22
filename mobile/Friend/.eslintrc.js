module.exports = {
  parser: '@babel/eslint-parser',
  parserOptions: {
    requireConfigFile: false,
    ecmaFeatures: {
      jsx: true, // Enable JSX
    },
  },
  root: true,
  extends: [
    '@react-native',
    'plugin:react/recommended', // Add this line
  ],
  plugins: [
    'react', // Add this line
  ],
  settings: {
    react: {
      version: 'detect', // React version. "detect" automatically picks the version you have installed.
    },
  },
};
