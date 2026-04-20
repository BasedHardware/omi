/**
 * Brain region classifier — maps a memory or insight to one of six anatomical
 * regions so the unified Brain page can render them on top of an SVG brain map.
 *
 * The classifier is deterministic: no async, no network, no ML. It inspects
 * explicit signals first (insight category tags, memory category strings) then
 * falls back to keyword scoring over the content. Keywords cover English and
 * Portuguese because the user writes in both.
 *
 * Regions:
 *   prefrontal  — goals, intentions, plans, decisions
 *   hippocampus — autobiographical events, identity, past experiences (default)
 *   temporal    — people, relationships, names, communication
 *   parietal    — skills, tools, technical know-how, work context
 *   occipital   — things, objects, products, visual assets
 *   cerebellum  — habits, routines, recurring activities
 */

export type BrainRegion =
  | "prefrontal"
  | "hippocampus"
  | "temporal"
  | "parietal"
  | "occipital"
  | "cerebellum";

export const BRAIN_REGIONS: BrainRegion[] = [
  "prefrontal",
  "hippocampus",
  "temporal",
  "parietal",
  "occipital",
  "cerebellum",
];

export interface BrainRegionMeta {
  label: string;
  shortLabel: string;
  description: string;
  color: string;
  icon: string;
}

export const BRAIN_REGION_META: Record<BrainRegion, BrainRegionMeta> = {
  prefrontal: {
    label: "Prefrontal cortex",
    shortLabel: "Intentions",
    description: "Goals, plans, decisions",
    color: "#8B5CF6",
    icon: "Target",
  },
  hippocampus: {
    label: "Hippocampus",
    shortLabel: "Identity",
    description: "Who you are and what you've lived",
    color: "#F59E0B",
    icon: "BookOpen",
  },
  temporal: {
    label: "Temporal lobe",
    shortLabel: "People",
    description: "Relationships and conversations",
    color: "#EC4899",
    icon: "Users",
  },
  parietal: {
    label: "Parietal lobe",
    shortLabel: "Skills",
    description: "Tools and technical know-how",
    color: "#3B82F6",
    icon: "Wrench",
  },
  occipital: {
    label: "Occipital lobe",
    shortLabel: "Things",
    description: "Objects, products, assets",
    color: "#10B981",
    icon: "Boxes",
  },
  cerebellum: {
    label: "Cerebellum",
    shortLabel: "Habits",
    description: "Routines and recurring activities",
    color: "#F97316",
    icon: "Repeat",
  },
};

// ---------------------------------------------------------------------------
// Input shape
// ---------------------------------------------------------------------------

export interface ClassifiableItem {
  content: string;
  category?: string | null;
  structuredCategory?: string | null;
  tags?: string[];
}

// ---------------------------------------------------------------------------
// Explicit category maps
// ---------------------------------------------------------------------------

/**
 * Insight categories (see `insightStore.ts`) map directly to regions.
 * "other" falls through to content-based classification.
 */
const INSIGHT_CATEGORY_TO_REGION: Record<string, BrainRegion> = {
  productivity: "parietal",
  communication: "temporal",
  learning: "prefrontal",
  health: "cerebellum",
};

/**
 * Memory category strings seen in the wild (Omi backend + user-defined).
 * Keys are lowercased.
 */
