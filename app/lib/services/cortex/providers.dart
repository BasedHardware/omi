// Cortex AI provider registry (Flutter port of desktop/windows/src/shared/providers.ts).
//
// Cortex runs its AI either on a *local* model (private, no key, on the user's
// own machine) or a *cloud* provider (BYOK). Providers are grouped by region so
// the user controls where their data is processed. Pure data + helpers.

enum ModelCapability { text, vision, tools, reasoning }

enum ProviderRegion { local, northAmerica, europe, china, global }

enum ProviderMode { local, cloud }

class ModelInfo {
  final String id;
  final String label;
  final List<ModelCapability> capabilities;
  final int? context;
  final String? note;

  const ModelInfo(this.id, this.label, this.capabilities, {this.context, this.note});

  bool get supportsVision => capabilities.contains(ModelCapability.vision);
}

class ProviderInfo {
  final String id;
  final String name;
  final ProviderMode mode;
  final ProviderRegion region;
  final String baseUrl;
  final String docsUrl;
  final bool requiresApiKey;
  final bool openAICompatible;
  final bool dynamicModels;
  final List<ModelInfo> models;
  final String? note;

  const ProviderInfo({
    required this.id,
    required this.name,
    required this.mode,
    required this.region,
    required this.baseUrl,
    required this.docsUrl,
    required this.requiresApiKey,
    required this.openAICompatible,
    this.dynamicModels = false,
    required this.models,
    this.note,
  });
}

const _t = [ModelCapability.text, ModelCapability.tools];
const _tv = [ModelCapability.text, ModelCapability.vision, ModelCapability.tools];
const _tvr = [ModelCapability.text, ModelCapability.vision, ModelCapability.tools, ModelCapability.reasoning];
const _tr = [ModelCapability.text, ModelCapability.tools, ModelCapability.reasoning];

