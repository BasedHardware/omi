import Foundation

/// Cortex AI provider registry (Swift port of the Windows/Flutter registry).
///
/// Cortex runs its AI either on a *local* model (private, no key, on the user's
/// machine) or a *cloud* provider (BYOK). Providers are grouped by region so the
/// user controls where their data is processed. Pure data + helpers.

enum CortexModelCapability: String {
  case text, vision, tools, reasoning
}

enum CortexProviderRegion: String, CaseIterable {
  case local
  case northAmerica
  case europe
  case china
  case global

  var label: String {
    switch self {
    case .local: return "On your computer"
    case .northAmerica: return "North America"
    case .europe: return "Europe"
    case .china: return "China"
    case .global: return "Global / Aggregators"
    }
  }
}

enum CortexProviderMode { case local, cloud }

struct CortexModel: Identifiable {
  let id: String
  let label: String
  let capabilities: [CortexModelCapability]
  var context: Int? = nil
  var note: String? = nil
  var supportsVision: Bool { capabilities.contains(.vision) }
}

struct CortexProvider: Identifiable {
  let id: String
  let name: String
  let mode: CortexProviderMode
  let region: CortexProviderRegion
  let baseUrl: String
  let docsUrl: String
  let requiresApiKey: Bool
  let openAICompatible: Bool
  var dynamicModels: Bool = false
  let models: [CortexModel]
  var note: String? = nil
}

private let T: [CortexModelCapability] = [.text, .tools]
private let TV: [CortexModelCapability] = [.text, .vision, .tools]
private let TVR: [CortexModelCapability] = [.text, .vision, .tools, .reasoning]
private let TR: [CortexModelCapability] = [.text, .tools, .reasoning]

