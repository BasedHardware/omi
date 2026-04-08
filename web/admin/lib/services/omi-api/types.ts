// Placeholder types based on common REST patterns for /apps
// Adjust according to the actual Omi API documentation

export type OmiAppStatus = "approved" | "pending" | "rejected" | "under-review" | string; // Add known statuses
export type OmiPaymentPlan = "free" | "one-time" | "monthly" | "yearly" | string; // Example plans

// Based on the provided API response structure
export interface OmiApp {
  id: string;
  name: string;
  uid: string; // User ID of the creator?
  private: boolean;
  approved: boolean;
  status: OmiAppStatus;
  category: string;
  email: string; // Contact email?
  author: string;
  description: string;
  image: string; // URL to main image?
  capabilities: OmiAppCapability[]; // Use the existing capability type
  memory_prompt?: string;
  chat_prompt?: string;
  persona_prompt?: string;
  username?: string; // Associated username?
  // connected_accounts: any[]; // Define more strictly if structure is known
  // twitter: any; // Define more strictly if structure is known
  external_integration?: {
    triggers_on?: string;
    webhook_url?: string;
    setup_completed_url?: string;
    setup_instructions_file_path?: string;
    is_instructions_url?: boolean;
    auth_steps?: any[]; // Define steps structure if known
    app_home_url?: string;
    actions?: any[]; // Define actions structure if known
  };
  // reviews: any[]; // Define review structure if needed
  user_review?: { // Define user review structure if needed
    uid: string;
    rated_at: string; // ISO Date string
    score: number;
    review: string;
    username: string;
    response?: string;
    responded_at?: string; // ISO Date string
  };
  rating_avg: number;
  rating_count: number;
  enabled: boolean;
  deleted: boolean;
  trigger_workflow_memories?: boolean;
  installs: number;
  proactive_notification?: {
    scopes?: string[];
  };
  created_at: string; // ISO Date string (renamed from createdAt)
  is_paid: boolean;
  price: number;
  payment_plan?: OmiPaymentPlan;
  payment_product_id?: string;
  payment_price_id?: string;
  payment_link_id?: string;
  payment_link?: string;
  is_user_paid?: boolean;
  thumbnails?: any[]; // Define thumbnail structure if known
  thumbnail_urls?: string[];
  is_influencer?: boolean;
  is_popular?: boolean;
}

// Update Input type to exclude new read-only/generated fields
// Keep fields that are likely user-settable during creation/update
export type OmiAppInput = Partial<Omit<OmiApp, 
  'id' | 'uid' | 'approved' | 'status' | 'reviews' | 'user_review' | 
  'rating_avg' | 'rating_count' | 'deleted' | 'installs' | 'created_at' | 
  'payment_product_id' | 'payment_price_id' | 'payment_link_id' | 'payment_link' | 
  'is_user_paid' | 'thumbnail_urls' | 'is_popular' | 'is_influencer'
>>;

// Placeholder for capability type - adjust based on actual API spec
export type OmiAppCapability = 
  | 'memories'
  | 'chat'
  | 'proactive_notification'
  | 'external_integration'
  | 'persona'
  | string; // Allow other string values if the API uses them 

// Payout-related types
export interface StripePayout {
  id: string;
  object: 'payout';
  amount: number;
  arrival_date: number;
  automatic: boolean;
  balance_transaction: string;
  created: number;
  currency: string;
  description: string;
  destination: string;
  failure_balance_transaction?: string;
  failure_code?: string;
  failure_message?: string;
  livemode: boolean;
  metadata: Record<string, string>;
  method: string;
  original_payout?: string;
  reversed_by?: string;
  source_type: string;
  statement_descriptor?: string;
  status: 'paid' | 'pending' | 'in_transit' | 'canceled' | 'failed';
  type: 'bank_account' | 'card' | 'fpx';
}

export interface PayoutsResponse {
  payouts: StripePayout[];
  hasMore: boolean;
  totalCount: number;
}

export interface UserWithStripeAccount {
  userId: string;
  stripeAccountId: string;
  appName: string;
  userName: string;
}

export interface PayoutWithAppInfo {
  payout: StripePayout;
  appName: string;
  uid: string; // Changed from userName and userId to just uid
} 