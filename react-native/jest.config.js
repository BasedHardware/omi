module.exports = {
  moduleNameMapper: {
    '^lucide-react-native/icons/(.*)$': '<rootDir>/test/lucideIcon.js',
  },
  preset: 'react-native',
  transformIgnorePatterns: [
    'node_modules/(?!((\\.bun/[^/]+/node_modules/)?(@react-native|react-native|lucide-react-native|react-native-safe-area-context|react-native-svg)(@|/)))',
  ],
};
