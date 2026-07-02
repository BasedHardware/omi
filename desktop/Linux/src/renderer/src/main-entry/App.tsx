import React, { useEffect, useState } from 'react'
import { useAuth } from '../stores/auth'
import { useSettings } from '../stores/settings'
import { Sidebar } from './Sidebar'
import { SignInView } from './SignInView'
import { Onboarding } from './Onboarding'
import { DashboardPage } from './pages/DashboardPage'
import { ConversationsPage } from './pages/ConversationsPage'
import { ChatPage } from './pages/ChatPage'
import { MemoriesPage } from './pages/MemoriesPage'
import { TasksPage } from './pages/TasksPage'
import { RewindPage } from './pages/RewindPage'
import { InsightsPage } from './pages/InsightsPage'
import { GoalsPage } from './pages/GoalsPage'
import { FocusPage } from './pages/FocusPage'
import { GraphPage } from './pages/GraphPage'
import { PersonaPage } from './pages/PersonaPage'
import { AppsPage } from './pages/AppsPage'
import { SettingsPage } from './pages/SettingsPage'
import { HelpPage } from './pages/HelpPage'
import { Spinner } from '../components/ui'
import { useProactive } from '../stores/proactive'
import CelebrationOverlay from '../components/CelebrationOverlay'
import { useChat } from '../stores/chat'
import { useTasks } from '../stores/tasks'
import { useGoals } from '../stores/goals'

export type Page =
  | 'dashboard'
  | 'conversations'
  | 'chat'
  | 'memories'
  | 'tasks'
  | 'goals'
  | 'rewind'
  | 'focus'
  | 'insights'
  | 'graph'
  | 'persona'
  | 'apps'
  | 'settings'
  | 'help'

const PAGE_ORDER: Page[] = [
  'dashboard',
  'conversations',
  'chat',
  'memories',
  'tasks',
  'goals',
  'rewind',
  'focus',
  'insights',
  'graph',
  'persona',
  'apps',
  'settings'
]

export function App() {
  const auth = useAuth((s) => s.state)
  const initAuth = useAuth((s) => s.init)
  const { settings, load: loadSettings } = useSettings()
  const initProactive = useProactive((s) => s.init)
  const [page, setPage] = useState<Page>('dashboard')

  useEffect(() => {
    initAuth()
    void loadSettings()
    initProactive()
    if (import.meta.env.DEV) {
      // Dev affordances for screenshot tooling: page nav + store handles for sample-data injection.
      const w = window as unknown as { __omiPreviewNavigate?: (p: Page) => void; __omiStores?: Record<string, unknown> }
      w.__omiPreviewNavigate = setPage
      w.__omiStores = { chat: useChat, tasks: useTasks, goals: useGoals, settings: useSettings }
    }
    return window.omi.nav.onNavigate((p) => setPage(p as Page))
  }, [])

  // Cmd+1-6 on Mac -> Ctrl+1-8 here.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && !e.shiftKey && !e.altKey) {
        const n = parseInt(e.key, 10)
        if (n >= 1 && n <= PAGE_ORDER.length) {
          setPage(PAGE_ORDER[n - 1])
          e.preventDefault()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (settings) {
      document.documentElement.style.setProperty('--font-scale', String(settings.fontScale || 1))
    }
  }, [settings?.fontScale])

  if (!auth) {
    return (
      <Shell>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <Spinner size={22} />
        </div>
      </Shell>
    )
  }

  if (!auth.signedIn) {
    return (
      <Shell>
        <SignInView />
      </Shell>
    )
  }

  if (settings && !settings.hasOnboarded) {
    return (
      <Shell>
        <Onboarding />
      </Shell>
    )
  }

  return (
    <Shell>
      <div style={{ display: 'flex', height: '100%', width: '100%' }}>
        <Sidebar page={page} onNavigate={setPage} />
        <main
          key={page}
          style={{
            flex: 1,
            margin: '14px 14px 14px 0',
            borderRadius: 'var(--radius-window)',
            border: '1px solid rgba(58, 57, 64, 0.22)',
            background: 'linear-gradient(135deg, rgba(26, 26, 26, 0.96), rgba(15, 15, 15, 0.96))',
            boxShadow: 'var(--shadow-content)',
            overflow: 'hidden',
            animation: 'fadeSlideIn 0.2s ease',
            minWidth: 0
          }}
        >
          {page === 'dashboard' && <DashboardPage onNavigate={setPage} />}
          {page === 'conversations' && <ConversationsPage />}
          {page === 'chat' && <ChatPage />}
          {page === 'memories' && <MemoriesPage />}
          {page === 'tasks' && <TasksPage />}
          {page === 'goals' && <GoalsPage />}
          {page === 'rewind' && <RewindPage />}
          {page === 'focus' && <FocusPage />}
          {page === 'insights' && <InsightsPage />}
          {page === 'graph' && <GraphPage />}
          {page === 'persona' && <PersonaPage />}
          {page === 'apps' && <AppsPage />}
          {page === 'settings' && <SettingsPage />}
          {page === 'help' && <HelpPage />}
        </main>
      </div>
      <CelebrationOverlay />
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ height: '100%', background: 'var(--bg-primary)', position: 'relative' }}>
      {/* Drag strip for the hidden titlebar; native window controls overlay the right edge. */}
      <div
        style={
          {
            position: 'absolute',
            top: 0,
            left: 0,
            right: 140,
            height: 38,
            WebkitAppRegion: 'drag',
            zIndex: 40
          } as React.CSSProperties
        }
      />
      {children}
    </div>
  )
}
