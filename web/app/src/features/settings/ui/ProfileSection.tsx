'use client';

import { useState } from 'react';
import Image from '@tschk/moonshine-next/image';
import { Copy, Check, Plus, X } from 'lucide-react';
import { SUPPORTED_LANGUAGES } from '@/types/user';
import type { DailySummarySettings } from '@/types/user';
import { cn } from '@/lib/utils';
import { Toggle, Card, SettingRow, Dropdown, HourPicker } from './settingsPrimitives';

export function ProfileSection({
  user,
  onCopyUserId,
  language,
  vocabulary,
  onLanguageChange,
  onAddWord,
  onRemoveWord,
  dailySummary,
  onDailySummaryToggle,
  onDailySummaryHourChange,
}: {
  user: any;
  onCopyUserId: () => void;
  language: string;
  vocabulary: string[];
  onLanguageChange: (lang: string) => void;
  onAddWord: (word: string) => void;
  onRemoveWord: (word: string) => void;
  dailySummary: DailySummarySettings;
  onDailySummaryToggle: (enabled: boolean) => void;
  onDailySummaryHourChange: (hour: number) => void;
}) {
  const [copiedUserId, setCopiedUserId] = useState(false);
  const [newWord, setNewWord] = useState('');

  const handleCopy = () => {
    onCopyUserId();
    setCopiedUserId(true);
    setTimeout(() => setCopiedUserId(false), 2000);
  };

  const handleAddWord = () => {
    if (newWord.trim()) {
      onAddWord(newWord.trim());
      setNewWord('');
    }
  };

  const languageOptions = SUPPORTED_LANGUAGES.map((l) => ({
    value: l.code,
    label: l.name,
  }));

  return (
    <div className="space-y-8">
      {/* Account Info */}
      <div id="account-info" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">
          Account
        </h3>
        <Card>
          <div className="flex items-center gap-5">
            <div className="w-20 h-20 rounded-full overflow-hidden bg-bg-tertiary ring-2 ring-white/25 flex-shrink-0">
              {user?.photoURL ? (
                <Image
                  src={user.photoURL}
                  alt={user.displayName || 'User'}
                  width={80}
                  height={80}
                  className="object-cover w-full h-full"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-text-tertiary text-2xl font-medium">
                  {user?.displayName?.charAt(0) || 'U'}
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-text-primary truncate">
                {user?.displayName || 'User'}
              </h3>
              <p className="text-text-tertiary truncate">{user?.email}</p>
            </div>
          </div>
        </Card>

        <Card>
          <SettingRow label="User ID" description="Your unique identifier">
            <div className="flex items-center gap-2">
              <code className="text-sm text-text-tertiary font-mono bg-bg-tertiary px-3 py-1.5 rounded-lg">
                {user?.uid?.slice(0, 8)}...{user?.uid?.slice(-4)}
              </code>
              <button
                onClick={handleCopy}
                className={cn(
                  'p-2 rounded-lg transition-colors',
                  copiedUserId
                    ? 'bg-green-500/10 text-green-400'
                    : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
                )}
              >
                {copiedUserId ? (
                  <Check className="w-4 h-4" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </SettingRow>
        </Card>
      </div>

      {/* Language & Transcription */}
      <div id="language" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">
          Language & Transcription
        </h3>
        <Card>
          <SettingRow
            label="Primary Language"
            description="Default language for transcription"
          >
            <Dropdown
              value={language}
              options={languageOptions}
              onChange={onLanguageChange}
            />
          </SettingRow>
        </Card>
      </div>

      {/* Custom Vocabulary */}
      <div id="vocabulary" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">
          Custom Vocabulary
        </h3>
        <Card>
          <div className="space-y-4">
            <p className="text-sm text-text-tertiary">
              Add words or phrases to improve transcription accuracy
            </p>

            <div className="flex gap-2">
              <input
                type="text"
                value={newWord}
                onChange={(e) => setNewWord(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddWord()}
                placeholder="Enter a word or phrase"
                className={cn(
                  'flex-1 px-4 py-2.5 rounded-xl',
                  'bg-bg-tertiary border border-white/[0.06]',
                  'text-text-primary placeholder:text-text-quaternary',
                  'focus:outline-none focus:border-white/25',
                )}
              />
              <button
                onClick={handleAddWord}
                disabled={!newWord.trim()}
                className={cn(
                  'px-4 py-2.5 rounded-xl font-medium',
                  'bg-text-primary text-bg-primary',
                  'hover:bg-text-primary/90 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <Plus className="w-5 h-5" />
              </button>
            </div>

            {vocabulary.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-2">
                {vocabulary.map((word) => (
                  <span
                    key={word}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bg-tertiary text-text-secondary text-sm"
                  >
                    {word}
                    <button
                      onClick={() => onRemoveWord(word)}
                      className="text-text-quaternary hover:text-red-400 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {vocabulary.length === 0 && (
              <p className="text-sm text-text-quaternary text-center py-4">
                No custom vocabulary added yet
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* Notifications */}
      <div id="notifications" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-medium text-text-tertiary uppercase tracking-wider">
          Notifications
        </h3>
        <Card>
          <SettingRow
            label="Daily Summary"
            description="Receive a daily digest of your action items"
          >
            <Toggle enabled={dailySummary.enabled} onChange={onDailySummaryToggle} />
          </SettingRow>

          {dailySummary.enabled && (
            <SettingRow
              label="Delivery Time"
              description="When to receive your daily summary"
            >
              <HourPicker value={dailySummary.hour} onChange={onDailySummaryHourChange} />
            </SettingRow>
          )}
        </Card>
      </div>
    </div>
  );
}
