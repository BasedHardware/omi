import { useState, useEffect } from 'react'
import { MessagesSquare, Mic, Volume2, Bot, FileText, Bluetooth, BluetoothConnected } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { speak, stop as stopTTS } from '../../../lib/ttsService'
import { startAgent, stopAgent } from '../../../lib/deepgramAgentClient'
import { extractSummary, type SummaryResult } from '../../../lib/summaryClient'
import { liveConversation } from '../../../lib/liveConversation'
import { omiApi } from '../../../lib/apiClient'
import { omiBleClient, type OmiDeviceState, type OmiDeviceInfo } from '../../../lib/omiBleClient'
import type { AgentConfig } from '../../../../../shared/types'
import {
  getMonologurSettings,
  saveMonologurSettings,
  startMonologur,
  stopMonologur
} from '../../../lib/monologurEngine'
import { clearVoiceprint, isEnrolled } from '../../../lib/voiceprint'

function loadAgentSettings(): AgentConfig {
  try {
    const stored = localStorage.getItem('agent-settings-v1')
    if (stored) return JSON.parse(stored)
  } catch { /* ignore */ }
  return {}
}

function saveAgentSettings(config: AgentConfig): void {
  localStorage.setItem('agent-settings-v1', JSON.stringify(config))
}

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [monologurEnabled, setMonologurEnabled] = useState(() => getMonologurSettings().enabled)
  const [ttsProvider, setTtsProvider] = useState<'web' | 'deepgram'>(() => getMonologurSettings().ttsProvider)
  const [voiceEnrolled, setVoiceEnrolled] = useState(() => isEnrolled())
  const [agentActive, setAgentActive] = useState(false)
  const [summaryResult, setSummaryResult] = useState<SummaryResult | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)

  const [agentName, setAgentName] = useState(() => loadAgentSettings().agentName || 'friend')
  const [personality, setPersonality] = useState(() => loadAgentSettings().personality || 'warm, curious, and helpful')
  const [activationMode, setActivationMode] = useState<'wake-word' | 'always'>(() => loadAgentSettings().activationMode || 'wake-word')
  const [clarificationEnabled, setClarificationEnabled] = useState(() => loadAgentSettings().clarificationEnabled !== false)
  const [llmProvider, setLlmProvider] = useState<'deepgram' | 'openai' | 'ollama'>(() => loadAgentSettings().llmProvider || 'deepgram')
  const [llmModel, setLlmModel] = useState(() => loadAgentSettings().llmModel || '')
  const [llmBaseUrl] = useState(() => loadAgentSettings().llmBaseUrl || 'http://localhost:11434/v1')
  const [ollamaStatus, setOllamaStatus] = useState<{ checked: boolean; ok: boolean; models: string[] }>({ checked: false, ok: false, models: [] })
  const [deviceState, setDeviceState] = useState<OmiDeviceState>('disconnected')
  const [deviceInfo, setDeviceInfo] = useState<OmiDeviceInfo | null>(null)
  const [deviceBattery, setDeviceBattery] = useState<number | null>(null)

  useEffect(() => {
    const unsub = omiBleClient.on({
      onStateChange: (s) => setDeviceState(s),
      onDeviceInfo: (info) => setDeviceInfo(info),
      onBatteryLevel: (b) => setDeviceBattery(b)
    })
    return unsub
  }, [])

  return (
    <>
      <SettingRow
        icon={MessagesSquare}
        title="Chat history"
        subtitle="By default, one ongoing conversation (shared with the floating bar) that persists across launches — scroll up in chat to load older messages. Or start a fresh conversation each launch."
        keywords="conversation thread floating bar history infinite"
        control={
          <select
            value={chatHistoryMode}
            onChange={(e) => {
              const v = e.target.value as 'per-launch' | 'infinite'
              setChatHistoryMode(v)
              setPreferences({ chatHistoryMode: v })
            }}
            className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
          >
            <option value="infinite" className="bg-neutral-900">
              One ongoing conversation (default)
            </option>
            <option value="per-launch" className="bg-neutral-900">
              New conversation each launch
            </option>
          </select>
        }
      />

      <SettingRow
        icon={Mic}
        title="Monologur"
        subtitle="Always-listening AI assistant that provides real-time guidance and suggestions via text-to-speech based on your ongoing conversations."
        keywords="monologur always listening tts speech proactive"
        control={
          <div className="flex items-center gap-2">
            <select
              value={ttsProvider}
              onChange={(e) => {
                const v = e.target.value as 'web' | 'deepgram'
                setTtsProvider(v)
                saveMonologurSettings({ ttsProvider: v })
              }}
              className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
            >
              <option value="web" className="bg-neutral-900">
                Web TTS
              </option>
              <option value="deepgram" className="bg-neutral-900">
                Deepgram Aura
              </option>
            </select>
            <button
              onClick={() => {
                const newValue = !monologurEnabled
                setMonologurEnabled(newValue)
                saveMonologurSettings({ enabled: newValue })
                if (newValue) {
                  startMonologur()
                } else {
                  stopMonologur()
                }
              }}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                monologurEnabled
                  ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                  : 'bg-white/10 text-white/60 hover:bg-white/20'
              }`}
            >
              {monologurEnabled ? 'Enabled' : 'Disabled'}
            </button>
          </div>
        }
      />

      <SettingRow
        icon={Mic}
        title="Voice Identity"
        subtitle={
          voiceEnrolled
            ? 'Your voice is enrolled. Omi labels your speech as "You" and others as "Other". Say something to re-confirm, or re-enroll.'
            : 'Not enrolled yet — the next voice Omi hears will be registered as you. Talk for a few seconds after saving, or re-enroll below.'
        }
        keywords="voiceprint speaker identity diarization me you"
        control={
          <button
            onClick={() => {
              clearVoiceprint()
              setVoiceEnrolled(false)
            }}
            className="rounded-md bg-white/10 px-3 py-1.5 text-sm font-medium text-white/70 transition-colors hover:bg-white/20"
          >
            {voiceEnrolled ? 'Re-enroll' : 'Clear'}
          </button>
        }
      />

      <SettingRow
        icon={Volume2}
        title="Test TTS"
        subtitle="Speak a sample sentence to verify text-to-speech is working."
        keywords="tts test speech speak audio"
        control={
          <button
            onClick={() => {
              stopTTS()
              speak(
                'Hello! This is a test of the text to speech system. The weather today is sunny with a high of twenty five degrees.',
                { enabled: true, rate: 1.0, pitch: 1.0, volume: 1.0, voiceName: null },
                { onEnd: () => console.log('[tts] test complete') }
              )
            }}
            className="rounded-md bg-blue-500/20 px-3 py-1.5 text-sm font-medium text-blue-400 hover:bg-blue-500/30"
          >
            Speak Test
          </button>
        }
      />

      <SettingRow
        icon={Bot}
        title="Voice Agent"
        subtitle="Full voice pipeline with personality. Speak to the mic and the AI responds with voice."
        keywords="voice agent deepgram stt tts llm conversation personality"
        control={
          <div className="flex flex-col items-end gap-2">
            <div className="flex gap-2">
              <input
                type="text"
                value={agentName}
                onChange={(e) => {
                  setAgentName(e.target.value)
                  saveAgentSettings({ agentName: e.target.value, personality, activationMode, clarificationEnabled, llmProvider, llmModel, llmBaseUrl })
                }}
                placeholder="Agent name"
                className="w-24 rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
              />
              <button
                onClick={async () => {
                  if (agentActive) {
                    stopAgent()
                    setAgentActive(false)
                  } else {
                    // Load memories before starting agent
                    const loadMemories = async (): Promise<Array<{ content: string; category?: string }>> => {
                      try {
                        const r = await omiApi.get('/v3/memories', { params: { limit: 20, offset: 0 } })
                        const data = r.data as { memories?: Array<{ content: string; category?: string }> } | Array<{ content: string; category?: string }>
                        const memories = Array.isArray(data) ? data : (data.memories ?? [])
                        return memories.map((m) => ({ content: m.content, category: m.category }))
                      } catch {
                        return []
                      }
                    }
                    const memories = await loadMemories()
                    const config: AgentConfig = {
                      agentName,
                      personality,
                      activationMode,
                      clarificationEnabled,
                      ttsVoice: 'aura-2-thalia-en',
                      memories,
                      llmProvider,
                      llmModel: llmModel || undefined,
                      llmBaseUrl: llmBaseUrl || undefined
                    }
                    // Use Omi device as audio source if connected, otherwise mic
                    const audioSource = deviceState === 'connected' ? 'omi-device' : 'mic'
                    startAgent(config, {
                      onConnected: () => console.log('[voice-agent] connected'),
                      onUserText: (t) => console.log('[voice-agent] user:', t),
                      onAgentText: (t) => console.log('[voice-agent] agent:', t),
                      onClosed: () => setAgentActive(false),
                      onError: (e) => { console.error('[voice-agent] error:', e); setAgentActive(false) }
                    }, audioSource)
                    setAgentActive(true)
                  }
                }}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  agentActive
                    ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                    : 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                }`}
              >
                {agentActive ? 'Stop' : 'Start'}
              </button>
            </div>
            <div className="flex gap-2 text-xs">
              <select
                value={activationMode}
                onChange={(e) => {
                  const v = e.target.value as 'wake-word' | 'always'
                  setActivationMode(v)
                  saveAgentSettings({ agentName, personality, activationMode: v, clarificationEnabled, llmProvider, llmModel, llmBaseUrl })
                }}
                className="rounded-md bg-white/10 px-2 py-1 text-white focus:outline-none"
              >
                <option value="wake-word" className="bg-neutral-900">Say "{agentName}" to activate</option>
                <option value="always" className="bg-neutral-900">Always respond</option>
              </select>
              <select
                value={activationMode}
                onChange={(e) => {
                  const v = e.target.value as 'wake-word' | 'always'
                  setActivationMode(v)
                  saveAgentSettings({ agentName, personality, activationMode: v, clarificationEnabled, llmProvider, llmModel, llmBaseUrl })
                }}
                className="rounded-md bg-white/10 px-2 py-1 text-white focus:outline-none"
              >
                <option value="wake-word" className="bg-neutral-900">Say "{agentName}" to activate</option>
                <option value="always" className="bg-neutral-900">Always respond</option>
              </select>
              <select
                value={loadAgentSettings().language || 'en'}
                onChange={(e) => {
                  const v = e.target.value
                  saveAgentSettings({ ...loadAgentSettings(), language: v })
                }}
                className="rounded-md bg-white/10 px-2 py-1 text-white focus:outline-none"
              >
                <option value="en" className="bg-neutral-900">English</option>
                <option value="es" className="bg-neutral-900">Español</option>
                <option value="fr" className="bg-neutral-900">Français</option>
                <option value="de" className="bg-neutral-900">Deutsch</option>
                <option value="zh" className="bg-neutral-900">中文</option>
                <option value="ja" className="bg-neutral-900">日本語</option>
              </select>
              <div className="flex items-center gap-2 ml-2">
                <input 
                  type="checkbox" 
                  id="sign-language"
                  onChange={(e) => {
                    localStorage.setItem('sign-language-enabled', String(e.target.checked));
                  }}
                  checked={localStorage.getItem('sign-language-enabled') === 'true'}
                  className="rounded"
                />
                <label htmlFor="sign-language" className="text-xs text-white/60 whitespace-nowrap">Sign Language</label>
              </div>
              <label className="flex items-center gap-1 text-white/60">
                <input
                  type="checkbox"
                  checked={clarificationEnabled}
                  onChange={(e) => {
                    setClarificationEnabled(e.target.checked)
                    saveAgentSettings({ agentName, personality, activationMode, clarificationEnabled: e.target.checked, llmProvider, llmModel, llmBaseUrl })
                  }}
                  className="rounded"
                />
                Ask when unsure
              </label>
            </div>
            <input
              type="text"
              value={personality}
              onChange={(e) => {
                setPersonality(e.target.value)
                saveAgentSettings({ agentName, personality: e.target.value, activationMode, clarificationEnabled, llmProvider, llmModel, llmBaseUrl })
              }}
              placeholder="Personality traits"
              className="w-full rounded-md bg-white/10 px-2 py-1.5 text-xs text-white/70 focus:outline-none"
            />
            <div className="flex gap-2 text-xs">
              <select
                value={llmProvider}
                onChange={(e) => {
                  const v = e.target.value as 'deepgram' | 'openai' | 'ollama'
                  setLlmProvider(v)
                  saveAgentSettings({ agentName, personality, activationMode, clarificationEnabled, llmProvider: v, llmModel, llmBaseUrl })
                  if (v === 'ollama') {
                    window.omi.deepgramAgentOllamaCheck().then((r) => {
                      setOllamaStatus({ checked: true, ok: r.ok, models: r.models ?? [] })
                    })
                  }
                }}
                className="rounded-md bg-white/10 px-2 py-1 text-white focus:outline-none"
              >
                <option value="deepgram" className="bg-neutral-900">Deepgram (hosted)</option>
                <option value="openai" className="bg-neutral-900">OpenAI</option>
                <option value="ollama" className="bg-neutral-900">Ollama (local)</option>
              </select>
              {llmProvider === 'ollama' && (
                <>
                  <input
                    type="text"
                    value={llmModel}
                    onChange={(e) => {
                      setLlmModel(e.target.value)
                      saveAgentSettings({ agentName, personality, activationMode, clarificationEnabled, llmProvider, llmModel: e.target.value, llmBaseUrl })
                    }}
                    placeholder="Model (e.g. qwen3.5)"
                    className="w-32 rounded-md bg-white/10 px-2 py-1 text-white focus:outline-none"
                  />
                  <button
                    onClick={async () => {
                      const r = await window.omi.deepgramAgentOllamaCheck()
                      setOllamaStatus({ checked: true, ok: r.ok, models: r.models ?? [] })
                    }}
                    className="rounded-md bg-white/10 px-2 py-1 text-white/60 hover:text-white"
                  >
                    {ollamaStatus.checked ? (ollamaStatus.ok ? 'Connected' : 'Offline') : 'Check'}
                  </button>
                </>
              )}
              {llmProvider === 'openai' && (
                <input
                  type="text"
                  value={llmModel}
                  onChange={(e) => {
                    setLlmModel(e.target.value)
                    saveAgentSettings({ agentName, personality, activationMode, clarificationEnabled, llmProvider, llmModel: e.target.value, llmBaseUrl })
                  }}
                  placeholder="Model (e.g. gpt-4o-mini)"
                  className="w-32 rounded-md bg-white/10 px-2 py-1 text-white focus:outline-none"
                />
              )}
            </div>
            {llmProvider === 'ollama' && ollamaStatus.checked && ollamaStatus.models.length > 0 && (
              <div className="text-xs text-white/40">
                Available: {ollamaStatus.models.slice(0, 5).join(', ')}
              </div>
            )}
          </div>
        }
      />

      <SettingRow
        icon={deviceState === 'connected' ? BluetoothConnected : Bluetooth}
        title="Omi Device"
        subtitle={deviceState === 'connected'
          ? `Connected: ${deviceInfo?.name || 'Omi'}${deviceBattery !== null ? ` (${deviceBattery}%)` : ''}`
          : 'Connect your Omi wearable via Bluetooth to stream audio directly'}
        keywords="omi device bluetooth ble wearable hardware"
        control={
          <div className="flex items-center gap-2">
            {deviceState === 'connected' ? (
              <>
                {deviceInfo?.firmwareRevision && (
                  <span className="text-xs text-white/40">v{deviceInfo.firmwareRevision}</span>
                )}
                {deviceBattery !== null && (
                  <span className="text-xs text-white/40">{deviceBattery}%</span>
                )}
                <button
                  onClick={() => omiBleClient.disconnect()}
                  className="rounded-md bg-red-500/20 px-3 py-1.5 text-sm font-medium text-red-400 hover:bg-red-500/30"
                >
                  Disconnect
                </button>
              </>
            ) : (
              <button
                onClick={async () => {
                  const device = await omiBleClient.scan()
                  if (device) {
                    await omiBleClient.connect(device)
                  }
                }}
                disabled={deviceState === 'scanning' || deviceState === 'connecting'}
                className="rounded-md bg-blue-500/20 px-3 py-1.5 text-sm font-medium text-blue-400 hover:bg-blue-500/30 disabled:opacity-50"
              >
                {deviceState === 'scanning' ? 'Scanning...' :
                 deviceState === 'connecting' ? 'Connecting...' :
                 'Connect'}
              </button>
            )}
          </div>
        }
      />

      <SettingRow
        icon={FileText}
        title="Summarize Transcript"
        subtitle="Extract summary, tasks, and key points from the current transcript using Gemini."
        keywords="summary tasks key points extract transcript"
        control={
          <div className="flex flex-col items-end gap-2">
            <button
              onClick={async () => {
                const segments = liveConversation.getSegments()
                if (segments.length === 0) {
                  setSummaryResult({ summary: 'No transcript yet. Start recording first.', tasks: [], keyPoints: [] })
                  return
                }
                setSummaryLoading(true)
                try {
                  const result = await extractSummary(segments)
                  setSummaryResult(result)
                } catch (e) {
                  setSummaryResult({ summary: `Error: ${(e as Error).message}`, tasks: [], keyPoints: [] })
                } finally {
                  setSummaryLoading(false)
                }
              }}
              disabled={summaryLoading}
              className="rounded-md bg-purple-500/20 px-3 py-1.5 text-sm font-medium text-purple-400 hover:bg-purple-500/30 disabled:opacity-50"
            >
              {summaryLoading ? 'Summarizing...' : 'Summarize'}
            </button>
            {summaryResult && (
              <div className="mt-2 w-full rounded-md bg-white/5 p-3 text-xs text-white/70">
                <p className="mb-1 font-medium text-white/90">Summary</p>
                <p>{summaryResult.summary}</p>
                {summaryResult.tasks.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 font-medium text-white/90">Tasks</p>
                    <ul className="list-disc pl-4">
                      {summaryResult.tasks.map((t, i) => <li key={i}>{t}</li>)}
                    </ul>
                  </div>
                )}
                {summaryResult.keyPoints.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 font-medium text-white/90">Key Points</p>
                    <ul className="list-disc pl-4">
                      {summaryResult.keyPoints.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        }
      />
    </>
  )
}
