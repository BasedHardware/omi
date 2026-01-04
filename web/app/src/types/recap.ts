// Daily Summary / Recap types matching backend API schema (snake_case)

export interface DailySummaryStats {
  total_conversations: number;
  total_duration_minutes: number;
  action_items_count: number;
}

export interface TopicHighlight {
  topic: string;
  emoji: string;
  summary: string;
  conversation_ids: string[];
}

export interface ActionItemSummary {
  description: string;
  priority: 'high' | 'medium' | 'low';
  source_conversation_id: string;
  completed: boolean;
}

export interface UnresolvedQuestion {
  question: string;
  conversation_id: string;
}

export interface DecisionMade {
  decision: string;
  conversation_id: string;
}

export interface KnowledgeNugget {
  insight: string;
  conversation_id: string;
}

export interface LocationPin {
  latitude: number;
  longitude: number;
  address: string;
  time: string;
  conversation_id?: string;
}

export interface DailySummary {
  id: string;
  date: string; // YYYY-MM-DD format
  headline: string;
  day_emoji: string;
  overview: string;
  stats: DailySummaryStats;
  highlights: TopicHighlight[];
  action_items: ActionItemSummary[];
  unresolved_questions: UnresolvedQuestion[];
  decisions_made: DecisionMade[];
  knowledge_nuggets: KnowledgeNugget[];
  locations: LocationPin[];
  created_at: string;
}

// Grouped summaries by month for display
export interface GroupedDailySummaries {
  [monthKey: string]: DailySummary[];
}
