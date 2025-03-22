export interface ExternalIntegration {
  id?: string;
}

export interface PluginReview {
  id?: string;
}

export interface Plugin {
  id: string;
  name: string;
  description: string;
  author: string;
  image: string;
  category: string;
  installs: number;
  rating_avg: number;
  rating_count: number;
  capabilities: Set<string>;
  created_at: string;
}

export interface PluginStat {
  id: string;
  money: number;
}

export interface CapabilityInfo {
  icon: React.ElementType;
  label: string;
  description: string;
}
