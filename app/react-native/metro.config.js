const { getDefaultConfig } = require('expo/metro-config');
const { withNativeWind } = require('nativewind/metro');
const path = require('path');
const { resolve: defaultResolve } = require('metro-resolver');

const config = getDefaultConfig(__dirname);

config.resolver.extraNodeModules = {
  '@': path.resolve(__dirname, 'src'),
};
config.watchFolders = [path.resolve(__dirname, 'src')];

// Native-only modules have no web build. When bundling for web, redirect them
// to no-op shims so the app can run in a browser for local testing.
//
// NOTE: we key off the `platform` argument Metro passes to `resolveRequest`
// (which is `'web'` for web bundles), NOT `process.env.PLATFORM`. Expo sets the
// resolver platform during a web build but does not guarantee the env var, so
// relying on the env var let web builds try to resolve the native modules and
// crash at runtime.
const WEB_SHIMS = {
  '@invertase/react-native-apple-authentication': path.resolve(__dirname, 'src/shims/web-apple-auth.js'),
  '@react-native-google-signin/google-signin': path.resolve(__dirname, 'src/shims/web-google-signin.js'),
  '@react-native-firebase/app': path.resolve(__dirname, 'src/shims/web-firebase.js'),
  '@react-native-firebase/auth': path.resolve(__dirname, 'src/shims/web-firebase.js'),
};

const originalResolveRequest = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === 'web' && WEB_SHIMS[moduleName]) {
    return { filePath: WEB_SHIMS[moduleName], type: 'sourceFile' };
  }
  if (originalResolveRequest) {
    return originalResolveRequest(context, moduleName, platform);
  }
  return defaultResolve(context, moduleName, platform);
};

module.exports = withNativeWind(config, { input: './global.css' });
