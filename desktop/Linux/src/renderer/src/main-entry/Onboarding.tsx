import React, { useState } from 'react'
import herologo from '../assets/herologo.png'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { useSettings } from '../stores/settings'

// First-run onboarding (OnboardingView.swift): welcome -> profile -> capture
// opt-in -> done. Gated by settings.hasOnboarded.

export function Onboarding() {
  const auth = useAuth((s) => s.state)
  const { settings, update } = useSettings()
  const [step, setStep] = useState(0)
  const [name, setName] = useState(auth?.name ?? '')
  const [enableCapture, setEnableCapture] = useState(true)

  const finish = async () => {
    if (name.trim() && name.trim() !== auth?.name) {
      void api.updateProfile({ name: name.trim() }).catch(() => {})
    }
    await update({
      hasOnboarded: true,
      rewindEnabled: enableCapture ? true : settings?.rewindEnabled ?? false,
      proactiveEnabled: enableCapture ? true : settings?.proactiveEnabled ?? false
    })
  }

  const next = () => setStep((s) => s + 1)

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 40
      }}
    >
      <div className="card" style={{ width: 460, padding: 32, textAlign: 'center', background: 'var(--bg-secondary)' }}>
        <img src={herologo} width={56} height={56} style={{ borderRadius: 14, marginBottom: 16 }} alt="omi" />

        {step === 0 && (
          <>
            <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Welcome to Omi</div>
            <div style={{ fontSize: 14, color: 'var(--text-tertiary)', lineHeight: 1.6, marginBottom: 24 }}>
              Your AI that sees your screen, listens to your conversations, remembers what matters, and helps you get
              things done, now on Linux.
            </div>
            <button className="btn-primary" style={{ width: '100%' }} onClick={next}>
              Get started
            </button>
          </>
        )}

        {step === 1 && (
          <>
            <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>What should Omi call you?</div>
            <div style={{ fontSize: 13.5, color: 'var(--text-tertiary)', marginBottom: 20 }}>
              This personalizes your memories and chat.
            </div>
            <input
              autoFocus
              value={name}
              placeholder="Your name"
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') next()
              }}
              style={{ width: '100%', marginBottom: 20, textAlign: 'center', fontSize: 15 }}
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn-secondary" style={{ flex: 1 }} onClick={next}>
                Skip
              </button>
              <button className="btn-primary" style={{ flex: 1 }} onClick={next}>
                Continue
              </button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Let Omi see your screen?</div>
            <div style={{ fontSize: 13.5, color: 'var(--text-tertiary)', lineHeight: 1.6, marginBottom: 18 }}>
              Omi can capture your screen on-device to power Rewind search and proactively surface memories, tasks,
              and nudges. Everything stays local except short text sent for analysis. You can change this anytime.
            </div>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: 12,
                borderRadius: 12,
                background: 'var(--bg-tertiary)',
                marginBottom: 20,
                cursor: 'pointer',
                textAlign: 'left'
              }}
            >
              <input type="checkbox" checked={enableCapture} onChange={(e) => setEnableCapture(e.target.checked)} />
              <span style={{ fontSize: 13.5, color: 'var(--text-secondary)' }}>
                Enable screen capture (Rewind + proactive assistant)
              </span>
            </label>
            <button className="btn-primary" style={{ width: '100%' }} onClick={() => void finish()}>
              Finish setup
            </button>
          </>
        )}

        <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginTop: 22 }}>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              style={{
                width: 7,
                height: 7,
                borderRadius: 4,
                background: i === step ? 'var(--purple-primary)' : 'var(--bg-quaternary)'
              }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
