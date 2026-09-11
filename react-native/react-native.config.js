const {resolve} = require('node:path');

module.exports = {
  reactNativePath: resolve(__dirname, '../node_modules/react-native'),
  dependencies: {
    'react-native-safe-area-context': {
      root: resolve(
        __dirname,
        '../node_modules/react-native-safe-area-context',
      ),
    },
    'react-native-svg': {
      root: resolve(__dirname, '../node_modules/react-native-svg'),
    },
    'react-native-webrtc': {
      root: resolve(__dirname, '../node_modules/react-native-webrtc'),
      platforms: {
        // GPT Live uses react-native-webrtc on phone only; keep macOS honest.
        macos: null,
      },
    },
  },
};
