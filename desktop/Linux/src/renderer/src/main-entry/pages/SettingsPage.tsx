import React, { useEffect, useState } from 'react'
import { SectionCard, SettingRow, Toggle } from '../../components/ui'
import { formatBytes } from '../../lib/format'
import { useAuth } from '../../stores/auth'
import { useSettings } from '../../stores/settings'

type Section =
  | 'general'
  | 'device'
  | 'rewind'
  | 'transcription'
  | 'notifications'
  | 'focus'
  | 'proactive'
  | 'voice'
  | 'privacy'
  | 'account'
  | 'plan'
  | 'shortcuts'
  | 'advanced'
  | 'about'

const SECTIONS: { key: Section; label: string }[] = [
  { key: 'general', label: 'General' },
  { key: 'device', label: 'Device' },
  { key: 'rewind', label: 'Rewind' },
  { key: 'transcription', label: 'Transcription' },
  { key: 'notifications', label: 'Notifications' },
  { key: 'focus', label: 'Focus' },
  { key: 'proactive', label: 'Proactive' },
  { key: 'voice', label: 'Voice' },
  { key: 'privacy', label: 'Privacy' },
  { key: 'account', label: 'Account' },
  { key: 'plan', label: 'Plan and Usage' },
  { key: 'shortcuts', label: 'Shortcuts' },
  { key: 'advanced', label: 'Advanced' },
  { key: 'about', label: 'About' }
]

