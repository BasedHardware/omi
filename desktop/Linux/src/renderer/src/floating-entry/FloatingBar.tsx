import React, { useEffect, useRef, useState } from 'react'
import herologo from '../assets/herologo.png'
import { IconCamera, IconClose, IconInsights, IconMic, IconPhone, IconSend, IconSettings } from '../components/Icons'
import { Markdown } from '../components/ui'
import { PcmCapture } from '../lib/audio'
import { RealtimeVoice } from '../lib/realtimeVoice'
import { useAuth } from '../stores/auth'
import { useChat } from '../stores/chat'
import type { ProactiveNotification } from '../../../shared/types'

const NOTIFICATION_SIZE = { width: 430, height: 112 }

// FloatingControlBarView.swift counterpart. States: pill -> bar (hover) ->
// ask input -> AI conversation; push-to-talk + realtime voice.

type BarState = 'pill' | 'bar' | 'input' | 'conversation' | 'voice'

const SIZES: Record<BarState, { width: number; height: number }> = {
  pill: { width: 40, height: 14 },
  bar: { width: 210, height: 50 },
  input: { width: 430, height: 96 },
  conversation: { width: 430, height: 440 },
  voice: { width: 360, height: 230 }
}

function initialState(): BarState {
  // Dev affordance: floating.html?state=bar|input|conversation|voice forces a start state.
  const forced = new URLSearchParams(location.search).get('state') as BarState | null
  return forced && ['pill', 'bar', 'input', 'conversation', 'voice'].includes(forced) ? forced : 'pill'
}

