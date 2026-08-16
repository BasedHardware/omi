module.exports = {
  preset: 'react-native',
  transformIgnorePatterns: [
    'node_modules/(?!((\\.bun/[^/]+/node_modules/)?(@react-native|react-native|lucide-react-native|react-native-safe-area-context|react-native-svg)(@|/)))',
  ],
};
