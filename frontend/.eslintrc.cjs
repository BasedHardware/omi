module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'module',
    ecmaFeatures: {
      jsx: true,
    },
  },
  settings: {
    react: {
      version: 'detect',
    },
    'import/resolver': {
      node: {
        paths: ['src'],
        extensions: ['.js', '.jsx', '.ts', '.tsx'],
      },
    },
  },
  env: {
    browser: true,
    amd: true,
    node: true,
  },
  extends: [
    'next',
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:jsx-a11y/recommended',
    'plugin:prettier/recommended', // Make sure this is always the last element in the array.
  ],
  plugins: ['simple-import-sort', 'prettier'],
  rules: {
    'prettier/prettier': ['error', {}, { usePrettierrc: true }],
    'react/react-in-jsx-scope': 'off',
    'jsx-a11y/accessible-emoji': 'off',
    'react/prop-types': 'off',
    '@typescript-eslint/explicit-function-return-type': 'off',
    '@typescript-eslint/ban-ts-comment': 'off',
    'simple-import-sort/imports': 'off',
    'simple-import-sort/exports': 'off',
    'jsx-a11y/anchor-is-valid': [
      'error',
      {
        components: ['Link'],
        specialLink: ['hrefLeft', 'hrefRight'],
        aspects: ['invalidHref', 'preferButton'],
      },
    ],
  },
};