export function FloatingBar() {
  const [state, setState] = useState<BarState>(initialState)
  const stateRef = useRef(state)
  stateRef.current = state
  const [input, setInput] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [listening, setListening] = useState(false)
  const [level, setLevel] = useState(0)
  const [interim, setInterim] = useState('')
  const [notif, setNotif] = useState<ProactiveNotification | null>(null)
  const notifTimer = useRef<number | null>(null)
  const collapseTimer = useRef<number | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const pttCapture = useRef<PcmCapture | null>(null)
  const realtime = useRef<RealtimeVoice | null>(null)
  const [voiceStatus, setVoiceStatus] = useState<'connecting' | 'live' | 'error'>('connecting')
  const [userTranscript, setUserTranscript] = useState('')
  const [aiTranscript, setAiTranscript] = useState('')
  const chat = useChat()
  const auth = useAuth((s) => s.state)
  const initAuth = useAuth((s) => s.init)

  const startRealtime = async () => {
    goTo('voice')
    setVoiceStatus('connecting')
    setUserTranscript('')
    setAiTranscript('')
    realtime.current = new RealtimeVoice()
    const ok = await realtime.current.start({
      onStatus: (s) => setVoiceStatus(s === 'connected' ? 'live' : s === 'error' ? 'error' : 'connecting'),
      onInputTranscript: (t) => setUserTranscript((prev) => (prev ? prev + ' ' : '') + t),
      onOutputTranscript: (t) => setAiTranscript((prev) => prev + t)
    })
    if (!ok) setVoiceStatus('error')
  }

  const stopRealtime = () => {
    realtime.current?.stop()
    realtime.current = null
    goTo('pill')
  }

  useEffect(() => {
    initAuth()
    // Sync the OS window to a forced initial state (dev affordance).
    if (state !== 'pill') {
      const size = SIZES[state]
      window.omi.floating.setSize(size.width, size.height)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    chat.setUserName(auth?.name)
  }, [auth?.name])

  const goTo = (next: BarState) => {
    setMenuOpen(false)
    setState(next)
    const size = SIZES[next]
    window.omi.floating.setSize(size.width, size.height)
    if (next === 'input') {
      window.omi.floating.focus()
      setTimeout(() => inputRef.current?.focus(), 60)
    }
  }

  // Global hotkey toggles the ask input (GlobalShortcutManager.askAINotification).
  useEffect(() => {
    return window.omi.floating.onToggleAsk(() => {
      if (stateRef.current === 'input' || stateRef.current === 'conversation') goTo('pill')
      else goTo('input')
    })
  }, [])

  const dismissNotif = () => {
    if (notifTimer.current) clearTimeout(notifTimer.current)
    notifTimer.current = null
    setNotif(null)
    if (stateRef.current === 'pill') {
      const size = SIZES.pill
      window.omi.floating.setSize(size.width, size.height)
    }
  }

  // Proactive insight notifications (the Mac app shows these below the bar).
  useEffect(() => {
    const show = (n: ProactiveNotification) => {
      if (stateRef.current !== 'pill') return // don't interrupt an active ask/conversation
      setNotif(n)
      window.omi.floating.setSize(NOTIFICATION_SIZE.width, NOTIFICATION_SIZE.height)
      if (notifTimer.current) clearTimeout(notifTimer.current)
      notifTimer.current = window.setTimeout(() => dismissNotif(), 12000)
    }
    if (import.meta.env.DEV) {
      ;(window as unknown as { __omiTestNotif?: (n: ProactiveNotification) => void }).__omiTestNotif = show
    }
    return window.omi.proactive.onNotification(show)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat.messages.length, chat.messages[chat.messages.length - 1]?.text?.length])

  // PTT voice input
  const startVoice = async () => {
    if (listening) return
    setListening(true)
    setInterim('')
    const unsub = window.omi.transcribe.onEvent('ptt', (event) => {
      if (event.type === 'interim') setInterim(event.text)
      else if (event.type === 'final') {
        setInterim('')
        setInput((prev) => (prev ? prev + ' ' : '') + event.text)
      }
    })
    const ok = await window.omi.transcribe.start('ptt')
    if (!ok) {
      setListening(false)
      unsub()
      return
    }
    pttCapture.current = new PcmCapture()
    try {
      await pttCapture.current.start({
        systemAudio: false,
        onFrame: (frame) => window.omi.transcribe.sendAudio('ptt', frame),
        onLevel: setLevel
      })
    } catch {
      setListening(false)
      window.omi.transcribe.stop('ptt')
      unsub()
    }
  }

  const stopVoice = (sendAfter: boolean) => {
    if (!listening) return
    window.omi.transcribe.finalize('ptt')
    pttCapture.current?.stop()
    pttCapture.current = null
    // Give the backend a moment to flush the final segment before closing.
    setTimeout(() => {
      window.omi.transcribe.stop('ptt')
      setListening(false)
      setLevel(0)
      if (sendAfter) {
        setTimeout(() => {
          const text = (inputRef.current?.value ?? '').trim()
          if (text) void submit(text)
        }, 350)
      }
    }, 600)
  }

  const submit = async (text: string) => {
    setInput('')
    goTo('conversation')
    const wantsScreen = /screen|see|looking at|tab|window/i.test(text)
    let imageDataUrl: string | undefined
    let screenContext: string | undefined
    if (wantsScreen) {
      const shot = await window.omi.capture.screenshot()
      imageDataUrl = shot?.dataUrl
      screenContext = (await window.omi.rewind.latestOcr(60_000)) ?? undefined
    }
    void chat.send(text, { imageDataUrl, screenContext })
  }

  const onPillEnter = () => {
    if (collapseTimer.current) clearTimeout(collapseTimer.current)
    if (stateRef.current === 'pill') goTo('bar')
  }

  const onBarLeave = () => {
    if (stateRef.current !== 'bar') return
    if (collapseTimer.current) clearTimeout(collapseTimer.current)
    collapseTimer.current = window.setTimeout(() => {
      if (stateRef.current === 'bar') goTo('pill')
    }, 450)
  }

  // ---------- renders ----------

  if (state === 'pill' && notif) {
    return (
      <div style={{ padding: 2, height: '100vh' }}>
        <NotificationCard
          notif={notif}
          onView={() => {
            window.omi.floating.openMain('insights')
            dismissNotif()
          }}
          onDismiss={dismissNotif}
        />
      </div>
    )
  }

  if (state === 'pill') {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {/* Outer hit target stays ~full window; inner pill matches the Mac's 28x6 collapsed bar. */}
        <div
          onMouseEnter={onPillEnter}
          style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <div
            style={{
              width: 28,
              height: 6,
              borderRadius: 3,
              background: 'rgba(255, 255, 255, 0.5)',
              boxShadow: '0 1px 4px rgba(0,0,0,0.4)'
            }}
          />
        </div>
      </div>
    )
  }

  if (state === 'bar') {
    return (
      <div style={{ padding: 2, height: '100vh' }} onMouseLeave={onBarLeave} onMouseEnter={onPillEnter}>
        <div style={shellStyle()}>
          <DragHandle />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, padding: '7px 0' }}>
            <button
              onClick={() => goTo('input')}
              style={{ fontSize: 13, fontWeight: 600, color: '#fff', lineHeight: 1.2 }}
            >
              Ask omi
            </button>
            <button
              onMouseDown={() => {
                goTo('input')
                void startVoice()
              }}
              style={{ fontSize: 11, color: 'rgba(255,255,255,0.8)', lineHeight: 1.2 }}
            >
              Push to talk
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '0 8px 0 0' }}>
            <button onClick={() => void startRealtime()} style={{ color: 'rgba(255,255,255,0.75)', padding: 2 }} title="Live voice">
              <IconPhone size={13} />
            </button>
            <div style={{ position: 'relative' }}>
              <button onClick={() => setMenuOpen((v) => !v)} style={{ color: 'rgba(255,255,255,0.7)', padding: 2 }} title="Options">
                <IconSettings size={11} />
              </button>
              {menuOpen && <GearMenu onClose={() => setMenuOpen(false)} />}
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (state === 'voice') {
    return (
      <div style={{ padding: 2, height: '100vh' }}>
        <div style={{ ...shellStyle(), flexDirection: 'column', alignItems: 'stretch', padding: '14px 16px', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                width: 9,
                height: 9,
                borderRadius: 5,
                background: voiceStatus === 'live' ? 'var(--success)' : voiceStatus === 'error' ? 'var(--error)' : 'var(--warning)',
                boxShadow: voiceStatus === 'live' ? '0 0 8px var(--success)' : 'none',
                animation: voiceStatus === 'live' ? 'pulse 1s ease-in-out infinite' : 'none'
              }}
            />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#fff', flex: 1 }}>
              {voiceStatus === 'live' ? 'Listening…' : voiceStatus === 'error' ? 'Voice unavailable' : 'Connecting…'}
            </span>
            <DragHandle inline />
          </div>
          <div style={{ flex: 1, overflowY: 'auto', fontSize: 13, lineHeight: 1.5 }}>
            {userTranscript && (
              <div style={{ color: 'rgba(255,255,255,0.9)', marginBottom: 8 }}>
                <span style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.45)' }}>You</span>
                <div>{userTranscript}</div>
              </div>
            )}
            {aiTranscript && (
              <div style={{ color: 'var(--purple-light)' }}>
                <span style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.45)' }}>omi</span>
                <div>{aiTranscript}</div>
              </div>
            )}
            {!userTranscript && !aiTranscript && voiceStatus === 'live' && (
              <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12 }}>Speak, pause and tap Done to get a reply.</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => realtime.current?.commit()}
              disabled={voiceStatus !== 'live'}
              style={{ flex: 1, fontSize: 12.5, fontWeight: 600, color: '#fff', background: 'rgba(255,255,255,0.12)', borderRadius: 10, padding: '7px 0' }}
            >
              Done speaking
            </button>
            <button
              onClick={stopRealtime}
              style={{ fontSize: 12.5, color: 'var(--error)', background: 'rgba(239,68,68,0.12)', borderRadius: 10, padding: '7px 14px' }}
            >
              End
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (state === 'input') {
    return (
      <div style={{ padding: 2, height: '100vh' }}>
        <div style={{ ...shellStyle(), flexDirection: 'column', alignItems: 'stretch', padding: '8px 10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <DragHandle inline />
            <button onClick={() => goTo('pill')} title="Close" style={{ color: 'rgba(255,255,255,0.5)', padding: 3 }}>
              <IconClose size={11} />
            </button>
            <input
              ref={inputRef}
              value={input}
              placeholder={listening ? 'Listening…' : 'Ask omi anything…'}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && input.trim()) void submit(input.trim())
                if (e.key === 'Escape') goTo('pill')
              }}
              style={{
                flex: 1,
                background: 'rgba(255,255,255,0.07)',
                border: '1px solid rgba(255,255,255,0.12)',
                color: '#fff',
                fontSize: 13
              }}
            />
            <button
              onClick={() => (listening ? stopVoice(true) : void startVoice())}
              title={listening ? 'Stop & send' : 'Voice input'}
              style={{
                color: listening ? 'var(--error)' : 'rgba(255,255,255,0.75)',
                padding: 5,
                animation: listening ? 'pulse 1.2s ease-in-out infinite' : 'none'
              }}
            >
              <IconMic size={15} />
            </button>
            <button
              onClick={() => {
                if (input.trim()) void submit(input.trim())
              }}
              disabled={!input.trim()}
              title="Send"
              style={{ color: input.trim() ? 'var(--purple-secondary)' : 'rgba(255,255,255,0.3)', padding: 5 }}
            >
              <IconSend size={14} />
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 7, minHeight: 16 }}>
            {listening ? (
              <>
                <Waveform level={level} />
                <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {interim || 'Speak now, release mic to send'}
                </span>
              </>
            ) : (
              <span style={{ fontSize: 10.5, color: 'rgba(255,255,255,0.35)' }}>
                Enter to send · Esc to dismiss · mentions of your screen attach a screenshot
              </span>
            )}
          </div>
        </div>
      </div>
    )
  }

  // conversation
  const last = chat.messages[chat.messages.length - 1]
  return (
    <div style={{ padding: 2, height: '100vh' }}>
      <div style={{ ...shellStyle(), flexDirection: 'column', alignItems: 'stretch', padding: 0, height: 'calc(100vh - 4px)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <button
            onClick={() => goTo('pill')}
            title="Close"
            style={{
              width: 22,
              height: 22,
              borderRadius: 11,
              background: 'rgba(255,255,255,0.08)',
              color: 'rgba(255,255,255,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <IconClose size={10} />
          </button>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'rgba(255,255,255,0.85)', flex: 1 }}>omi</span>
          <DragHandle inline />
          <button
            onClick={() => window.omi.floating.openMain('chat')}
            style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}
            title="Open in main window"
          >
            Open app
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
          {chat.messages.slice(-8).map((m) =>
            m.role === 'user' ? (
              <div
                key={m.id}
                style={{
                  background: 'var(--user-bubble)',
                  borderRadius: 14,
                  padding: '8px 12px',
                  fontSize: 13,
                  marginLeft: 40,
                  marginBottom: 12
                }}
              >
                {m.text}
              </div>
            ) : (
              <div key={m.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 12 }}>
                <img src={herologo} width={26} height={26} style={{ borderRadius: 7, flexShrink: 0 }} alt="omi" />
                <div
                  style={{
                    minWidth: 0,
                    flex: 1,
                    background: 'rgba(255,255,255,0.06)',
                    borderRadius: 14,
                    padding: '8px 12px',
                    fontSize: 13,
                    color: m.error ? 'var(--warning)' : 'rgba(255,255,255,0.9)'
                  }}
                >
                  {m.text ? <Markdown>{m.text}</Markdown> : m.streaming ? <FloatingTypingDots /> : null}
                </div>
              </div>
            )
          )}
          <div ref={endRef} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '9px 12px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <button
            onClick={async () => {
              const shot = await window.omi.capture.screenshot()
              if (shot) void chat.send('What do you see on my screen?', { imageDataUrl: shot.dataUrl })
            }}
            title="Ask about screen"
            style={{ color: 'rgba(255,255,255,0.6)', padding: 4 }}
          >
            <IconCamera size={15} />
          </button>
          <input
            value={input}
            placeholder="Follow up…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && input.trim() && !chat.streaming) {
                const t = input.trim()
                setInput('')
                void chat.send(t)
              }
              if (e.key === 'Escape') goTo('pill')
            }}
            style={{
              flex: 1,
              background: 'rgba(255,255,255,0.07)',
              border: '1px solid rgba(255,255,255,0.12)',
              color: '#fff',
              fontSize: 13
            }}
          />
          {chat.streaming ? (
            <button onClick={chat.stop} style={{ fontSize: 11.5, color: 'rgba(255,255,255,0.6)' }}>
              Stop
            </button>
          ) : (
            <button
              onClick={() => (listening ? stopVoice(true) : void startVoice())}
              title="Voice"
              style={{ color: listening ? 'var(--error)' : 'rgba(255,255,255,0.6)', padding: 4 }}
            >
              <IconMic size={14} />
            </button>
          )}
        </div>
        {last?.streaming === false && null}
      </div>
    </div>
  )
}

