import { useState } from 'react'
import { signInWithGoogle } from '../lib/firebase'
import omiLogo from '../assets/omilogo.png'

export function Login(): React.JSX.Element {
  const [signing, setSigning] = useState(false)

  const onClick = async (): Promise<void> => {
    if (signing) return
    setSigning(true)
    try {
      const user = await signInWithGoogle()
      console.log('Signed in as', user.email)
    } catch (e) {
      console.error('Sign-in failed:', e)
      alert(`Sign-in failed: ${(e as Error).message}`)
    } finally {
      setSigning(false)
    }
  }

  return (
    <div className="app-canvas relative flex h-full items-center justify-center p-8">
      <div className="animate-fade-in relative z-10 flex w-full max-w-[420px] flex-col items-center">
        <img src={omiLogo} alt="omi" className="h-24 w-auto" />
        <p className="mt-6 text-base leading-relaxed text-white/70">Sign in to continue</p>
        <div className="h-48" />
        <button
          onClick={onClick}
          disabled={signing}
          className="flex items-center justify-center gap-3 rounded-xl bg-white px-8 py-3.5 font-medium text-black transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          <svg viewBox="0 0 48 48" className="h-5 w-5">
            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
            <path fill="#FBBC05" d="M10.54 28.59A14.5 14.5 0 0 1 9.5 24c0-1.59.28-3.14.76-4.59l-7.98-6.19A23.99 23.99 0 0 0 0 24c0 3.77.87 7.35 2.56 10.56l7.98-5.97z" />
            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 5.97C6.51 42.62 14.62 48 24 48z" />
          </svg>
          {signing ? 'Signing in…' : 'Sign in with Google'}
        </button>
      </div>
    </div>
  )
}