enum CortexProviders {
  static let all: [CortexProvider] = [
    // Local
    CortexProvider(
      id: "ollama", name: "Ollama", mode: .local, region: .local,
      baseUrl: "http://localhost:11434/v1", docsUrl: "https://ollama.com",
      requiresApiKey: false, openAICompatible: true, dynamicModels: true,
      models: [
        CortexModel(id: "llama3.3:70b", label: "Llama 3.3 70B", capabilities: T, context: 128000),
        CortexModel(id: "qwen3:8b", label: "Qwen3 8B", capabilities: TR, context: 128000),
        CortexModel(id: "gpt-oss:20b", label: "GPT-OSS 20B", capabilities: TR, context: 128000, note: "great default"),
        CortexModel(id: "gpt-oss:120b", label: "GPT-OSS 120B", capabilities: TR, context: 128000),
        CortexModel(id: "qwen3-coder:30b", label: "Qwen3 Coder 30B", capabilities: T, context: 256000, note: "coding"),
        CortexModel(id: "gemma3:12b", label: "Gemma 3 12B", capabilities: TV, context: 128000),
      ],
      note: "Runs models locally. Pull any model with `ollama pull`."),
    CortexProvider(
      id: "lmstudio", name: "LM Studio", mode: .local, region: .local,
      baseUrl: "http://localhost:1234/v1", docsUrl: "https://lmstudio.ai",
      requiresApiKey: false, openAICompatible: true, dynamicModels: true,
      models: [
        CortexModel(id: "openai/gpt-oss-20b", label: "GPT-OSS 20B", capabilities: TR, context: 128000),
        CortexModel(id: "qwen/qwen3-8b", label: "Qwen3 8B", capabilities: TR, context: 128000),
        CortexModel(id: "qwen/qwen3-coder-30b", label: "Qwen3 Coder 30B", capabilities: T, context: 256000),
        CortexModel(id: "google/gemma-3-12b", label: "Gemma 3 12B", capabilities: TV, context: 128000),
      ],
      note: "Runs GGUF models locally via LM Studio’s OpenAI-compatible server."),

    // North America
    CortexProvider(
      id: "openai", name: "OpenAI", mode: .cloud, region: .northAmerica,
      baseUrl: "https://api.openai.com/v1", docsUrl: "https://platform.openai.com/docs/models",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "gpt-5.5", label: "GPT-5.5", capabilities: TVR, context: 1000000, note: "flagship"),
        CortexModel(id: "gpt-5.5-pro", label: "GPT-5.5 Pro", capabilities: TVR, context: 1000000, note: "highest accuracy"),
        CortexModel(id: "gpt-5.4-mini", label: "GPT-5.4 mini", capabilities: TV, context: 400000, note: "fast/cheap"),
        CortexModel(id: "gpt-5.4-nano", label: "GPT-5.4 nano", capabilities: TV, context: 400000, note: "cheapest"),
        CortexModel(id: "gpt-5", label: "GPT-5", capabilities: TVR, context: 400000),
      ]),
    CortexProvider(
      id: "anthropic", name: "Anthropic (Claude)", mode: .cloud, region: .northAmerica,
      baseUrl: "https://api.anthropic.com/v1", docsUrl: "https://docs.claude.com/en/docs/about-claude/models",
      requiresApiKey: true, openAICompatible: false,
      models: [
        CortexModel(id: "claude-opus-4-8", label: "Claude Opus 4.8", capabilities: TVR, context: 1000000, note: "most capable"),
        CortexModel(id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", capabilities: TVR, context: 1000000, note: "balanced"),
        CortexModel(id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5", capabilities: TV, context: 200000, note: "fast/cheap"),
      ],
      note: "Uses Anthropic’s native Messages API (not OpenAI-compatible)."),
    CortexProvider(
      id: "xai", name: "xAI (Grok)", mode: .cloud, region: .northAmerica,
      baseUrl: "https://api.x.ai/v1", docsUrl: "https://docs.x.ai/developers/models",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "grok-4.3", label: "Grok 4.3", capabilities: TVR, context: 256000, note: "flagship"),
        CortexModel(id: "grok-4.20", label: "Grok 4.20", capabilities: TR, context: 256000, note: "low hallucination"),
        CortexModel(id: "grok-4.1", label: "Grok 4.1", capabilities: TV, context: 256000),
        CortexModel(id: "grok-4", label: "Grok 4", capabilities: TVR, context: 256000),
      ]),
    CortexProvider(
      id: "groq", name: "Groq", mode: .cloud, region: .northAmerica,
      baseUrl: "https://api.groq.com/openai/v1", docsUrl: "https://console.groq.com/docs/models",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "openai/gpt-oss-120b", label: "GPT-OSS 120B", capabilities: TR, context: 128000),
        CortexModel(id: "openai/gpt-oss-20b", label: "GPT-OSS 20B", capabilities: TR, context: 128000),
        CortexModel(id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B", capabilities: T, context: 128000),
        CortexModel(id: "llama-3.1-8b-instant", label: "Llama 3.1 8B Instant", capabilities: T, context: 128000, note: "cheapest"),
        CortexModel(id: "moonshotai/kimi-k2.6", label: "Kimi K2.6", capabilities: TR, context: 256000),
      ],
      note: "Ultra-fast LPU inference for open models."),
    CortexProvider(
      id: "together", name: "Together AI", mode: .cloud, region: .northAmerica,
      baseUrl: "https://api.together.xyz/v1", docsUrl: "https://docs.together.ai/docs/serverless-models",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "deepseek-ai/DeepSeek-V4-Pro", label: "DeepSeek V4 Pro", capabilities: TR, context: 128000),
        CortexModel(id: "meta-llama/Llama-3.3-70B-Instruct-Turbo", label: "Llama 3.3 70B Turbo", capabilities: T, context: 128000),
        CortexModel(id: "Qwen/Qwen3-235B-A22B", label: "Qwen3 235B", capabilities: TR, context: 128000),
        CortexModel(id: "moonshotai/Kimi-K2.6", label: "Kimi K2.6", capabilities: TR, context: 256000),
        CortexModel(id: "zai-org/GLM-5", label: "GLM-5", capabilities: TR, context: 200000),
      ],
      note: "Serverless access to 200+ open models."),

    // Europe
    CortexProvider(
      id: "mistral", name: "Mistral AI", mode: .cloud, region: .europe,
      baseUrl: "https://api.mistral.ai/v1", docsUrl: "https://docs.mistral.ai/models",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "mistral-large-latest", label: "Mistral Large 3", capabilities: T, context: 128000, note: "flagship"),
        CortexModel(id: "mistral-medium-latest", label: "Mistral Medium 3.5", capabilities: TV, context: 128000),
        CortexModel(id: "mistral-small-latest", label: "Mistral Small 4", capabilities: TVR, context: 128000, note: "multimodal, cheap"),
        CortexModel(id: "magistral-medium-latest", label: "Magistral Medium", capabilities: TR, context: 128000, note: "reasoning"),
        CortexModel(id: "codestral-latest", label: "Codestral", capabilities: T, context: 256000, note: "coding"),
      ],
      note: "EU-based (France)."),

    // China
    CortexProvider(
      id: "dashscope", name: "Alibaba DashScope (Qwen)", mode: .cloud, region: .china,
      baseUrl: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
      docsUrl: "https://www.alibabacloud.com/help/en/model-studio/models",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "qwen3.7-max", label: "Qwen3.7 Max", capabilities: T, context: 256000, note: "flagship"),
        CortexModel(id: "qwen3.7-plus", label: "Qwen3.7 Plus", capabilities: TV, context: 1000000, note: "multimodal agent"),
        CortexModel(id: "qwen3.6-flash", label: "Qwen3.6 Flash", capabilities: T, context: 1000000, note: "cheapest"),
        CortexModel(id: "qwen-max", label: "Qwen Max", capabilities: T, context: 32000),
        CortexModel(id: "qwen-plus", label: "Qwen Plus", capabilities: T, context: 131000),
      ],
      note: "Alibaba Cloud Model Studio. International endpoint (Singapore)."),
    CortexProvider(
      id: "zhipu", name: "Zhipu / Z.ai (GLM)", mode: .cloud, region: .china,
      baseUrl: "https://api.z.ai/api/paas/v4", docsUrl: "https://docs.z.ai",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "glm-5", label: "GLM-5", capabilities: TR, context: 200000, note: "flagship, MIT"),
        CortexModel(id: "glm-4.6", label: "GLM-4.6", capabilities: TR, context: 200000),
        CortexModel(id: "glm-4.6v", label: "GLM-4.6V", capabilities: TV, context: 200000, note: "vision"),
      ]),
    CortexProvider(
      id: "moonshot", name: "Moonshot AI (Kimi)", mode: .cloud, region: .china,
      baseUrl: "https://api.moonshot.ai/v1", docsUrl: "https://platform.moonshot.ai",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "kimi-k2.6", label: "Kimi K2.6", capabilities: TR, context: 256000, note: "flagship agentic"),
        CortexModel(id: "kimi-k2.7-code", label: "Kimi K2.7 Code", capabilities: TR, context: 256000, note: "coding"),
        CortexModel(id: "kimi-latest", label: "Kimi (latest)", capabilities: TV, context: 256000),
      ]),
    CortexProvider(
      id: "deepseek", name: "DeepSeek", mode: .cloud, region: .china,
      baseUrl: "https://api.deepseek.com/v1", docsUrl: "https://api-docs.deepseek.com",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "deepseek-v4-pro", label: "DeepSeek V4 Pro", capabilities: TR, context: 128000, note: "reasoning/agent"),
        CortexModel(id: "deepseek-v4-flash", label: "DeepSeek V4 Flash", capabilities: T, context: 128000, note: "fast/cheap"),
        CortexModel(id: "deepseek-chat", label: "deepseek-chat", capabilities: T, context: 128000),
        CortexModel(id: "deepseek-reasoner", label: "deepseek-reasoner", capabilities: TR, context: 128000),
      ],
      note: "Text-only (no vision input)."),
    CortexProvider(
      id: "tencent", name: "Tencent Hunyuan", mode: .cloud, region: .china,
      baseUrl: "https://api.hunyuan.cloud.tencent.com/v1", docsUrl: "https://cloud.tencent.com/document/product/1729",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "hunyuan-turbos-latest", label: "Hunyuan TurboS", capabilities: T, context: 256000, note: "flagship"),
        CortexModel(id: "hunyuan-t1-latest", label: "Hunyuan T1", capabilities: TR, context: 128000, note: "reasoning"),
        CortexModel(id: "hunyuan-large", label: "Hunyuan Large", capabilities: T, context: 32000),
      ]),
    CortexProvider(
      id: "baidu", name: "Baidu ERNIE", mode: .cloud, region: .china,
      baseUrl: "https://qianfan.baidubce.com/v2", docsUrl: "https://cloud.baidu.com/doc/qianfan-api",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "ernie-5.0", label: "ERNIE 5.0", capabilities: TVR, context: 128000, note: "flagship"),
        CortexModel(id: "ernie-4.5-turbo-128k", label: "ERNIE 4.5 Turbo 128K", capabilities: T, context: 128000),
        CortexModel(id: "ernie-4.5-vl-424b-a47b", label: "ERNIE 4.5 VL", capabilities: TV, context: 128000, note: "vision"),
      ]),
    CortexProvider(
      id: "volcengine", name: "Volcengine (Doubao)", mode: .cloud, region: .china,
      baseUrl: "https://ark.cn-beijing.volces.com/api/v3", docsUrl: "https://www.volcengine.com/docs/82379",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "doubao-seed-2.1-pro", label: "Doubao Seed 2.1 Pro", capabilities: TV, context: 256000, note: "flagship"),
        CortexModel(id: "doubao-seed-2.1-turbo", label: "Doubao Seed 2.1 Turbo", capabilities: T, context: 256000, note: "cheap"),
        CortexModel(id: "doubao-1.6-vision", label: "Doubao 1.6 Vision", capabilities: TV, context: 256000),
      ],
      note: "ByteDance’s Doubao models via Volcengine Ark."),

    // Global / aggregators
    CortexProvider(
      id: "ollama-cloud", name: "Ollama Cloud", mode: .cloud, region: .global,
      baseUrl: "https://ollama.com/v1", docsUrl: "https://docs.ollama.com/cloud",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "gpt-oss:120b-cloud", label: "GPT-OSS 120B (cloud)", capabilities: TR, context: 128000),
        CortexModel(id: "gpt-oss:20b-cloud", label: "GPT-OSS 20B (cloud)", capabilities: TR, context: 128000),
        CortexModel(id: "qwen3-coder:480b-cloud", label: "Qwen3 Coder 480B (cloud)", capabilities: T, context: 256000, note: "agentic coding"),
        CortexModel(id: "deepseek-v3.1:671b-cloud", label: "DeepSeek V3.1 671B (cloud)", capabilities: TR, context: 128000),
      ],
      note: "Hosted big open models (the `-cloud` tags) — no local GPU needed."),
    CortexProvider(
      id: "openrouter", name: "OpenRouter", mode: .cloud, region: .global,
      baseUrl: "https://openrouter.ai/api/v1", docsUrl: "https://openrouter.ai/models",
      requiresApiKey: true, openAICompatible: true, dynamicModels: true,
      models: [
        CortexModel(id: "anthropic/claude-opus-4.8", label: "Claude Opus 4.8", capabilities: TVR, context: 1000000),
        CortexModel(id: "openai/gpt-5.5", label: "GPT-5.5", capabilities: TVR, context: 1000000),
        CortexModel(id: "google/gemini-3.5-flash", label: "Gemini 3.5 Flash", capabilities: TV, context: 1000000),
        CortexModel(id: "deepseek/deepseek-v4-pro", label: "DeepSeek V4 Pro", capabilities: TR, context: 128000),
        CortexModel(id: "z-ai/glm-5", label: "GLM-5", capabilities: TR, context: 200000),
      ],
      note: "One key routes to 400+ models; any OpenRouter model id works."),
    CortexProvider(
      id: "google", name: "Google (Gemini)", mode: .cloud, region: .global,
      baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
      docsUrl: "https://ai.google.dev/gemini-api/docs/models",
      requiresApiKey: true, openAICompatible: true,
      models: [
        CortexModel(id: "gemini-3.5-flash", label: "Gemini 3.5 Flash", capabilities: TVR, context: 1000000, note: "best value"),
        CortexModel(id: "gemini-3.1-pro", label: "Gemini 3.1 Pro", capabilities: TVR, context: 1000000, note: "strongest"),
        CortexModel(id: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite", capabilities: TV, context: 1000000, note: "cheapest"),
        CortexModel(id: "gemini-2.5-flash", label: "Gemini 2.5 Flash", capabilities: TV, context: 1000000),
      ],
      note: "Gemini via the OpenAI-compatible endpoint."),
    CortexProvider(
      id: "custom", name: "Custom (OpenAI-compatible)", mode: .cloud, region: .global,
      baseUrl: "", docsUrl: "", requiresApiKey: false, openAICompatible: true, dynamicModels: true,
      models: [],
      note: "Point Cortex at any OpenAI-compatible endpoint."),
  ]

  static func provider(_ id: String) -> CortexProvider? { all.first { $0.id == id } }

  static func model(providerId: String, modelId: String) -> CortexModel? {
    provider(providerId)?.models.first { $0.id == modelId }
  }

  struct RegionGroup: Identifiable {
    let region: CortexProviderRegion
    var id: String { region.rawValue }
    var label: String { region.label }
    let providers: [CortexProvider]
  }

  /// Providers grouped by region (empty groups omitted). On macOS we keep both
  /// local and cloud; pass `cloudOnly` for parity with the phone apps.
  static func byRegion(cloudOnly: Bool = false) -> [RegionGroup] {
    CortexProviderRegion.allCases.compactMap { region in
      let ps = all.filter { $0.region == region && (!cloudOnly || $0.mode == .cloud) }
      return ps.isEmpty ? nil : RegionGroup(region: region, providers: ps)
    }
  }
}
