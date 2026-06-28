// Cortex AI provider registry.
//
// Cortex can run its agentic features against a *local* model (private, no key,
// runs on the user's own machine) or a *cloud* provider (BYOK — bring your own
// key). Providers are grouped by region so users can pick where their data is
// processed.
//
// This file is pure data + small helpers so it can be unit-tested and shared by
// both the Electron main process and the renderer. Model lineups were curated
// from each provider's public docs (mid-2026); keep `notes` short and update the
// `models` arrays as providers rotate their offerings.

export type ModelCapability = 'text' | 'vision' | 'tools' | 'reasoning'

/** Where a provider physically runs / is governed. */
export type ProviderRegion =
  | 'local' // runs on the user's machine
  | 'north-america'
  | 'europe'
  | 'china'
  | 'global' // aggregators / multi-region routers

export type ProviderMode = 'local' | 'cloud'

export type ModelInfo = {
  /** API model id sent on the wire. */
  id: string
  /** Human label for the picker. */
  label: string
  capabilities: ModelCapability[]
  /** Context window in tokens, when known. */
  context?: number
  /** Short note (e.g. "flagship", "cheapest", "text-only"). */
  note?: string
}

export type ProviderInfo = {
  id: string
  name: string
  mode: ProviderMode
  region: ProviderRegion
  /** OpenAI-compatible /chat/completions base URL (most providers expose one). */
  baseUrl: string
  /** Provider docs / console URL shown in settings. */
  docsUrl: string
  /** Cloud providers need a key; local ones don't. */
  requiresApiKey: boolean
  /** True when /v1/chat/completions speaks the OpenAI schema. */
  openAICompatible: boolean
  /**
   * When true, the model list is discovered at runtime (e.g. Ollama/LM Studio
   * expose /models for whatever the user pulled). `models` then holds popular
   * suggestions rather than an exhaustive list.
   */
  dynamicModels?: boolean
  models: ModelInfo[]
  note?: string
}

const T: ModelCapability[] = ['text', 'tools']
const TV: ModelCapability[] = ['text', 'vision', 'tools']
const TVR: ModelCapability[] = ['text', 'vision', 'tools', 'reasoning']
const TR: ModelCapability[] = ['text', 'tools', 'reasoning']

// ---------------------------------------------------------------------------
// Local providers — private, no API key, run on the user's own hardware.
// ---------------------------------------------------------------------------

const LOCAL: ProviderInfo[] = [
  {
    id: 'ollama',
    name: 'Ollama',
    mode: 'local',
    region: 'local',
    baseUrl: 'http://localhost:11434/v1',
    docsUrl: 'https://ollama.com',
    requiresApiKey: false,
    openAICompatible: true,
    dynamicModels: true,
    note: 'Runs models locally. The list below is suggestions — pull any model with `ollama pull`.',
    models: [
      { id: 'llama3.3:70b', label: 'Llama 3.3 70B', capabilities: T, context: 128000 },
      { id: 'qwen3:8b', label: 'Qwen3 8B', capabilities: TR, context: 128000 },
      { id: 'qwen3:30b', label: 'Qwen3 30B', capabilities: TR, context: 128000 },
      {
        id: 'gpt-oss:20b',
        label: 'GPT-OSS 20B',
        capabilities: TR,
        context: 128000,
        note: 'great default'
      },
      { id: 'gpt-oss:120b', label: 'GPT-OSS 120B', capabilities: TR, context: 128000 },
      {
        id: 'qwen3-coder:30b',
        label: 'Qwen3 Coder 30B',
        capabilities: T,
        context: 256000,
        note: 'coding/agent'
      },
      { id: 'gemma3:12b', label: 'Gemma 3 12B', capabilities: TV, context: 128000 },
      {
        id: 'llama3.2-vision:11b',
        label: 'Llama 3.2 Vision 11B',
        capabilities: TV,
        context: 128000
      }
    ]
  },
  {
    id: 'lmstudio',
    name: 'LM Studio',
    mode: 'local',
    region: 'local',
    baseUrl: 'http://localhost:1234/v1',
    docsUrl: 'https://lmstudio.ai',
    requiresApiKey: false,
    openAICompatible: true,
    dynamicModels: true,
    note: 'Runs GGUF models locally via LM Studio’s OpenAI-compatible server (enable it in LM Studio → Developer).',
    models: [
      { id: 'openai/gpt-oss-20b', label: 'GPT-OSS 20B', capabilities: TR, context: 128000 },
      { id: 'qwen/qwen3-8b', label: 'Qwen3 8B', capabilities: TR, context: 128000 },
      { id: 'qwen/qwen3-coder-30b', label: 'Qwen3 Coder 30B', capabilities: T, context: 256000 },
      { id: 'google/gemma-3-12b', label: 'Gemma 3 12B', capabilities: TV, context: 128000 }
    ]
  }
]

