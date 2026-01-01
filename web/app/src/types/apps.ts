// App Types for the Omi Web App

export interface AppReview {
  uid: string;
  rated_at: string;
  score: number;
  review: string;
  username?: string;
  response?: string;
  responded_at?: string;
}

export interface AuthStep {
  name: string;
  url: string;
}

export interface ExternalIntegration {
  triggers_on?: string;
  webhook_url?: string;
  setup_completed_url?: string;
  setup_instructions_file_path?: string;
  is_instructions_url?: boolean;
  auth_steps?: AuthStep[];
  app_home_url?: string;
}

export interface ChatTool {
  name: string;
  description: string;
  endpoint: string;
  method?: string;
  parameters?: Record<string, unknown>;
  auth_required?: boolean;
  status_message?: string;
}

export interface App {
  id: string;
  name: string;
  description: string;
  image?: string;
  author?: string;
  email?: string;
  uid?: string;
  category: string;
  capabilities: string[];
  enabled: boolean;
  deleted?: boolean;
  private?: boolean;
  approved?: boolean;
  status?: string;
  installs?: number;
  rating_avg?: number;
  rating_count?: number;
  reviews?: AppReview[];
  user_review?: AppReview;
  memory_prompt?: string;
  chat_prompt?: string;
  persona_prompt?: string;
  external_integration?: ExternalIntegration;
  chat_tools?: ChatTool[];
  thumbnails?: string[];
  thumbnail_urls?: string[];
  is_paid?: boolean;
  price?: number;
  payment_plan?: string;
  payment_link?: string;
  is_user_paid?: boolean;
  is_popular?: boolean;
  created_at?: string;
}

export interface AppCategory {
  id: string;
  title: string;
}

export interface AppCapability {
  id: string;
  title: string;
  triggers?: { id: string; title: string }[];
}

export interface AppsGroupedResponse {
  groups: AppGroup[];
  meta: {
    capabilities: AppCapability[];
    groupCount: number;
    limit: number;
    offset: number;
  };
}

export interface AppGroup {
  capability?: {
    id: string;
    title: string;
  };
  category?: {
    id: string;
    title: string;
  };
  data: App[];
  pagination?: {
    total?: number;
    count?: number;
    offset?: number;
    limit?: number;
  };
}

export interface AppsSearchResponse {
  data: App[];
  pagination: {
    total: number;
    offset: number;
    limit: number;
    hasMore: boolean;
  };
  filters: {
    query?: string;
    category?: string;
    rating?: number;
    capability?: string;
    sort?: string;
    my_apps?: boolean;
    installed_apps?: boolean;
  };
}

export interface AppsSearchParams {
  q?: string;
  category?: string;
  rating?: number;
  capability?: string;
  sort?: 'installs_desc' | 'rating_desc' | 'rating_asc' | 'name_asc' | 'name_desc';
  my_apps?: boolean;
  installed_apps?: boolean;
  offset?: number;
  limit?: number;
}

// Filter types for the UI
export type SortOption =
  | 'installs_desc'
  | 'rating_desc'
  | 'rating_asc'
  | 'name_asc'
  | 'name_desc';

export interface AppsFilters {
  category?: string;
  capability?: string;
  rating?: number;
  sort?: SortOption;
  installed?: boolean;
}

// ============================================================================
// App Creation/Editing Types
// ============================================================================

export interface ExternalIntegrationTrigger {
  id: string;
  title: string;
}

export interface NotificationScope {
  id: string;
  title: string;
}

export interface PaymentPlan {
  id: string;
  title: string;
}

export interface AppFormData {
  // Metadata
  name: string;
  description: string;
  category: string;

  // Capabilities
  capabilities: string[];

  // Prompts (conditional based on capabilities)
  chatPrompt?: string;
  memoryPrompt?: string;
  personaPrompt?: string;

  // External integration (conditional)
  externalIntegration?: {
    triggerEvent?: string;
    webhookUrl?: string;
    setupCompletedUrl?: string;
    setupInstructionsFilePath?: string;
    isInstructionsUrl?: boolean;
    appHomeUrl?: string;
    authSteps?: AuthStep[];
  };

  // Notification scopes (conditional)
  notificationScopes?: string[];

  // Privacy & Payment
  isPrivate: boolean;
  isPaid: boolean;
  price?: number;
  paymentPlan?: string;
}

export interface CreateAppRequest {
  name: string;
  description: string;
  category: string;
  capabilities: string[];
  private: boolean;
  is_paid?: boolean;
  price?: number;
  payment_plan?: string;
  chat_prompt?: string;
  memory_prompt?: string;
  persona_prompt?: string;
  external_integration?: {
    triggers_on?: string;
    webhook_url?: string;
    setup_completed_url?: string;
    setup_instructions_file_path?: string;
    is_instructions_url?: boolean;
    app_home_url?: string;
    auth_steps?: AuthStep[];
  };
  proactive_notification_scopes?: string[];
}

export interface UpdateAppRequest extends Partial<CreateAppRequest> {
  id: string;
}

export interface ThumbnailUploadResponse {
  thumbnail_url: string;
  thumbnail_id: string;
}

export interface GenerateDescriptionResponse {
  description: string;
}

export interface AppApiKey {
  id: string;
  key?: string; // Only returned on creation
  created_at: string;
}
