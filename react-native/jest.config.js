module.exports = {
  moduleNameMapper: {
    '^@omi-core/ratified-contracts/(.*)$':
      '<rootDir>/../packages/contracts/ratified/dist/$1.js',
    '^lucide-react-native/icons/(.*)$': '<rootDir>/test/lucideIcon.js',
  },
  preset: 'react-native',
  transformIgnorePatterns: [
    'node_modules/(?!((\\.bun/[^/]+/node_modules/)?(@react-native|react-native|lucide-react-native|react-native-safe-area-context|react-native-svg)(@|/)))',
  ],
};
