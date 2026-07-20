const { getDefaultConfig } = require('expo/metro-config');
const { withNativeWind } = require('nativewind/metro');
const path = require('path');
const { resolve: defaultResolve } = require('metro-resolver');

const config = getDefaultConfig(__dirname);

config.resolver.extraNodeModules = {
  '@': path.resolve(__dirname, 'src'),
};
config.watchFolders = [path.resolve(__dirname, 'src')];

// Native-only modules have no web build. When bundling for web (run with
// PLATFORM=web), redirect them to no-op shims so the app can run in a browser
// for local testing. On native builds these aliases are skipped.
const WEB_SHIMS = process.env.PLATFORM === 'web'
  ? {
      '@invertase/react-native-apple-authentication': path.resolve(__dirname, 'src/shims/web-apple-auth.js'),
      '@react-native-google-signin/google-signin': path.resolve(__dirname, 'src/shims/web-google-signin.js'),
      '@react-native-firebase/app': path.resolve(__dirname, 'src/shims/web-firebase.js'),
      '@react-native-firebase/auth': path.resolve(__dirname, 'src/shims/web-firebase.js'),
    }
  : {};

const originalResolveRequest = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (WEB_SHIMS[moduleName]) {
    return { filePath: WEB_SHIMS[moduleName], type: 'sourceFile' };
  }
  if (originalResolveRequest) {
    return originalResolveRequest(context, moduleName, platform);
  }
  return defaultResolve(context, moduleName, platform);
};

module.exports = withNativeWind(config, { input: './global.css' });