const MEMORY_CATEGORY_TO_REGION: Record<string, BrainRegion> = {
  // identity / autobiographical
  core: "hippocampus",
  personal: "hippocampus",
  identity: "hippocampus",
  about: "hippocampus",
  bio: "hippocampus",
  life: "hippocampus",
  lifestyle: "hippocampus",
  experience: "hippocampus",
  experiences: "hippocampus",
  memory: "hippocampus",
  memories: "hippocampus",

  // plans / goals
  goal: "prefrontal",
  goals: "prefrontal",
  plan: "prefrontal",
  plans: "prefrontal",
  intention: "prefrontal",
  intentions: "prefrontal",
  decision: "prefrontal",
  decisions: "prefrontal",
  task: "prefrontal",
  tasks: "prefrontal",
  todo: "prefrontal",
  learning: "prefrontal",

  // relationships / people
  people: "temporal",
  person: "temporal",
  relationship: "temporal",
  relationships: "temporal",
  family: "temporal",
  friend: "temporal",
  friends: "temporal",
  social: "temporal",
  communication: "temporal",
  conversation: "temporal",
  contact: "temporal",
  contacts: "temporal",

  // skills / work / tools
  work: "parietal",
  job: "parietal",
  career: "parietal",
  skill: "parietal",
  skills: "parietal",
  tool: "parietal",
  tools: "parietal",
  tech: "parietal",
  technology: "parietal",
  technical: "parietal",
  education: "parietal",
  productivity: "parietal",
  profession: "parietal",
  professional: "parietal",

  // things / products / places
  thing: "occipital",
  things: "occipital",
  object: "occipital",
  objects: "occipital",
  product: "occipital",
  products: "occipital",
  possession: "occipital",
  possessions: "occipital",
  asset: "occipital",
  assets: "occipital",
  place: "occipital",
  places: "occipital",

  // habits
  habit: "cerebellum",
  habits: "cerebellum",
  routine: "cerebellum",
  routines: "cerebellum",
  health: "cerebellum",
  fitness: "cerebellum",
  exercise: "cerebellum",
  hobby: "cerebellum",
  hobbies: "cerebellum",
};

// ---------------------------------------------------------------------------
// Keyword dictionary — content-level fallback
// ---------------------------------------------------------------------------

/**
 * Per-region keyword lists. Matches use whole-word boundaries against a
 * lowercased, diacritic-stripped copy of the content. English + Portuguese.
 */
