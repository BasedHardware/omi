module.exports = function (api) {
  api.cache(true);
  return {
    plugins: [
      ["react-native-worklets-core/plugin"],
    ],
    presets: ['babel-preset-expo'],
  };
};
