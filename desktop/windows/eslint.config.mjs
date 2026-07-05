import { defineConfig } from 'eslint/config'
import tseslint from '@electron-toolkit/eslint-config-ts'
import eslintConfigPrettier from '@electron-toolkit/eslint-config-prettier'
import eslintPluginReact from 'eslint-plugin-react'
import eslintPluginReactHooks from 'eslint-plugin-react-hooks'
import eslintPluginReactRefresh from 'eslint-plugin-react-refresh'

export default defineConfig(
  { ignores: ['**/node_modules', '**/dist', '**/out'] },
  tseslint.configs.recommended,
  eslintPluginReact.configs.flat.recommended,
  eslintPluginReact.configs.flat['jsx-runtime'],
  {
    settings: {
      react: {
        version: 'detect'
      }
    }
  },
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': eslintPluginReactHooks,
      'react-refresh': eslintPluginReactRefresh
    },
    rules: {
      ...eslintPluginReactHooks.configs.recommended.rules,
      ...eslintPluginReactRefresh.configs.vite.rules
    }
  },
  {
    // react-three-fiber intrinsics (<mesh>, <group>, position, args, intensity…)
    // are not DOM elements/attributes, so the DOM-oriented react/no-unknown-property
    // rule mis-flags them. Scope it off for the r3f render trees.
    files: ['**/components/graph/**/*.tsx'],
    rules: {
      'react/no-unknown-property': 'off'
    }
  },
  {
    // Diagnostic scripts and test files don't benefit from explicit return-type
    // annotations; the strictness is noise there.
    files: ['scripts/**/*.{ts,js,mjs,cjs}', '**/*.test.{ts,tsx,mjs}'],
    rules: {
      '@typescript-eslint/explicit-function-return-type': 'off'
    }
  },
  eslintConfigPrettier
)
