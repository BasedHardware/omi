const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

// Find the project and workspace directories
const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, '../');

const config = getDefaultConfig(projectRoot);

// 1. Watch all files within the monorepo
config.watchFolders = [workspaceRoot];

// 2. Let Metro know where to resolve packages and allow it to access packages in the monorepo
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
  path.resolve(workspaceRoot, 'node_modules'),
];

// 3. Force Metro to resolve (sub)dependencies only from the `nodeModulesPaths`
config.resolver.disableHierarchicalLookup = true;

// 4. Extra modules to include in the bundle
config.resolver.extraNodeModules = {
  'omi-react-native': path.resolve(workspaceRoot),
  'base-64': path.resolve(projectRoot, 'node_modules/base-64'),
};

module.exports = config;
