export type ResponseTrends = Trend[];

export interface Trend {
  create_at: Date;
  id: string;
  category: string;
  topics: Topic[];
}

export interface Topic {
  id: string;
  topic: string;
  memories_count: number;
}