// ---------------------------------------------------------------------------
// Cloud providers — BYOK. Grouped by region below for the picker.
// ---------------------------------------------------------------------------

const NORTH_AMERICA: ProviderInfo[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    mode: 'cloud',
    region: 'north-america',
    baseUrl: 'https://api.openai.com/v1',
    docsUrl: 'https://platform.openai.com/docs/models',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      { id: 'gpt-5.5', label: 'GPT-5.5', capabilities: TVR, context: 1000000, note: 'flagship' },
      {
        id: 'gpt-5.5-pro',
        label: 'GPT-5.5 Pro',
        capabilities: TVR,
        context: 1000000,
        note: 'highest accuracy'
      },
      {
        id: 'gpt-5.4-mini',
        label: 'GPT-5.4 mini',
        capabilities: TV,
        context: 400000,
        note: 'fast/cheap'
      },
      {
        id: 'gpt-5.4-nano',
        label: 'GPT-5.4 nano',
        capabilities: TV,
        context: 400000,
        note: 'cheapest'
      },
      { id: 'gpt-5', label: 'GPT-5', capabilities: TVR, context: 400000 }
    ]
  },
  {
    id: 'anthropic',
    name: 'Anthropic (Claude)',
    mode: 'cloud',
    region: 'north-america',
    baseUrl: 'https://api.anthropic.com/v1',
    docsUrl: 'https://docs.claude.com/en/docs/about-claude/models',
    requiresApiKey: true,
    openAICompatible: false,
    note: 'Uses Anthropic’s native Messages API (not OpenAI-compatible).',
    models: [
      {
        id: 'claude-opus-4-8',
        label: 'Claude Opus 4.8',
        capabilities: TVR,
        context: 1000000,
        note: 'most capable'
      },
      {
        id: 'claude-sonnet-4-6',
        label: 'Claude Sonnet 4.6',
        capabilities: TVR,
        context: 1000000,
        note: 'balanced'
      },
      {
        id: 'claude-haiku-4-5-20251001',
        label: 'Claude Haiku 4.5',
        capabilities: TV,
        context: 200000,
        note: 'fast/cheap'
      }
    ]
  },
  {
    id: 'xai',
    name: 'xAI (Grok)',
    mode: 'cloud',
    region: 'north-america',
    baseUrl: 'https://api.x.ai/v1',
    docsUrl: 'https://docs.x.ai/developers/models',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      { id: 'grok-4.3', label: 'Grok 4.3', capabilities: TVR, context: 256000, note: 'flagship' },
      {
        id: 'grok-4.20',
        label: 'Grok 4.20',
        capabilities: TR,
        context: 256000,
        note: 'low hallucination'
      },
      { id: 'grok-4.1', label: 'Grok 4.1', capabilities: TV, context: 256000 },
      { id: 'grok-4', label: 'Grok 4', capabilities: TVR, context: 256000 }
    ]
  },
  {
    id: 'groq',
    name: 'Groq',
    mode: 'cloud',
    region: 'north-america',
    baseUrl: 'https://api.groq.com/openai/v1',
    docsUrl: 'https://console.groq.com/docs/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Ultra-fast LPU inference for open models.',
    models: [
      { id: 'openai/gpt-oss-120b', label: 'GPT-OSS 120B', capabilities: TR, context: 128000 },
      { id: 'openai/gpt-oss-20b', label: 'GPT-OSS 20B', capabilities: TR, context: 128000 },
      { id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B', capabilities: T, context: 128000 },
      {
        id: 'llama-3.1-8b-instant',
        label: 'Llama 3.1 8B Instant',
        capabilities: T,
        context: 128000,
        note: 'cheapest'
      },
      { id: 'moonshotai/kimi-k2.6', label: 'Kimi K2.6', capabilities: TR, context: 256000 }
    ]
  },
  {
    id: 'together',
    name: 'Together AI',
    mode: 'cloud',
    region: 'north-america',
    baseUrl: 'https://api.together.xyz/v1',
    docsUrl: 'https://docs.together.ai/docs/serverless-models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Serverless access to 200+ open models.',
    models: [
      {
        id: 'deepseek-ai/DeepSeek-V4-Pro',
        label: 'DeepSeek V4 Pro',
        capabilities: TR,
        context: 128000
      },
      {
        id: 'meta-llama/Llama-3.3-70B-Instruct-Turbo',
        label: 'Llama 3.3 70B Turbo',
        capabilities: T,
        context: 128000
      },
      { id: 'Qwen/Qwen3-235B-A22B', label: 'Qwen3 235B', capabilities: TR, context: 128000 },
      { id: 'moonshotai/Kimi-K2.6', label: 'Kimi K2.6', capabilities: TR, context: 256000 },
      { id: 'zai-org/GLM-5', label: 'GLM-5', capabilities: TR, context: 200000 }
    ]
  }
]

