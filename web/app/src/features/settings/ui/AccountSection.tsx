'use client';

import Link from '@tschk/moonshine-next/link';
import { LogOut, Trash2, ExternalLink, Scale, ChevronRight } from 'lucide-react';
import type { AllUsageData, UserSubscription, PricingOption } from '@/types/user';
import { Card } from './settingsPrimitives';
import { UsageSectionContent } from './UsageSection';

export function AccountSection({
  allUsage,
  subscription,
  cachedPlans,
  onSubscriptionUpdate,
  onSignOut,
  onDeleteAccount,
}: {
  allUsage: AllUsageData | null;
  subscription: UserSubscription | null;
  cachedPlans: PricingOption[] | null;
  onSubscriptionUpdate: () => void;
  onSignOut: () => void;
  onDeleteAccount: () => void;
}) {
  return (
    <div className="space-y-8">
      {/* Plan & Usage */}
      <div id="plan-usage" className="scroll-mt-4">
        <UsageSectionContent
          allUsage={allUsage}
          subscription={subscription}
          onSubscriptionUpdate={onSubscriptionUpdate}
          cachedPlans={cachedPlans}
        />
      </div>

      {/* Fair Use */}
      <div id="fair-use" className="scroll-mt-4">
        <Card>
          <Link
            href="/fair-use"
            className="flex items-center justify-between py-2 text-text-primary hover:text-text-secondary transition-colors"
          >
            <div className="flex items-center gap-3">
              <Scale className="w-5 h-5 text-text-tertiary" />
              <div>
                <span className="font-medium">Fair Use</span>
                <p className="text-sm text-text-quaternary">
                  View speech usage and policy status
                </p>
              </div>
            </div>
            <ChevronRight className="w-4 h-4 text-text-quaternary" />
          </Link>
        </Card>
      </div>

      {/* Account Actions */}
      <div id="actions" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">
          Account Actions
        </h3>
        <Card>
          <button
            onClick={onSignOut}
            className="w-full flex items-center gap-3 py-3 text-text-primary hover:text-text-secondary transition-colors"
          >
            <LogOut className="w-5 h-5" />
            <span className="font-medium">Sign Out</span>
          </button>
        </Card>

        <Card className="border-red-500/20">
          <button
            onClick={onDeleteAccount}
            className="w-full flex items-center gap-3 py-3 text-red-400 hover:text-red-300 transition-colors"
          >
            <Trash2 className="w-5 h-5" />
            <div className="text-left">
              <span className="font-medium block">Delete Account</span>
              <span className="text-sm text-red-400/70">
                Permanently delete your account and all data
              </span>
            </div>
          </button>
        </Card>
      </div>

      {/* Support */}
      <div id="support" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">
          Support
        </h3>
        <Card>
          <a
            href="https://feedback.omi.me"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between py-3 border-b border-white/[0.06] text-text-primary hover:text-text-secondary transition-colors"
          >
            <span>Feedback & Bug Reports</span>
            <ExternalLink className="w-4 h-4" />
          </a>
          <a
            href="https://help.omi.me"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between py-3 text-text-primary hover:text-text-secondary transition-colors"
          >
            <span>Help Center</span>
            <ExternalLink className="w-4 h-4" />
          </a>
        </Card>
      </div>
    </div>
  );
}