const List<ProviderInfo> kCortexProviders = [
  // -------- Local --------
  ProviderInfo(
    id: 'ollama',
    name: 'Ollama',
    mode: ProviderMode.local,
    region: ProviderRegion.local,
    baseUrl: 'http://localhost:11434/v1',
    docsUrl: 'https://ollama.com',
    requiresApiKey: false,
    openAICompatible: true,
    dynamicModels: true,
    note: 'Runs models locally. Suggestions below — pull any model with `ollama pull`.',
    models: [
      ModelInfo('llama3.3:70b', 'Llama 3.3 70B', _t, context: 128000),
      ModelInfo('qwen3:8b', 'Qwen3 8B', _tr, context: 128000),
      ModelInfo('gpt-oss:20b', 'GPT-OSS 20B', _tr, context: 128000, note: 'great default'),
      ModelInfo('gpt-oss:120b', 'GPT-OSS 120B', _tr, context: 128000),
      ModelInfo('qwen3-coder:30b', 'Qwen3 Coder 30B', _t, context: 256000, note: 'coding/agent'),
      ModelInfo('gemma3:12b', 'Gemma 3 12B', _tv, context: 128000),
    ],
  ),
  ProviderInfo(
    id: 'lmstudio',
    name: 'LM Studio',
    mode: ProviderMode.local,
    region: ProviderRegion.local,
    baseUrl: 'http://localhost:1234/v1',
    docsUrl: 'https://lmstudio.ai',
    requiresApiKey: false,
    openAICompatible: true,
    dynamicModels: true,
    note: 'Runs GGUF models locally via LM Studio’s OpenAI-compatible server.',
    models: [
      ModelInfo('openai/gpt-oss-20b', 'GPT-OSS 20B', _tr, context: 128000),
      ModelInfo('qwen/qwen3-8b', 'Qwen3 8B', _tr, context: 128000),
      ModelInfo('qwen/qwen3-coder-30b', 'Qwen3 Coder 30B', _t, context: 256000),
      ModelInfo('google/gemma-3-12b', 'Gemma 3 12B', _tv, context: 128000),
    ],
  ),

  // -------- North America --------
  ProviderInfo(
    id: 'openai',
    name: 'OpenAI',
    mode: ProviderMode.cloud,
    region: ProviderRegion.northAmerica,
    baseUrl: 'https://api.openai.com/v1',
    docsUrl: 'https://platform.openai.com/docs/models',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      ModelInfo('gpt-5.5', 'GPT-5.5', _tvr, context: 1000000, note: 'flagship'),
      ModelInfo('gpt-5.5-pro', 'GPT-5.5 Pro', _tvr, context: 1000000, note: 'highest accuracy'),
      ModelInfo('gpt-5.4-mini', 'GPT-5.4 mini', _tv, context: 400000, note: 'fast/cheap'),
      ModelInfo('gpt-5.4-nano', 'GPT-5.4 nano', _tv, context: 400000, note: 'cheapest'),
      ModelInfo('gpt-5', 'GPT-5', _tvr, context: 400000),
    ],
  ),
  ProviderInfo(
    id: 'anthropic',
    name: 'Anthropic (Claude)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.northAmerica,
    baseUrl: 'https://api.anthropic.com/v1',
    docsUrl: 'https://docs.claude.com/en/docs/about-claude/models',
    requiresApiKey: true,
    openAICompatible: false,
    note: 'Uses Anthropic’s native Messages API (not OpenAI-compatible).',
    models: [
      ModelInfo('claude-opus-4-8', 'Claude Opus 4.8', _tvr, context: 1000000, note: 'most capable'),
      ModelInfo('claude-sonnet-4-6', 'Claude Sonnet 4.6', _tvr, context: 1000000, note: 'balanced'),
      ModelInfo('claude-haiku-4-5-20251001', 'Claude Haiku 4.5', _tv, context: 200000, note: 'fast/cheap'),
    ],
  ),
  ProviderInfo(
    id: 'xai',
    name: 'xAI (Grok)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.northAmerica,
    baseUrl: 'https://api.x.ai/v1',
    docsUrl: 'https://docs.x.ai/developers/models',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      ModelInfo('grok-4.3', 'Grok 4.3', _tvr, context: 256000, note: 'flagship'),
      ModelInfo('grok-4.20', 'Grok 4.20', _tr, context: 256000, note: 'low hallucination'),
      ModelInfo('grok-4.1', 'Grok 4.1', _tv, context: 256000),
      ModelInfo('grok-4', 'Grok 4', _tvr, context: 256000),
    ],
  ),
  ProviderInfo(
    id: 'groq',
    name: 'Groq',
    mode: ProviderMode.cloud,
    region: ProviderRegion.northAmerica,
    baseUrl: 'https://api.groq.com/openai/v1',
    docsUrl: 'https://console.groq.com/docs/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Ultra-fast LPU inference for open models.',
    models: [
      ModelInfo('openai/gpt-oss-120b', 'GPT-OSS 120B', _tr, context: 128000),
      ModelInfo('openai/gpt-oss-20b', 'GPT-OSS 20B', _tr, context: 128000),
      ModelInfo('llama-3.3-70b-versatile', 'Llama 3.3 70B', _t, context: 128000),
      ModelInfo('llama-3.1-8b-instant', 'Llama 3.1 8B Instant', _t, context: 128000, note: 'cheapest'),
      ModelInfo('moonshotai/kimi-k2.6', 'Kimi K2.6', _tr, context: 256000),
    ],
  ),
  ProviderInfo(
    id: 'together',
    name: 'Together AI',
    mode: ProviderMode.cloud,
    region: ProviderRegion.northAmerica,
    baseUrl: 'https://api.together.xyz/v1',
    docsUrl: 'https://docs.together.ai/docs/serverless-models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Serverless access to 200+ open models.',
    models: [
      ModelInfo('deepseek-ai/DeepSeek-V4-Pro', 'DeepSeek V4 Pro', _tr, context: 128000),
      ModelInfo('meta-llama/Llama-3.3-70B-Instruct-Turbo', 'Llama 3.3 70B Turbo', _t, context: 128000),
      ModelInfo('Qwen/Qwen3-235B-A22B', 'Qwen3 235B', _tr, context: 128000),
      ModelInfo('moonshotai/Kimi-K2.6', 'Kimi K2.6', _tr, context: 256000),
      ModelInfo('zai-org/GLM-5', 'GLM-5', _tr, context: 200000),
    ],
  ),

  // -------- Europe --------
  ProviderInfo(
    id: 'mistral',
    name: 'Mistral AI',
    mode: ProviderMode.cloud,
    region: ProviderRegion.europe,
    baseUrl: 'https://api.mistral.ai/v1',
    docsUrl: 'https://docs.mistral.ai/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'EU-based (France).',
    models: [
      ModelInfo('mistral-large-latest', 'Mistral Large 3', _t, context: 128000, note: 'flagship'),
      ModelInfo('mistral-medium-latest', 'Mistral Medium 3.5', _tv, context: 128000),
      ModelInfo('mistral-small-latest', 'Mistral Small 4', _tvr, context: 128000, note: 'multimodal, cheap'),
      ModelInfo('magistral-medium-latest', 'Magistral Medium', _tr, context: 128000, note: 'reasoning'),
      ModelInfo('codestral-latest', 'Codestral', _t, context: 256000, note: 'coding'),
    ],
  ),

  // -------- China --------
  ProviderInfo(
    id: 'dashscope',
    name: 'Alibaba DashScope (Qwen)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.china,
    baseUrl: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
    docsUrl: 'https://www.alibabacloud.com/help/en/model-studio/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Alibaba Cloud Model Studio. International endpoint (Singapore).',
    models: [
      ModelInfo('qwen3.7-max', 'Qwen3.7 Max', _t, context: 256000, note: 'flagship'),
      ModelInfo('qwen3.7-plus', 'Qwen3.7 Plus', _tv, context: 1000000, note: 'multimodal agent'),
      ModelInfo('qwen3.6-flash', 'Qwen3.6 Flash', _t, context: 1000000, note: 'cheapest'),
      ModelInfo('qwen-max', 'Qwen Max', _t, context: 32000),
      ModelInfo('qwen-plus', 'Qwen Plus', _t, context: 131000),
    ],
  ),
  ProviderInfo(
    id: 'zhipu',
    name: 'Zhipu / Z.ai (GLM)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.china,
    baseUrl: 'https://api.z.ai/api/paas/v4',
    docsUrl: 'https://docs.z.ai',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      ModelInfo('glm-5', 'GLM-5', _tr, context: 200000, note: 'flagship, MIT-licensed'),
      ModelInfo('glm-4.6', 'GLM-4.6', _tr, context: 200000),
      ModelInfo('glm-4.6v', 'GLM-4.6V', _tv, context: 200000, note: 'vision'),
    ],
  ),
  ProviderInfo(
    id: 'moonshot',
    name: 'Moonshot AI (Kimi)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.china,
    baseUrl: 'https://api.moonshot.ai/v1',
    docsUrl: 'https://platform.moonshot.ai',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      ModelInfo('kimi-k2.6', 'Kimi K2.6', _tr, context: 256000, note: 'flagship agentic'),
      ModelInfo('kimi-k2.7-code', 'Kimi K2.7 Code', _tr, context: 256000, note: 'coding'),
      ModelInfo('kimi-latest', 'Kimi (latest)', _tv, context: 256000),
    ],
  ),
  ProviderInfo(
    id: 'deepseek',
    name: 'DeepSeek',
    mode: ProviderMode.cloud,
    region: ProviderRegion.china,
    baseUrl: 'https://api.deepseek.com/v1',
    docsUrl: 'https://api-docs.deepseek.com',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Text-only (no vision input).',
    models: [
      ModelInfo('deepseek-v4-pro', 'DeepSeek V4 Pro', _tr, context: 128000, note: 'reasoning/agent'),
      ModelInfo('deepseek-v4-flash', 'DeepSeek V4 Flash', _t, context: 128000, note: 'fast/cheap'),
      ModelInfo('deepseek-chat', 'deepseek-chat (V4 Flash)', _t, context: 128000),
      ModelInfo('deepseek-reasoner', 'deepseek-reasoner (V4 Flash think)', _tr, context: 128000),
    ],
  ),
  ProviderInfo(
    id: 'tencent',
    name: 'Tencent Hunyuan',
    mode: ProviderMode.cloud,
    region: ProviderRegion.china,
    baseUrl: 'https://api.hunyuan.cloud.tencent.com/v1',
    docsUrl: 'https://cloud.tencent.com/document/product/1729',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      ModelInfo('hunyuan-turbos-latest', 'Hunyuan TurboS', _t, context: 256000, note: 'flagship'),
      ModelInfo('hunyuan-t1-latest', 'Hunyuan T1', _tr, context: 128000, note: 'reasoning'),
      ModelInfo('hunyuan-large', 'Hunyuan Large', _t, context: 32000),
    ],
  ),
  ProviderInfo(
    id: 'baidu',
    name: 'Baidu ERNIE',
    mode: ProviderMode.cloud,
    region: ProviderRegion.china,
    baseUrl: 'https://qianfan.baidubce.com/v2',
    docsUrl: 'https://cloud.baidu.com/doc/qianfan-api',
    requiresApiKey: true,
    openAICompatible: true,
    models: [
      ModelInfo('ernie-5.0', 'ERNIE 5.0', _tvr, context: 128000, note: 'flagship'),
      ModelInfo('ernie-4.5-turbo-128k', 'ERNIE 4.5 Turbo 128K', _t, context: 128000),
      ModelInfo('ernie-4.5-vl-424b-a47b', 'ERNIE 4.5 VL', _tv, context: 128000, note: 'vision'),
    ],
  ),
  ProviderInfo(
    id: 'volcengine',
    name: 'Volcengine (Doubao)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.china,
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    docsUrl: 'https://www.volcengine.com/docs/82379',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'ByteDance’s Doubao models via Volcengine Ark.',
    models: [
      ModelInfo('doubao-seed-2.1-pro', 'Doubao Seed 2.1 Pro', _tv, context: 256000, note: 'flagship'),
      ModelInfo('doubao-seed-2.1-turbo', 'Doubao Seed 2.1 Turbo', _t, context: 256000, note: 'cheap'),
      ModelInfo('doubao-1.6-vision', 'Doubao 1.6 Vision', _tv, context: 256000),
    ],
  ),

  // -------- Global / aggregators --------
  ProviderInfo(
    id: 'ollama-cloud',
    name: 'Ollama Cloud',
    mode: ProviderMode.cloud,
    region: ProviderRegion.global,
    baseUrl: 'https://ollama.com/v1',
    docsUrl: 'https://docs.ollama.com/cloud',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Hosted big open models (the `-cloud` tags) — no local GPU needed.',
    models: [
      ModelInfo('gpt-oss:120b-cloud', 'GPT-OSS 120B (cloud)', _tr, context: 128000),
      ModelInfo('gpt-oss:20b-cloud', 'GPT-OSS 20B (cloud)', _tr, context: 128000),
      ModelInfo('qwen3-coder:480b-cloud', 'Qwen3 Coder 480B (cloud)', _t, context: 256000, note: 'agentic coding'),
      ModelInfo('deepseek-v3.1:671b-cloud', 'DeepSeek V3.1 671B (cloud)', _tr, context: 128000),
    ],
  ),
  ProviderInfo(
    id: 'openrouter',
    name: 'OpenRouter',
    mode: ProviderMode.cloud,
    region: ProviderRegion.global,
    baseUrl: 'https://openrouter.ai/api/v1',
    docsUrl: 'https://openrouter.ai/models',
    requiresApiKey: true,
    openAICompatible: true,
    dynamicModels: true,
    note: 'One key routes to 400+ models. Suggestions below; any OpenRouter model id works.',
    models: [
      ModelInfo('anthropic/claude-opus-4.8', 'Claude Opus 4.8', _tvr, context: 1000000),
      ModelInfo('openai/gpt-5.5', 'GPT-5.5', _tvr, context: 1000000),
      ModelInfo('google/gemini-3.5-flash', 'Gemini 3.5 Flash', _tv, context: 1000000),
      ModelInfo('deepseek/deepseek-v4-pro', 'DeepSeek V4 Pro', _tr, context: 128000),
      ModelInfo('z-ai/glm-5', 'GLM-5', _tr, context: 200000),
    ],
  ),
  ProviderInfo(
    id: 'google',
    name: 'Google (Gemini)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.global,
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    docsUrl: 'https://ai.google.dev/gemini-api/docs/models',
    requiresApiKey: true,
    openAICompatible: true,
    note: 'Gemini via the OpenAI-compatible endpoint.',
    models: [
      ModelInfo('gemini-3.5-flash', 'Gemini 3.5 Flash', _tvr, context: 1000000, note: 'best value'),
      ModelInfo('gemini-3.1-pro', 'Gemini 3.1 Pro', _tvr, context: 1000000, note: 'strongest'),
      ModelInfo('gemini-3.1-flash-lite', 'Gemini 3.1 Flash-Lite', _tv, context: 1000000, note: 'cheapest'),
      ModelInfo('gemini-2.5-flash', 'Gemini 2.5 Flash', _tv, context: 1000000),
    ],
  ),
  ProviderInfo(
    id: 'custom',
    name: 'Custom (OpenAI-compatible)',
    mode: ProviderMode.cloud,
    region: ProviderRegion.global,
    baseUrl: '',
    docsUrl: '',
    requiresApiKey: false,
    openAICompatible: true,
    dynamicModels: true,
    note: 'Point Cortex at any OpenAI-compatible endpoint — set base URL, optional key, and model id.',
    models: [],
  ),
];