const EUROPE: ProviderInfo[] = [
  {
    id: 'mistral',
    name: 'Mistral AI',
    mode: 'cloud',
    region: 'europe',
    baseUrl: 'https://api.mistral.ai/v1',
    docsUrl: 'https://docs.mistral.ai/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'EU-based (France).',
    models: [
      {
        id: 'mistral-large-latest',
        label: 'Mistral Large 3',
        capabilities: T,
        context: 128000,
        note: 'flagship'
      },
      {
        id: 'mistral-medium-latest',
        label: 'Mistral Medium 3.5',
        capabilities: TV,
        context: 128000
      },
      {
        id: 'mistral-small-latest',
        label: 'Mistral Small 4',
        capabilities: TVR,
        context: 128000,
        note: 'multimodal, cheap'
      },
      {
        id: 'magistral-medium-latest',
        label: 'Magistral Medium',
        capabilities: TR,
        context: 128000,
        note: 'reasoning'
      },
      {
        id: 'codestral-latest',
        label: 'Codestral',
        capabilities: T,
        context: 256000,
        note: 'coding'
      }
    ]
  }
]

const CHINA: ProviderInfo[] = [
  {
    id: 'dashscope',
    name: 'Alibaba DashScope (Qwen)',
    mode: 'cloud',
    region: 'china',
    // International (Singapore) OpenAI-compatible endpoint.
    baseUrl: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
    docsUrl: 'https://www.alibabacloud.com/help/en/model-studio/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Alibaba Cloud Model Studio. International endpoint (Singapore).',
    models: [
      {
        id: 'qwen3.7-max',
        label: 'Qwen3.7 Max',
        capabilities: T,
        context: 256000,
        note: 'flagship'
      },
      {
        id: 'qwen3.7-plus',
        label: 'Qwen3.7 Plus',
        capabilities: TV,
        context: 1000000,
        note: 'multimodal agent'
      },
      {
        id: 'qwen3.6-flash',
        label: 'Qwen3.6 Flash',
        capabilities: T,
        context: 1000000,
        note: 'cheapest'
      },
      { id: 'qwen-max', label: 'Qwen Max', capabilities: T, context: 32000 },
      { id: 'qwen-plus', label: 'Qwen Plus', capabilities: T, context: 131000 }
    ]
  },
  {
    id: 'zhipu',
    name: 'Zhipu / Z.ai (GLM)',
    mode: 'cloud',
    region: 'china',
    baseUrl: 'https://api.z.ai/api/paas/v4',
    docsUrl: 'https://docs.z.ai',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      {
        id: 'glm-5',
        label: 'GLM-5',
        capabilities: TR,
        context: 200000,
        note: 'flagship, MIT-licensed'
      },
      { id: 'glm-4.6', label: 'GLM-4.6', capabilities: TR, context: 200000 },
      { id: 'glm-4.6v', label: 'GLM-4.6V', capabilities: TV, context: 200000, note: 'vision' }
    ]
  },
  {
    id: 'moonshot',
    name: 'Moonshot AI (Kimi)',
    mode: 'cloud',
    region: 'china',
    baseUrl: 'https://api.moonshot.ai/v1',
    docsUrl: 'https://platform.moonshot.ai',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      {
        id: 'kimi-k2.6',
        label: 'Kimi K2.6',
        capabilities: TR,
        context: 256000,
        note: 'flagship agentic'
      },
      {
        id: 'kimi-k2.7-code',
        label: 'Kimi K2.7 Code',
        capabilities: TR,
        context: 256000,
        note: 'coding'
      },
      { id: 'kimi-latest', label: 'Kimi (latest)', capabilities: TV, context: 256000 }
    ]
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    mode: 'cloud',
    region: 'china',
    baseUrl: 'https://api.deepseek.com/v1',
    docsUrl: 'https://api-docs.deepseek.com',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Text-only (no vision input).',
    models: [
      {
        id: 'deepseek-v4-pro',
        label: 'DeepSeek V4 Pro',
        capabilities: TR,
        context: 128000,
        note: 'reasoning/agent'
      },
      {
        id: 'deepseek-v4-flash',
        label: 'DeepSeek V4 Flash',
        capabilities: T,
        context: 128000,
        note: 'fast/cheap'
      },
      { id: 'deepseek-chat', label: 'deepseek-chat (V4 Flash)', capabilities: T, context: 128000 },
      {
        id: 'deepseek-reasoner',
        label: 'deepseek-reasoner (V4 Flash think)',
        capabilities: TR,
        context: 128000
      }
    ]
  },
  {
    id: 'tencent',
    name: 'Tencent Hunyuan',
    mode: 'cloud',
    region: 'china',
    baseUrl: 'https://api.hunyuan.cloud.tencent.com/v1',
    docsUrl: 'https://cloud.tencent.com/document/product/1729',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      {
        id: 'hunyuan-turbos-latest',
        label: 'Hunyuan TurboS',
        capabilities: T,
        context: 256000,
        note: 'flagship'
      },
      {
        id: 'hunyuan-t1-latest',
        label: 'Hunyuan T1',
        capabilities: TR,
        context: 128000,
        note: 'reasoning'
      },
      { id: 'hunyuan-large', label: 'Hunyuan Large', capabilities: T, context: 32000 }
    ]
  },
  {
    id: 'baidu',
    name: 'Baidu ERNIE',
    mode: 'cloud',
    region: 'china',
    baseUrl: 'https://qianfan.baidubce.com/v2',
    docsUrl: 'https://cloud.baidu.com/doc/qianfan-api',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      { id: 'ernie-5.0', label: 'ERNIE 5.0', capabilities: TVR, context: 128000, note: 'flagship' },
      {
        id: 'ernie-4.5-turbo-128k',
        label: 'ERNIE 4.5 Turbo 128K',
        capabilities: T,
        context: 128000
      },
      {
        id: 'ernie-4.5-vl-424b-a47b',
        label: 'ERNIE 4.5 VL',
        capabilities: TV,
        context: 128000,
        note: 'vision'
      }
    ]
  },
  {
    id: 'volcengine',
    name: 'Volcengine (Doubao)',
    mode: 'cloud',
    region: 'china',
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    docsUrl: 'https://www.volcengine.com/docs/82379',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'ByteDance’s Doubao models via Volcengine Ark.',
    models: [
      {
        id: 'doubao-seed-2.1-pro',
        label: 'Doubao Seed 2.1 Pro',
        capabilities: TV,
        context: 256000,
        note: 'flagship'
      },
      {
        id: 'doubao-seed-2.1-turbo',
        label: 'Doubao Seed 2.1 Turbo',
        capabilities: T,
        context: 256000,
        note: 'cheap'
      },
      { id: 'doubao-1.6-vision', label: 'Doubao 1.6 Vision', capabilities: TV, context: 256000 }
    ]
  }
]