function NotificationCard({
  notif,
  onView,
  onDismiss
}: {
  notif: ProactiveNotification
  onView: () => void
  onDismiss: () => void
}) {
  const accent =
    notif.category === 'focus' ? '#3B82F6' : notif.category === 'reminder' ? '#F59E0B' : 'var(--purple-secondary)'
  return (
    <div
      style={{
        display: 'flex',
        gap: 11,
        height: 'calc(100vh - 4px)',
        padding: '12px 13px',
        borderRadius: 18,
        background: 'rgba(18, 18, 22, 0.95)',
        border: '1px solid rgba(255, 255, 255, 0.13)',
        boxShadow: '0 8px 28px rgba(0,0,0,0.5)'
      }}
    >
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: 10,
          background: `${accent}22`,
          color: accent,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0
        }}
      >
        <IconInsights size={17} />
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: '#fff',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              flex: 1
            }}
          >
            {notif.title}
          </span>
          <button
            onClick={onDismiss}
            title="Dismiss"
            style={{ color: 'rgba(255,255,255,0.5)', padding: 2, flexShrink: 0 }}
          >
            <IconClose size={11} />
          </button>
        </div>
        <div
          style={{
            fontSize: 12,
            color: 'rgba(255,255,255,0.7)',
            lineHeight: 1.4,
            marginTop: 2,
            overflow: 'hidden',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical'
          }}
        >
          {notif.body}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 7 }}>
          <button
            onClick={onView}
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: '#fff',
              background: 'rgba(255,255,255,0.1)',
              borderRadius: 8,
              padding: '4px 12px'
            }}
          >
            View in Omi
          </button>
        </div>
      </div>
    </div>
  )
}