const Map<ProviderRegion, String> kRegionLabels = {
  ProviderRegion.local: 'On your computer',
  ProviderRegion.northAmerica: 'North America',
  ProviderRegion.europe: 'Europe',
  ProviderRegion.china: 'China',
  ProviderRegion.global: 'Global / Aggregators',
};

const List<ProviderRegion> kRegionOrder = [
  ProviderRegion.local,
  ProviderRegion.northAmerica,
  ProviderRegion.europe,
  ProviderRegion.china,
  ProviderRegion.global,
];

ProviderInfo? cortexProviderById(String? id) {
  if (id == null) return null;
  for (final p in kCortexProviders) {
    if (p.id == id) return p;
  }
  return null;
}

ModelInfo? cortexModel(String providerId, String? modelId) {
  if (modelId == null) return null;
  final p = cortexProviderById(providerId);
  if (p == null) return null;
  for (final m in p.models) {
    if (m.id == modelId) return m;
  }
  return null;
}

class RegionGroup {
  final ProviderRegion region;
  final String label;
  final List<ProviderInfo> providers;
  const RegionGroup(this.region, this.label, this.providers);
}

List<RegionGroup> cortexProvidersByRegion({bool cloudOnly = false}) {
  final groups = <RegionGroup>[];
  for (final region in kRegionOrder) {
    final ps = kCortexProviders
        .where((p) => p.region == region && (!cloudOnly || p.mode == ProviderMode.cloud))
        .toList();
    if (ps.isNotEmpty) groups.add(RegionGroup(region, kRegionLabels[region]!, ps));
  }
  return groups;
}

/// Phones can't run real (vision) local models, so the mobile app exposes cloud
/// providers only. Desktop keeps both local and cloud.
const bool kCortexMobileCloudOnly = true;