const GLOBAL: ProviderInfo[] = [
  {
    id: 'ollama-cloud',
    name: 'Ollama Cloud',
    mode: 'cloud',
    region: 'global',
    baseUrl: 'https://ollama.com/v1',
    docsUrl: 'https://docs.ollama.com/cloud',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Hosted big open models (the `:cloud` tags) — same Ollama API, no local GPU needed.',
    models: [
      {
        id: 'gpt-oss:120b-cloud',
        label: 'GPT-OSS 120B (cloud)',
        capabilities: TR,
        context: 128000
      },
      { id: 'gpt-oss:20b-cloud', label: 'GPT-OSS 20B (cloud)', capabilities: TR, context: 128000 },
      {
        id: 'qwen3-coder:480b-cloud',
        label: 'Qwen3 Coder 480B (cloud)',
        capabilities: T,
        context: 256000,
        note: 'agentic coding'
      },
      {
        id: 'deepseek-v3.1:671b-cloud',
        label: 'DeepSeek V3.1 671B (cloud)',
        capabilities: TR,
        context: 128000
      }
    ]
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    mode: 'cloud',
    region: 'global',
    baseUrl: 'https://openrouter.ai/api/v1',
    docsUrl: 'https://openrouter.ai/models',
    requiresApiKey: true,
    openAICompatible: true,
    dynamicModels: true,
    note: 'One key routes to 400+ models across 60+ providers. Suggestions below; any OpenRouter model id works.',
    models: [
      {
        id: 'anthropic/claude-opus-4.8',
        label: 'Claude Opus 4.8',
        capabilities: TVR,
        context: 1000000
      },
      { id: 'openai/gpt-5.5', label: 'GPT-5.5', capabilities: TVR, context: 1000000 },
      {
        id: 'google/gemini-3.5-flash',
        label: 'Gemini 3.5 Flash',
        capabilities: TV,
        context: 1000000
      },
      {
        id: 'deepseek/deepseek-v4-pro',
        label: 'DeepSeek V4 Pro',
        capabilities: TR,
        context: 128000
      },
      { id: 'z-ai/glm-5', label: 'GLM-5', capabilities: TR, context: 200000 }
    ]
  },
  {
    id: 'google',
    name: 'Google (Gemini)',
    mode: 'cloud',
    region: 'global',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    docsUrl: 'https://ai.google.dev/gemini-api/docs/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Gemini via the OpenAI-compatible endpoint.',
    models: [
      {
        id: 'gemini-3.5-flash',
        label: 'Gemini 3.5 Flash',
        capabilities: TVR,
        context: 1000000,
        note: 'best value'
      },
      {
        id: 'gemini-3.1-pro',
        label: 'Gemini 3.1 Pro',
        capabilities: TVR,
        context: 1000000,
        note: 'strongest'
      },
      {
        id: 'gemini-3.1-flash-lite',
        label: 'Gemini 3.1 Flash-Lite',
        capabilities: TV,
        context: 1000000,
        note: 'cheapest'
      },
      { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', capabilities: TV, context: 1000000 }
    ]
  },
  {
    id: 'custom',
    name: 'Custom (OpenAI-compatible)',
    mode: 'cloud',
    region: 'global',
    baseUrl: '',
    docsUrl: '',
    requiresApiKey: false,
    openAICompatible: true,
    dynamicModels: true,
    note: 'Point Cortex at any OpenAI-compatible endpoint — set the base URL, optional key, and model id yourself.',
    models: []
  }
]

export const PROVIDERS: ProviderInfo[] = [
  ...LOCAL,
  ...NORTH_AMERICA,
  ...EUROPE,
  ...CHINA,
  ...GLOBAL
]

export const REGION_LABELS: Record<ProviderRegion, string> = {
  local: 'On your computer',
  'north-america': 'North America',
  europe: 'Europe',
  china: 'China',
  global: 'Global / Aggregators'
}

/** Display order for region groups in the picker. */
export const REGION_ORDER: ProviderRegion[] = [
  'local',
  'north-america',
  'europe',
  'china',
  'global'
]

export function getProvider(id: string): ProviderInfo | undefined {
  return PROVIDERS.find((p) => p.id === id)
}

export function getModel(providerId: string, modelId: string): ModelInfo | undefined {
  return getProvider(providerId)?.models.find((m) => m.id === modelId)
}

/** Providers grouped by region, in display order. Empty groups are omitted. */
export function providersByRegion(): {
  region: ProviderRegion
  label: string
  providers: ProviderInfo[]
}[] {
  return REGION_ORDER.map((region) => ({
    region,
    label: REGION_LABELS[region],
    providers: PROVIDERS.filter((p) => p.region === region)
  })).filter((g) => g.providers.length > 0)
}

export function localProviders(): ProviderInfo[] {
  return PROVIDERS.filter((p) => p.mode === 'local')
}

export function cloudProviders(): ProviderInfo[] {
  return PROVIDERS.filter((p) => p.mode === 'cloud')
}