const VOICES = ['marin', 'alloy', 'echo', 'shimmer', 'cedar']
const MODELS = [
  { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 (default)' },
  { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5 (faster)' }
]

const LANGUAGES = ['en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'hi', 'ru', 'uk', 'zh', 'ja', 'ko', 'ar']

export function SettingsPage() {
  const { settings, update } = useSettings()
  const auth = useAuth((s) => s.state)
  const signOut = useAuth((s) => s.signOut)
  const [section, setSection] = useState<Section>('general')
  const [version, setVersion] = useState('')
  const [rewindStats, setRewindStats] = useState<{ frames: number; bytes: number } | null>(null)
  const [capturingHotkey, setCapturingHotkey] = useState(false)
  const [byokMsg, setByokMsg] = useState<string | null>(null)
  // BYOK key fields use a LOCAL draft, not settings[key]: the main process masks the
  // stored keys to '' on every read/write response, so a controlled input bound to
  // settings would clear on each keystroke. Configured status comes from byok.status().
  const [byokDraft, setByokDraft] = useState<Record<string, string>>({})
  const [byokConfigured, setByokConfigured] = useState<Record<string, boolean>>({})

  useEffect(() => {
    void window.omi.system.version().then(setVersion)
    void window.omi.rewind.status().then((s) => setRewindStats(s))
    void window.omi.byok.status().then(setByokConfigured)
  }, [])

  useEffect(() => {
    if (!capturingHotkey) return
    const onKey = (e: KeyboardEvent) => {
      e.preventDefault()
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return
      const parts: string[] = []
      if (e.ctrlKey) parts.push('Control')
      if (e.shiftKey) parts.push('Shift')
      if (e.altKey) parts.push('Alt')
      const key = e.key === ' ' ? 'Space' : e.key.length === 1 ? e.key.toUpperCase() : e.key
      parts.push(key)
      if (parts.length >= 2) {
        void update({ hotkey: parts.join('+') })
        setCapturingHotkey(false)
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [capturingHotkey])

  if (!settings) return null

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <div style={{ width: 260, borderRight: '1px solid var(--border)', padding: '46px 12px 14px', flexShrink: 0 }}>
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '11px 12px',
              borderRadius: 11,
              fontSize: 13.5,
              color: section === s.key ? 'var(--text-primary)' : 'var(--text-tertiary)',
              background: section === s.key ? 'var(--bg-tertiary)' : 'transparent',
              marginBottom: 2
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '46px 26px 26px', minWidth: 0 }}>
        <div className="page-title" style={{ marginBottom: 20, fontSize: 28, fontWeight: 700 }}>
          {SECTIONS.find((s) => s.key === section)?.label}
        </div>

        {section === 'general' && (
          <>
            <SectionCard title="Ask omi Floating Bar">
              <SettingRow label="Keyboard shortcut" description="Summons the floating bar from anywhere">
                <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => setCapturingHotkey(true)}>
                  {capturingHotkey ? 'Press keys…' : settings.hotkey.replace(/Control/g, 'Ctrl')}
                </button>
              </SettingRow>
              <SettingRow label="Show floating bar" description="The always-on-top pill at the top of your screen">
                <Toggle on={settings.floatingBarVisible} onChange={(v) => void update({ floatingBarVisible: v })} />
              </SettingRow>
            </SectionCard>
            <SectionCard title="System">
              <SettingRow label="Launch at login">
                <Toggle on={settings.launchAtLogin} onChange={(v) => void update({ launchAtLogin: v })} />
              </SettingRow>
              <SettingRow label="Font size" description="Scales text across the app">
                <input
                  type="range"
                  min={0.85}
                  max={1.3}
                  step={0.05}
                  value={settings.fontScale}
                  onChange={(e) => void update({ fontScale: parseFloat(e.target.value) })}
                  style={{ width: 130, accentColor: 'var(--purple-primary)', padding: 0, border: 'none', background: 'transparent' }}
                />
              </SettingRow>
            </SectionCard>
          </>
        )}

        {section === 'rewind' && (
          <>
            <SectionCard title="Screen Capture">
              <SettingRow label="Enable Rewind" description="Capture and index your screen so you can search anything you've seen">
                <Toggle on={settings.rewindEnabled} onChange={(v) => void update({ rewindEnabled: v })} />
              </SettingRow>
              <SettingRow label="Capture interval">
                <select
                  value={settings.rewindIntervalMs}
                  onChange={(e) => void update({ rewindIntervalMs: parseInt(e.target.value, 10) })}
                >
                  <option value={2000}>2 seconds</option>
                  <option value={3000}>3 seconds (default)</option>
                  <option value={5000}>5 seconds</option>
                  <option value={10000}>10 seconds</option>
                </select>
              </SettingRow>
              <SettingRow label="Keep history for">
                <select
                  value={settings.retentionDays}
                  onChange={(e) => void update({ retentionDays: parseInt(e.target.value, 10) })}
                >
                  <option value={7}>7 days</option>
                  <option value={30}>30 days</option>
                  <option value={90}>90 days</option>
                  <option value={365}>1 year</option>
                </select>
              </SettingRow>
              <SettingRow
                label="Storage"
                description="Frames and OCR text are stored locally, never uploaded"
              >
                <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)' }}>
                  {rewindStats ? `${rewindStats.frames} frames · ${formatBytes(rewindStats.bytes)}` : ', '}
                </span>
              </SettingRow>
            </SectionCard>
          </>
        )}

        {section === 'proactive' && (
          <SectionCard title="Proactive Assistant">
            <SettingRow
              label="Enable proactive assistant"
              description="Periodically read recent screen activity to extract memories, tasks, and useful nudges"
            >
              <Toggle
                on={settings.proactiveEnabled}
                onChange={(v) => void update({ proactiveEnabled: v, rewindEnabled: v ? true : settings.rewindEnabled })}
              />
            </SettingRow>
            <SettingRow label="Analysis interval">
              <select
                value={settings.proactiveIntervalMs}
                onChange={(e) => void update({ proactiveIntervalMs: parseInt(e.target.value, 10) })}
              >
                <option value={120000}>Every 2 minutes</option>
                <option value={180000}>Every 3 minutes (default)</option>
                <option value={300000}>Every 5 minutes</option>
                <option value={600000}>Every 10 minutes</option>
              </select>
            </SettingRow>
            <SettingRow label="Show insight notifications" description="Surface nudges in the floating bar as they happen">
              <Toggle
                on={settings.proactiveNotifications}
                onChange={(v) => void update({ proactiveNotifications: v })}
              />
            </SettingRow>
            <SettingRow
              label="Privacy"
              description="Screen text stays on this device; only short excerpts are sent to the model for analysis, same as the Mac app"
            >
              <span style={{ fontSize: 12, color: 'var(--text-quaternary)' }}>local-first</span>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'device' && (
          <SectionCard title="Device">
            <SettingRow label="Omi pendant" description="BLE pairing is iOS/macOS-only for now">
              <span style={{ fontSize: 12.5, color: 'var(--text-quaternary)' }}>No device paired</span>
            </SettingRow>
            <SettingRow label="Get an omi device" description="Wearable that captures your day">
              <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => window.omi.system.openExternal('https://www.omi.me')}>
                Learn more
              </button>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'shortcuts' && (
          <SectionCard title="Keyboard Shortcuts">
            <SettingRow label="Ask omi" description="Summon the floating bar from anywhere">
              <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => setCapturingHotkey(true)}>
                {capturingHotkey ? 'Press keys…' : settings.hotkey.replace(/Control/g, 'Ctrl')}
              </button>
            </SettingRow>
            <SettingRow label="Switch pages" description="Jump between sidebar pages">
              <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)' }}>Ctrl + 1…9</span>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'notifications' && (
          <SectionCard title="Notifications">
            <SettingRow label="Proactive insight notifications" description="Surface nudges in the floating bar">
              <Toggle on={settings.proactiveNotifications} onChange={(v) => void update({ proactiveNotifications: v })} />
            </SettingRow>
            <SettingRow label="Focus glow" description="Flash the screen-edge glow on focus changes">
              <Toggle on={settings.focusGlow} onChange={(v) => void update({ focusGlow: v })} />
            </SettingRow>
          </SectionCard>
        )}

        {section === 'privacy' && (
          <SectionCard title="Privacy">
            <SettingRow
              label="Screen capture stays local"
              description="Rewind frames + OCR text are stored only on this device"
            >
              <span style={{ fontSize: 12.5, color: 'var(--success)' }}>on-device</span>
            </SettingRow>
            <SettingRow label="Data retention">
              <select
                value={settings.retentionDays}
                onChange={(e) => void update({ retentionDays: parseInt(e.target.value, 10) })}
              >
                <option value={7}>7 days</option>
                <option value={30}>30 days</option>
                <option value={90}>90 days</option>
                <option value={365}>1 year</option>
              </select>
            </SettingRow>
            <SettingRow label="What we send" description="Only short text excerpts go to the model for analysis">
              <span style={{ fontSize: 12.5, color: 'var(--text-quaternary)' }}>excerpts only</span>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'plan' && (
          <SectionCard title="Plan & Usage">
            <SettingRow label="Current plan" description="Basic includes 1,200 transcription minutes/month">
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{settings.byokActive ? 'BYOK (unlimited)' : 'Basic'}</span>
            </SettingRow>
            <SettingRow label="Upgrade to Unlimited" description="$19/mo or $199/yr, more listening minutes">
              <button className="btn-primary" style={{ fontSize: 12.5 }} onClick={() => window.omi.system.openExternal('https://www.omi.me')}>
                Manage plan
              </button>
            </SettingRow>
            <SettingRow label="Free chat path" description="Bring your own keys to use chat for free (Advanced → BYOK)">
              <span style={{ fontSize: 12.5, color: 'var(--text-quaternary)' }}>see Advanced</span>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'focus' && (
          <SectionCard title="Focus Monitoring">
            <SettingRow label="Enable focus monitoring" description="Detect focused vs distracted screen activity">
              <Toggle
                on={settings.focusEnabled}
                onChange={(v) => void update({ focusEnabled: v, rewindEnabled: v ? true : settings.rewindEnabled })}
              />
            </SettingRow>
            <SettingRow label="Screen-edge glow" description="Flash a green/red glow on focus changes">
              <Toggle on={settings.focusGlow} onChange={(v) => void update({ focusGlow: v })} />
            </SettingRow>
            <SettingRow label="Check interval">
              <select
                value={settings.focusAnalysisDelayMs}
                onChange={(e) => void update({ focusAnalysisDelayMs: parseInt(e.target.value, 10) })}
              >
                <option value={45000}>Every 45 seconds</option>
                <option value={60000}>Every minute (default)</option>
                <option value={120000}>Every 2 minutes</option>
              </select>
            </SettingRow>
            <SettingRow label="Distraction cooldown" description="Don't re-nudge for this long after a distraction glow">
              <select
                value={settings.focusCooldownMs}
                onChange={(e) => void update({ focusCooldownMs: parseInt(e.target.value, 10) })}
              >
                <option value={300000}>5 minutes</option>
                <option value={600000}>10 minutes (default)</option>
                <option value={1200000}>20 minutes</option>
              </select>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'voice' && (
          <>
            <SectionCard title="Realtime Voice">
              <SettingRow label="Provider" description="Used for live voice conversations from the floating bar">
                <select
                  value={settings.realtimeProvider}
                  onChange={(e) => void update({ realtimeProvider: e.target.value as 'auto' | 'gemini' | 'openai' })}
                >
                  <option value="auto">Auto</option>
                  <option value="gemini">Gemini Flash Live</option>
                  <option value="openai">OpenAI Realtime</option>
                </select>
              </SettingRow>
            </SectionCard>
            <SectionCard title="Spoken Replies (TTS)">
              <SettingRow label="Speak assistant replies" description="Read answers aloud in the floating bar">
                <Toggle on={settings.ttsEnabled} onChange={(v) => void update({ ttsEnabled: v })} />
              </SettingRow>
              <SettingRow label="Voice">
                <select value={settings.ttsVoice} onChange={(e) => void update({ ttsVoice: e.target.value })}>
                  {VOICES.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </SettingRow>
            </SectionCard>
          </>
        )}

        {section === 'transcription' && (
          <SectionCard title="Live Transcription">
            <SettingRow label="Language">
              <select
                value={settings.transcriptionLanguage}
                onChange={(e) => void update({ transcriptionLanguage: e.target.value })}
              >
                {LANGUAGES.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </SettingRow>
            <SettingRow label="Custom vocabulary" description="Comma-separated names/terms to bias transcription">
              <input
                placeholder="Omi, Nik, Sakhalin…"
                defaultValue={settings.customVocabulary.join(', ')}
                onBlur={(e) =>
                  void update({
                    customVocabulary: e.target.value
                      .split(',')
                      .map((s) => s.trim())
                      .filter(Boolean)
                  })
                }
                style={{ width: 240 }}
              />
            </SettingRow>
            <SettingRow
              label="System audio"
              description="Default for new recordings, captures meeting audio via PulseAudio loopback"
            >
              <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)' }}>toggle on the Conversations page</span>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'account' && (
          <SectionCard title="Account">
            <SettingRow label="Name">
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{auth?.name || ', '}</span>
            </SettingRow>
            <SettingRow label="Email">
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{auth?.email || ', '}</span>
            </SettingRow>
            <SettingRow label="Plan & usage" description="Subscriptions are managed on omi.me">
              <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => window.omi.system.openExternal('https://www.omi.me')}>
                Manage
              </button>
            </SettingRow>
            <SettingRow label="Sign out of this device">
              <button
                className="btn-secondary"
                style={{ fontSize: 12.5, color: 'var(--error)', borderColor: 'rgba(239,68,68,0.4)' }}
                onClick={signOut}
              >
                Sign Out
              </button>
            </SettingRow>
          </SectionCard>
        )}

        {section === 'advanced' && (
          <>
            <SectionCard title="Bring Your Own Keys">
              {(
                [
                  ['byokAnthropic', 'Anthropic API key'],
                  ['byokOpenAI', 'OpenAI API key'],
                  ['byokGemini', 'Gemini API key'],
                  ['byokDeepgram', 'Deepgram API key']
                ] as const
              ).map(([key, label]) => {
                const provider = key.replace('byok', '').toLowerCase()
                return (
                  <SettingRow key={key} label={label} description="Sent as X-BYOK header, used server-side">
                    <input
                      type="password"
                      placeholder={byokConfigured[provider] ? 'configured' : 'not set'}
                      value={byokDraft[key] ?? ''}
                      onChange={(e) => setByokDraft((d) => ({ ...d, [key]: e.target.value }))}
                      onBlur={() => {
                        const v = (byokDraft[key] ?? '').trim()
                        if (!v) return
                        void update({ [key]: v } as never)
                        setByokDraft((d) => {
                          const next = { ...d }
                          delete next[key]
                          return next
                        })
                        void window.omi.byok.status().then(setByokConfigured)
                      }}
                      style={{ width: 220 }}
                    />
                  </SettingRow>
                )
              })}
              <SettingRow
                label="BYOK free plan"
                description="Enroll your 4 keys to bypass the subscription, you pay the providers directly"
              >
                {settings.byokActive ? (
                  <button
                    className="btn-secondary"
                    style={{ fontSize: 12.5 }}
                    onClick={async () => {
                      await window.omi.byok.deactivate()
                      void useSettings.getState().load()
                    }}
                  >
                    Active, deactivate
                  </button>
                ) : (
                  <button
                    className="btn-primary"
                    style={{ fontSize: 12.5 }}
                    onClick={async () => {
                      setByokMsg('Activating…')
                      const r = await window.omi.byok.activate()
                      if (r.ok) {
                        setByokMsg('Activated, chat is now free (charged to your keys)')
                        void useSettings.getState().load()
                      } else if (r.missing?.length) {
                        setByokMsg(`Missing keys: ${r.missing.join(', ')}`)
                      } else {
                        setByokMsg(r.error || 'Activation failed')
                      }
                    }}
                  >
                    Activate
                  </button>
                )}
              </SettingRow>
              {byokMsg && (
                <div style={{ padding: '8px 16px', fontSize: 12, color: 'var(--text-tertiary)' }}>{byokMsg}</div>
              )}
            </SectionCard>
            <SectionCard title="AI Model">
              <SettingRow label="Chat model" description="Used for the main chat and floating bar">
                <select value={settings.aiModel} onChange={(e) => void update({ aiModel: e.target.value })}>
                  {MODELS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </SettingRow>
            </SectionCard>
            <SectionCard title="Backends">
              <SettingRow
                label="Backend URLs"
                description="Production by default. Override only via the OMI_PYTHON_API_URL / OMI_DESKTOP_API_URL environment variables at launch. URL overrides are kept out of app settings so a compromised page cannot repoint where your credentials are sent."
              >
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>env-var override only</span>
              </SettingRow>
            </SectionCard>
          </>
        )}

        {section === 'about' && (
          <SectionCard title="About omi">
            <SettingRow label="Version">
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{version} (Linux)</span>
            </SettingRow>
            <SettingRow label="Software updates" description="Installed builds update automatically from GitHub releases">
              <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => void window.omi.updater.check()}>
                Check for updates
              </button>
            </SettingRow>
            <SettingRow label="Update channel">
              <select
                value={settings.updateChannel}
                onChange={(e) => void update({ updateChannel: e.target.value as 'stable' | 'beta' })}
              >
                <option value="stable">Stable</option>
                <option value="beta">Beta</option>
              </select>
            </SettingRow>
            <SettingRow label="Website">
              <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => window.omi.system.openExternal('https://www.omi.me')}>
                omi.me
              </button>
            </SettingRow>
            <SettingRow label="Source">
              <button
                className="btn-secondary"
                style={{ fontSize: 12.5 }}
                onClick={() => window.omi.system.openExternal('https://github.com/BasedHardware/omi')}
              >
                github.com/BasedHardware/omi
              </button>
            </SettingRow>
            <SettingRow label="Built with" description="Linux port of the macOS app (desktop/Desktop), same backends and design system">
              <span style={{ fontSize: 12.5, color: 'var(--text-quaternary)' }}>Electron + TypeScript</span>
            </SettingRow>
          </SectionCard>
        )}
      </div>
    </div>
  )
}
