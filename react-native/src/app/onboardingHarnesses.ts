export type HarnessKind = 'agent' | 'context';

export type OnboardingHarness = {
  id: string;
  kind: HarnessKind;
  name: string;
  detail: string;
  mark: string;
};

export const ONBOARDING_HARNESSES: readonly OnboardingHarness[] = [
  {
    id: 'openclaw',
    kind: 'agent',
    name: 'OpenClaw',
    detail: 'runs tasks on your Mac',
    mark: 'OC',
  },
  {
    id: 'hermes',
    kind: 'agent',
    name: 'Hermes',
    detail: 'autonomous background agent',
    mark: 'H',
  },
  {
    id: 'claudeCode',
    kind: 'agent',
    name: 'Claude Code',
    detail: 'codes in your repos',
    mark: 'CC',
  },
  {
    id: 'codex',
    kind: 'agent',
    name: 'Codex',
    detail: "OpenAI's coding agent",
    mark: 'Cx',
  },
  {
    id: 'calendar',
    kind: 'context',
    name: 'Calendar',
    detail: 'Import events and recurring routines.',
    mark: 'Cal',
  },
  {
    id: 'email',
    kind: 'context',
    name: 'Email',
    detail: 'Import email history and follow-ups.',
    mark: 'Gm',
  },
  {
    id: 'local-files',
    kind: 'context',
    name: 'Local files',
    detail: 'Index documents, code, and working folders.',
    mark: 'Fi',
  },
  {
    id: 'apple-notes',
    kind: 'context',
    name: 'Apple Notes',
    detail: 'Import notes and private written context.',
    mark: 'Nt',
  },
  {
    id: 'x',
    kind: 'context',
    name: 'X (Twitter)',
    detail: 'Learn from your posts and bookmarks.',
    mark: 'X',
  },
  {
    id: 'chatgpt',
    kind: 'context',
    name: 'ChatGPT',
    detail: 'Paste a memory export into Omi.',
    mark: 'GPT',
  },
];