const REGION_KEYWORDS: Record<BrainRegion, string[]> = {
  prefrontal: [
    // english — plans, goals, decisions, intent
    "plan", "plans", "planning", "planned",
    "goal", "goals",
    "intend", "intends", "intention", "intent",
    "decide", "decides", "decided", "decision",
    "aim", "aims", "aiming",
    "target", "targets", "targeting",
    "wants to", "want to", "wanted to",
    "going to", "gonna",
    "launch", "release", "releases", "roadmap",
    "todo", "to-do", "to do",
    "objective", "objectives",
    "milestone", "milestones",
    "strategy", "strategic",
    "priority", "priorities",
    "schedule", "scheduled", "scheduling",
    "deadline", "deadlines",
    "future", "upcoming",
    "learn", "learns", "learning", "study", "studying",
    // portuguese
    "planeja", "planejar", "planejamento", "plano",
    "meta", "metas", "objetivo", "objetivos",
    "pretende", "pretender", "pretendo",
    "decidir", "decidiu", "decisao",
    "prazo", "prazos",
    "futuro", "proximo", "proxima",
    "estudar", "estudando", "aprender", "aprendendo",
  ],
  hippocampus: [
    // english — identity, biography, past
    "i am", "i'm", "was born", "born in", "born on",
    "grew up", "lived", "lives in", "live in", "used to",
    "background", "childhood", "when i was",
    "years old", "year old",
    "remember", "remembered", "remembering",
    "history", "past",
    "life story", "biography",
    "identity", "who i am",
    "my name", "named",
    "birthday", "anniversary",
    "married", "divorced", "single",
    "originally from", "moved to",
    "graduated", "degree", "university", "college",
    // portuguese
    "eu sou", "nasci", "nasceu", "cresceu",
    "cresci", "morava", "morou", "morei", "mora em", "moro em",
    "infancia", "quando era",
    "anos de idade", "anos atras",
    "lembro", "lembrar", "lembrou", "lembrava",
    "historia", "passado",
    "casado", "casada", "solteiro", "solteira", "divorciado",
    "formou", "formado", "graduou", "universidade", "faculdade",
  ],
  temporal: [
    // english — people, names, social, comms
    "met with", "meeting with", "talked to", "talking to",
    "spoke with", "spoke to", "speaking with",
    "called", "calling", "texted", "messaged",
    "emailed", "email from", "email to",
    "conversation", "conversations", "chat", "chatted",
    "friend", "friends", "friendship",
    "family", "parents", "mother", "father", "mom", "dad",
    "brother", "sister", "sibling", "cousin",
    "wife", "husband", "partner", "boyfriend", "girlfriend",
    "son", "daughter", "kids", "children",
    "teammate", "coworker", "colleague",
    "boss", "manager", "client", "customer",
    "neighbor", "roommate",
    "relationship", "relationships",
    "people", "person",
    "praised", "complimented", "thanked",
    "introduced", "introducing",
    // portuguese
    "encontrou", "encontrei", "conversou", "conversei", "conversa",
    "falou com", "falei com", "falando com",
    "ligou", "mandou mensagem",
    "amigo", "amiga", "amigos", "amigas", "amizade",
    "familia", "mae", "pai", "irmao", "irma",
    "esposa", "marido", "namorado", "namorada",
    "filho", "filha", "filhos", "filhas",
    "colega", "colegas", "chefe", "cliente",
    "vizinho", "vizinha",
    "elogiou", "elogiado", "agradeceu",
    "pessoa", "pessoas", "gente",
  ],
  parietal: [
    // english — skills, tools, tech, work
    "uses", "using", "utilize", "utilizes", "utilizing",
    "prefers", "favors",
    "values", "believes in",
    "workflow",
    "skill", "skills", "skilled",
    "experienced in", "expert in", "proficient",
    "developer", "engineer", "programmer",
    "software", "hardware", "firmware",
    "code", "coding", "codebase",
    "debug", "debugging", "debugger", "breakpoint", "breakpoints",
    "api", "sdk", "framework", "library", "libraries",
    "database", "backend", "frontend", "fullstack",
    "server", "deploy", "deployment", "pipeline",
    "monitoring", "observability", "sentry", "datadog", "grafana",
    "javascript", "typescript", "python", "rust", "swift", "kotlin",
    "react", "vue", "angular", "tauri", "flutter",
    "git", "github", "gitlab",
    "aws", "gcp", "azure",
    "docker", "kubernetes",
    "terminal", "cli",
    "standup",
    "testing", "unit test", "integration test",
    "method", "methodology", "technique",
    // portuguese
    "usa", "usando", "utiliza", "utilizando",
    "prefere", "valoriza", "acredita em",
    "desenvolvedor", "engenheiro", "programador",
    "programando", "codigo", "codificacao",
    "depuracao", "depurador",
    "servidor", "implantacao",
    "testes", "teste unitario",
    "habilidade", "habilidades", "especialista",
    "ferramenta", "ferramentas",
  ],
  occipital: [
    // english — things, products, objects
    "owns", "has a", "has an", "has the",
    "bought", "purchased", "ordered",
    "product", "products",
    "device", "devices", "gadget",
    "phone", "iphone", "android",
    "laptop", "macbook", "computer",
    "gpu", "cpu", "monitor", "keyboard", "mouse",
    "headphones", "earbuds", "speakers",
    "car", "vehicle", "bike", "bicycle",
    "house", "home", "apartment", "flat",
    "subscription", "subscribed",
    "account", "accounts", "billing",
    "maps", "google maps", "apple maps",
    "app", "application",
    "gear",
    // portuguese
    "possui", "tem um", "tem uma", "tem o", "tem a",
    "comprou", "comprei", "adquiriu",
    "produto", "produtos",
    "dispositivo", "aparelho",
    "celular", "telefone",
    "notebook", "computador",
    "carro", "veiculo", "bicicleta",
    "casa", "apartamento",
    "assinatura", "assinou",
    "conta", "faturamento", "cobranca",
    "aplicativo", "aplicativos",
  ],
  cerebellum: [
    // english — habits, routines, recurring
    "daily", "every day", "each day",
    "weekly", "every week", "each week",
    "monthly", "every month",
    "regularly", "routinely", "habitually",
    "habit", "habits", "routine", "routines",
    "always", "often", "usually",
    "morning routine", "evening routine", "night routine",
    "workout", "workouts", "exercise", "exercising",
    "gym", "run", "running", "jog", "jogging",
    "yoga", "meditation", "meditate", "meditating",
    "reads daily", "reads weekly",
    "practice", "practices", "practicing",
    "ritual", "rituals",
    "recurring", "recurrent",
    "bedtime", "sleep schedule",
    "diet", "eating habits",
    // portuguese
    "diariamente", "todo dia", "todos os dias",
    "semanalmente", "toda semana",
    "mensalmente", "todo mes",
    "regularmente", "rotineiramente",
    "habito", "habitos", "rotina", "rotinas",
    "sempre", "geralmente", "costuma",
    "treino", "treinos", "exercicio", "exercicios",
    "academia", "corrida", "correr",
    "meditacao", "meditar",
    "pratica", "praticando",
    "ritual", "rituais",
  ],
};