function shellStyle(): React.CSSProperties {
  return {
    display: 'flex',
    alignItems: 'center',
    height: 'calc(100vh - 4px)',
    borderRadius: 20,
    background: 'rgba(18, 18, 22, 0.92)',
    border: '1px solid rgba(255, 255, 255, 0.15)',
    boxShadow: '0 8px 28px rgba(0,0,0,0.5)',
    overflow: 'visible'
  }
}

function DragHandle({ inline }: { inline?: boolean }) {
  return (
    <div
      title="Drag to move"
      style={
        {
          WebkitAppRegion: 'drag',
          padding: inline ? '2px 4px' : '8px 5px 8px 9px',
          color: 'rgba(255,255,255,0.3)',
          fontSize: 11,
          letterSpacing: 1,
          cursor: 'grab',
          flexShrink: 0
        } as React.CSSProperties
      }
    >
      ⋮⋮
    </div>
  )
}

// Three bouncing dots (theme.css `typingBounce`), tuned for the dark glass shell.
function FloatingTypingDots() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, height: 14 }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.7)',
            animation: 'typingBounce 1.3s ease-in-out infinite',
            animationDelay: `${i * 0.18}s`
          }}
        />
      ))}
    </div>
  )
}

function Waveform({ level }: { level: number }) {
  const factors = [0.6, 1, 0.8, 0.5]
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 2.5, height: 16 }}>
      {factors.map((f, i) => (
        <div
          key={i}
          style={{
            width: 3,
            height: Math.max(4, Math.min(16, 4 + level * 120 * f)),
            borderRadius: 2,
            background: 'var(--purple-secondary)',
            transition: 'height 0.09s ease'
          }}
        />
      ))}
    </div>
  )
}

function GearMenu({ onClose }: { onClose: () => void }) {
  const items = [
    { label: 'Open Omi', action: () => window.omi.floating.openMain() },
    { label: 'Settings', action: () => window.omi.floating.openMain('settings') },
    { label: 'Hide bar', action: () => window.omi.floating.hide() }
  ]
  return (
    <div
      style={{
        position: 'absolute',
        top: 20,
        right: 0,
        width: 130,
        background: 'rgba(26, 26, 30, 0.97)',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: 12,
        padding: 4,
        zIndex: 10,
        boxShadow: '0 8px 20px rgba(0,0,0,0.5)'
      }}
    >
      {items.map((i) => (
        <button
          key={i.label}
          onClick={() => {
            onClose()
            i.action()
          }}
          style={{ display: 'block', width: '100%', textAlign: 'left', fontSize: 12, color: 'rgba(255,255,255,0.8)', padding: '7px 9px', borderRadius: 8 }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.08)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          {i.label}
        </button>
      ))}
    </div>
  )
}
