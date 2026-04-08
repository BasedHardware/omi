// App Status Types
export type AppStatus = "public" | "private" | "in-review" | "rejected";

export type AppCategory = 
  | "Productivity And Organization"
  | "Communication Improvement"
  | "Education And Learning"
  | "Utilities And Tools"
  | "Entertainment And Fun"
  | "Emotional And Mental Support"
  | "Personality Emulation"
  | "Conversation Analysis";

// App Capabilities with descriptions
export type AppCapability = 
  | "memory"    // Ability to remember and recall past interactions
  | "chat"      // Real-time conversation capabilities
  | "proactive" // Can initiate actions or suggestions without prompting
  | "integration" // Can connect with external services and APIs
  | "persona";    // Can adopt different personalities or roles

// Review Status
export type ReviewStatus = "pending" | "approved" | "rejected";

// Review Data
export interface Review {
  id: string;
  appId: string;
  reviewerId: string;
  status: ReviewStatus;
  comments: string;
  createdAt: string;
  updatedAt: string;
}

// App Data Type
export interface App {
    id: string;
    name: string;
    description?: string;
    author: string;
    category: AppCategory;
    status: AppStatus;
    capabilities: AppCapability[];
    installs: number;
    usage: number;
    earnings: number;
    rating?: number;
    created: string;
    icon?: string;
    review?: Review;
}

// Stats Data Type
export interface DashboardStats {
  totalApps: number;
  approvedApps: number;
  inReviewApps: number;
  paidApps: number;
  publicApps: number;
  privateApps: number;
  earnings: number;
  usage: number;
  installs: number;
  categories: {
    memory: number;
    chat: number;
    proactive: number;
    integration: number;
    persona: number;
  };
}

// Popular App Type
export interface PopularApp {
  id: string;
  name: string;
  description?: string;
  author: string;
  category: AppCategory;
  status: AppStatus;
  capabilities: AppCapability[];
  installs: number;
  usage: number;
  earnings: number;
  rating?: number;
  created: string;
  image?: string;
  icon?: string;
}