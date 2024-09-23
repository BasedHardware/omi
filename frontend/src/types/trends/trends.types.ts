export interface Trends {
  created_at: Date;
  type: string;
  id: string;
  category: string;
  topics: Topic[];
}

export interface Topic {
  topic: string;
  id: string;
  memories_count: number;
}
