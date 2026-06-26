import React, { useState } from 'react'
import herologo from '../assets/herologo.png'
import googleLogo from '../assets/google_logo.png'
import { useAuth } from '../stores/auth'

export function SignInView() {
  const signIn = useAuth((s) => s.signIn)
  const [waiting, setWaiting] = useState<null | 'google' | 'apple'>(null)

  const start = (provider: 'google' | 'apple') => {
    setWaiting(provider)
    signIn(provider)
  }

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 14
      }}
    >
      <img src={herologo} width={64} height={64} style={{ borderRadius: 16, marginBottom: 6 }} alt="omi" />
      <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5 }}>omi</div>
      <div style={{ fontSize: 14, color: 'var(--text-tertiary)', marginBottom: 18 }}>
        Your AI that sees, listens, and remembers, now on Linux.
      </div>

      <button
        onClick={() => start('google')}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 10,
          width: 280,
          padding: '11px 0',
          borderRadius: 14,
          background: '#ffffff',
          color: '#1a1a1a',
          fontSize: 14,
          fontWeight: 600
        }}
      >
        <img src={googleLogo} width={16} height={16} alt="" />
        Continue with Google
      </button>
      <button
        onClick={() => start('apple')}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 10,
          width: 280,
          padding: '11px 0',
          borderRadius: 14,
          background: '#000',
          border: '1px solid var(--border-strong)',
          color: '#fff',
          fontSize: 14,
          fontWeight: 600
        }}
      >
         Continue with Apple
      </button>

      <div style={{ fontSize: 12, color: 'var(--text-quaternary)', marginTop: 14, maxWidth: 320, textAlign: 'center' }}>
        {waiting
          ? 'Complete sign-in in your browser. This window will update automatically.'
          : 'Sign-in opens in your browser and returns here. Same account as the Mac and mobile apps.'}
      </div>
      {waiting && <div className="spinner" />}
    </div>
  )
}
