const { getDefaultConfig, mergeConfig } = require('@react-native/metro-config');

const config = {
    resolver: {
        sourceExts: ['js', 'json', 'ts', 'tsx'],
        entryFile: 'apps/mobile/client/src/index.js',
    },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
