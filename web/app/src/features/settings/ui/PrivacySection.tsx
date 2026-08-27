'use client';

import { Shield, ExternalLink } from 'lucide-react';
import { Toggle, Card, SettingRow } from './settingsPrimitives';

export function PrivacySection({
  recordingPermission,
  trainingDataOptIn,
  onRecordingChange,
  onTrainingDataChange,
}: {
  recordingPermission: boolean;
  trainingDataOptIn: boolean;
  onRecordingChange: (enabled: boolean) => void;
  onTrainingDataChange: (enabled: boolean) => void;
}) {
  return (
    <div className="space-y-6">
      <Card>
        <SettingRow
          label="Store Recordings"
          description="Allow storing audio recordings for improved accuracy"
        >
          <Toggle enabled={recordingPermission} onChange={onRecordingChange} />
        </SettingRow>

        <SettingRow
          label="Training Data"
          description="Help improve Omi by contributing anonymous usage data"
        >
          <Toggle enabled={trainingDataOptIn} onChange={onTrainingDataChange} />
        </SettingRow>
      </Card>

      <Card className="border-white/25">
        <div className="flex items-start gap-4">
          <div className="p-2 rounded-lg bg-white/[0.08]">
            <Shield className="w-5 h-5 text-text-secondary" />
          </div>
          <div>
            <h3 className="text-text-primary font-medium">Your Privacy Matters</h3>
            <p className="text-sm text-text-tertiary mt-1">
              Your data is encrypted and never shared with third parties. You have full
              control over what data is collected and stored.
            </p>
            <a
              href="https://omi.me/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-text-secondary hover:underline mt-2"
            >
              Learn more about our privacy policy
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      </Card>
    </div>
  );
}
