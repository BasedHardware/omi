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
      ...eslintPluginReactRefresh.configs.vite.rules,
      'react-refresh/only-export-components': 'off'
    }
  },
  {
    files: [
      'src/renderer/src/components/settings/tabs/IntegrationsTab.tsx',
      'src/renderer/src/components/settings/tabs/RewindTab.tsx',
      'src/renderer/src/hooks/useRewind.ts',
      'src/renderer/src/pages/Apps.tsx',
      'src/renderer/src/pages/ConversationDetail.tsx',
      'src/renderer/src/pages/Conversations.tsx',
      'src/renderer/src/pages/Home.tsx',
      'src/renderer/src/components/rewind/RewindPlayer.tsx'
    ],
    rules: {
      'react-hooks/set-state-in-effect': 'off'
    }
  },
  {
    files: [
      'src/renderer/src/components/overlay/OverlayApp.tsx',
      'src/renderer/src/hooks/usePushToTalk.ts',
      'src/renderer/src/lib/useGraphSimulation.ts',
      'src/renderer/src/App.tsx',
      'src/renderer/src/components/chat/ChatMessages.tsx',
      'src/renderer/src/components/graph/BrainGraph.tsx'
    ],
    rules: {
      'react-hooks/refs': 'off'
    }
  },
  {
    files: [
      'src/renderer/src/components/rewind/RewindPlayer.tsx',
      'src/renderer/src/hooks/useRewind.ts'
    ],
    rules: {
      'react-hooks/purity': 'off'
    }
  },
  {
    files: ['src/renderer/src/components/graph/BrainGraph.tsx'],
    rules: {
      'react/no-unknown-property': 'off',
      'react-hooks/immutability': 'off'
    }
  },
  {
    files: ['scripts/**/*.mjs', '**/*.test.ts'],
    rules: {
      '@typescript-eslint/explicit-function-return-type': 'off',
      'no-empty': 'off'
    }
  },
  eslintConfigPrettier
)