// ---------------------------------------------------------------------------
// Matching helpers
// ---------------------------------------------------------------------------

/** Strip diacritics so "habito" matches "hábito" and vice versa. */
function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function tagsFromItem(item: ClassifiableItem): string[] {
  if (!item.tags) return [];
  return item.tags.filter((t): t is string => typeof t === "string");
}

function classifyByInsightCategory(
  tags: string[],
  category: string | null | undefined,
): BrainRegion | null {
  const isInsight = tags.some((t) => t.toLowerCase() === "tips");
  if (!isInsight) return null;

  // Look for an insight category in the tags
  for (const t of tags) {
    const lower = t.toLowerCase();
    if (lower === "tips") continue;
    const mapped = INSIGHT_CATEGORY_TO_REGION[lower];
    if (mapped) return mapped;
    if (lower === "other") return null; // fall through
  }

  // Fallback to the category field for insights without a category tag
  if (category) {
    const mapped = INSIGHT_CATEGORY_TO_REGION[category.toLowerCase()];
    if (mapped) return mapped;
  }

  return null;
}

function classifyByCategory(
  category: string | null | undefined,
  structuredCategory: string | null | undefined,
  tags: string[],
): BrainRegion | null {
  const candidates: string[] = [];
  if (structuredCategory) candidates.push(structuredCategory);
  if (category) candidates.push(category);
  for (const t of tags) {
    if (t && t.toLowerCase() !== "tips") candidates.push(t);
  }

  for (const raw of candidates) {
    const key = raw.toLowerCase().trim();
    if (!key) continue;
    const mapped = MEMORY_CATEGORY_TO_REGION[key];
    if (mapped) return mapped;
  }
  return null;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function classifyByKeywords(content: string): BrainRegion | null {
  const normalized = normalize(content);
  if (!normalized) return null;

  const scores: Record<BrainRegion, number> = {
    prefrontal: 0,
    hippocampus: 0,
    temporal: 0,
    parietal: 0,
    occipital: 0,
    cerebellum: 0,
  };

  for (const region of BRAIN_REGIONS) {
    const keywords = REGION_KEYWORDS[region];
    for (const kw of keywords) {
      const needle = normalize(kw);
      if (!needle) continue;
      // multi-word phrases: substring check (phrases are strong signals, weight 2)
      if (needle.includes(" ")) {
        if (normalized.includes(needle)) scores[region] += 2;
        continue;
      }
      // single words: whole-word boundary check
      const pattern = new RegExp(
        `(^|[^a-z0-9])${escapeRegex(needle)}([^a-z0-9]|$)`,
      );
      if (pattern.test(normalized)) scores[region] += 1;
    }
  }

  let best: BrainRegion | null = null;
  let bestScore = 0;
  for (const region of BRAIN_REGIONS) {
    if (scores[region] > bestScore) {
      bestScore = scores[region];
      best = region;
    }
  }
  return bestScore > 0 ? best : null;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function classifyRegion(item: ClassifiableItem): BrainRegion {
  const tags = tagsFromItem(item);

  // 1. Insight-aware: tips + known category → region
  const insightRegion = classifyByInsightCategory(tags, item.category);
  if (insightRegion) return insightRegion;

  // 2. Explicit category/tag signals on regular memories
  const categoryRegion = classifyByCategory(
    item.category ?? null,
    item.structuredCategory ?? null,
    tags,
  );
  if (categoryRegion) return categoryRegion;

  // 3. Keyword scoring over content
  const keywordRegion = classifyByKeywords(item.content ?? "");
  if (keywordRegion) return keywordRegion;

  // 4. Fallback — autobiographical default
  return "hippocampus";
}

export function countByRegion(
  items: ClassifiableItem[],
): Record<BrainRegion, number> {
  const counts: Record<BrainRegion, number> = {
    prefrontal: 0,
    hippocampus: 0,
    temporal: 0,
    parietal: 0,
    occipital: 0,
    cerebellum: 0,
  };
  for (const item of items) {
    counts[classifyRegion(item)] += 1;
  }
  return counts;
}

export function filterByRegion<T extends ClassifiableItem>(
  items: T[],
  region: BrainRegion | null,
): T[] {
  if (region === null) return items;
  return items.filter((item) => classifyRegion(item) === region);
}
