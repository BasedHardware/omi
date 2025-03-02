/**
 * @fileoverview Type definitions for subscription-related data
 * @description Contains type interfaces for subscription plans and user subscription status
 */

/**
 * Subscription plan type definition
 * @description Represents a subscription plan with pricing and features
 */
export type SubscriptionPlan = {
  id: string;
  name: string;
  description: string;
  price: number;
  interval: 'month' | 'year';
  features: string[];
  isPopular?: boolean;
  model?: string;
};

/**
 * User subscription type definition
 * @description Represents a user's subscription status
 */
export type UserSubscription = {
  id: string;
  userId: string;
  planId: string;
  status: 'active' | 'canceled' | 'past_due' | 'incomplete';
  currentPeriodStart: number;
  currentPeriodEnd: number;
  cancelAtPeriodEnd: boolean;
  createdAt: number;
  updatedAt: number;
  stripeCustomerId?: string;
  stripeSubscriptionId?: string;
};

/**
 * Subscription feature flags
 * @description Represents features available to different subscription tiers
 */
export type SubscriptionFeatures = {
  advancedModel: boolean;
  maxChatsPerDay: number;
  maxMessagesPerChat: number;
  prioritySupport: boolean;
  offlineAccess: boolean;
}; 