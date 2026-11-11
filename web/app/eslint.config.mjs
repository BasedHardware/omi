import coreWebVitals from 'eslint-config-next/core-web-vitals';

export default [
  {
    ignores: [
      '.next/**',
      'node_modules/**',
      'public/**',
      'src/lib/omiApi.generated.ts',
      '**/*.backup',
    ],
  },
  ...coreWebVitals,
];
