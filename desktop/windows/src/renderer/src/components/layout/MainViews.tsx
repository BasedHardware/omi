import { memo } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  Brain,
  History,
  ListChecks,
  MessageSquare,
  Puzzle,
  Settings as SettingsIcon,
  X,
  type LucideIcon
} from 'lucide-react'
import { Home } from '../../pages/Home'
import { Conversations } from '../../pages/Conversations'
import { Memories } from '../../pages/Memories'
import { Settings } from '../../pages/Settings'
import { ConversationDetail } from '../../pages/ConversationDetail'
import { Tasks } from '../../pages/Tasks'
import { Goals } from '../../pages/Goals'
import { Apps } from '../../pages/Apps'
import { Rewind } from '../../pages/Rewind'
import { LiveConversation } from '../../pages/LiveConversation'
import { cn } from '../../lib/utils'

const HomePanel = memo(Home)
const ConversationsPanel = memo(Conversations)
const MemoriesPanel = memo(Memories)
const SettingsPanel = memo(Settings)
const TasksPanel = memo(Tasks)
const GoalsPanel = memo(Goals)
const AppsPanel = memo(Apps)
const RewindPanel = memo(Rewind)

type NavId = 'conversations' | 'tasks' | 'memories' | 'rewind' | 'integrations'

const NAV_ITEMS: { id: NavId; label: string; to: string; Icon: LucideIcon }[] = [
  { id: 'conversations', label: 'Conversations', to: '/conversations', Icon: MessageSquare },
  { id: 'tasks', label: 'Tasks', to: '/tasks', Icon: ListChecks },
  { id: 'memories', label: 'Memories', to: '/memories', Icon: Brain },
  { id: 'rewind', label: 'Rewind', to: '/rewind', Icon: History },
  { id: 'integrations', label: 'Integrations', to: '/integrations', Icon: Puzzle }
]

type ModalSpec = {
  nav: NavId
  label: string
  node: React.ReactNode
  size?: 'normal' | 'wide'
}

function TopChrome(props: { activeNav?: NavId; settingsOpen: boolean }): React.JSX.Element {
  const { activeNav, settingsOpen } = props
  const navigate = useNavigate()

  const goNav = (item: (typeof NAV_ITEMS)[number]): void => {
    navigate(activeNav === item.id ? '/home' : item.to)
  }

  return (
    <header className="pointer-events-none fixed left-0 right-0 top-0 z-50 flex h-24 items-start justify-between px-8 pt-7">
      <button
        onClick={() => navigate('/home')}
        className="pointer-events-auto mt-1 font-display text-2xl font-bold tracking-tight text-white"
        aria-label="Omi home"
      >
        omi
      </button>

      <nav className="pointer-events-auto absolute left-1/2 top-6 flex -translate-x-1/2 items-center gap-6">
        {NAV_ITEMS.map((item) => {
          const active = activeNav === item.id
          const Icon = item.Icon
          return (
            <button
              key={item.id}
              onClick={() => goNav(item)}
              aria-label={item.label}
              aria-pressed={active}
              title={item.label}
              className={cn(
                'group relative flex h-14 w-14 items-center justify-center rounded-2xl border transition-all duration-200',
                active
                  ? 'border-white/15 bg-white/[0.08] text-white shadow-[0_12px_30px_rgba(91,2,224,0.35)]'
                  : 'border-white/10 bg-black/20 text-white/55 hover:border-white/[0.18] hover:bg-white/[0.04] hover:text-white/85'
              )}
            >
              <Icon className="h-6 w-6" strokeWidth={active ? 2.2 : 1.9} />
              {active && (
                <span className="absolute -bottom-1.5 h-0.5 w-7 rounded-full bg-[color:var(--accent)] shadow-[0_0_14px_rgba(168,85,247,0.9)]" />
              )}
            </button>
          )
        })}
      </nav>

      <button
        onClick={() => navigate(settingsOpen ? '/home' : '/settings')}
        aria-label="Settings"
        aria-pressed={settingsOpen}
        title="Settings"
        className={cn(
          'pointer-events-auto flex h-12 w-12 items-center justify-center rounded-2xl border transition-all duration-200',
          settingsOpen
            ? 'border-white/15 bg-white/[0.08] text-white shadow-[0_0_26px_rgba(91,2,224,0.85)]'
            : 'border-transparent bg-transparent text-white/65 hover:bg-white/[0.04] hover:text-white'
        )}
      >
        <SettingsIcon className="h-6 w-6" strokeWidth={2} />
      </button>
    </header>
  )
}

function ModalFrame(props: {
  title: string
  size?: ModalSpec['size']
  onClose: () => void
  children: React.ReactNode
}): React.JSX.Element {
  const widthClass = props.size === 'wide' ? 'max-w-6xl' : 'max-w-5xl'
  return (
    <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center px-8 pb-10 pt-28">
      <section
        className={cn(
          'pointer-events-auto relative flex h-[min(78vh,760px)] w-full flex-col overflow-hidden rounded-[1.35rem] border border-white/[0.12] bg-black/45 shadow-[0_28px_80px_rgba(0,0,0,0.46)] backdrop-blur-2xl',
          widthClass
        )}
        aria-label={props.title}
      >
        <button
          onClick={props.onClose}
          className="absolute right-5 top-5 z-20 rounded-xl p-2 text-white/55 transition-colors hover:bg-white/[0.08] hover:text-white"
          aria-label={`Close ${props.title}`}
          title="Close"
        >
          <X className="h-5 w-5" strokeWidth={2} />
        </button>
        <div className="min-h-0 flex-1 overflow-hidden">{props.children}</div>
      </section>
    </div>
  )
}

function SettingsDrawer(props: { onClose: () => void; open: boolean }): React.JSX.Element | null {
  if (!props.open) return null
  return (
    <aside className="fixed bottom-8 right-8 top-28 z-40 w-[min(720px,42vw)] min-w-[520px] overflow-hidden rounded-[1.35rem] border border-white/[0.12] bg-black/50 shadow-[0_28px_80px_rgba(0,0,0,0.48)] backdrop-blur-2xl">
      <SettingsPanel onClose={props.onClose} />
    </aside>
  )
}

export function MainViews(): React.JSX.Element {
  const { pathname } = useLocation()
  const navigate = useNavigate()

  if (pathname === '/' || pathname === '/live' || pathname === '/chat') {
    return <Navigate to="/home" replace />
  }

  const closeOverlay = (): void => {
    void navigate('/home')
  }
  const isSettings = pathname === '/settings'
  const detailMatch = pathname.match(/^\/conversations\/([^/]+)$/)

  let modal: ModalSpec | null = null
  if (pathname === '/conversations') {
    modal = {
      nav: 'conversations',
      label: 'Conversations',
      node: <ConversationsPanel onClose={closeOverlay} />
    }
  } else if (pathname === '/conversations/live') {
    modal = {
      nav: 'conversations',
      label: 'Live Conversation',
      node: <LiveConversation />
    }
  } else if (detailMatch) {
    modal = {
      nav: 'conversations',
      label: 'Conversation',
      node: <ConversationDetail conversationId={detailMatch[1]} />
    }
  } else if (pathname === '/tasks') {
    modal = { nav: 'tasks', label: 'Tasks', node: <TasksPanel /> }
  } else if (pathname === '/goals') {
    modal = { nav: 'tasks', label: 'Goals', node: <GoalsPanel /> }
  } else if (pathname === '/memories') {
    modal = { nav: 'memories', label: 'Memories', node: <MemoriesPanel />, size: 'wide' }
  } else if (pathname === '/rewind') {
    modal = { nav: 'rewind', label: 'Rewind', node: <RewindPanel />, size: 'wide' }
  } else if (pathname === '/apps' || pathname === '/integrations') {
    modal = { nav: 'integrations', label: 'Integrations', node: <AppsPanel /> }
  } else if (pathname !== '/home' && !isSettings) {
    return <Navigate to="/home" replace />
  }

  return (
    <div className="relative h-full min-h-0 overflow-hidden">
      <HomePanel />
      <TopChrome activeNav={modal?.nav} settingsOpen={isSettings} />
      {modal && (
        <ModalFrame title={modal.label} size={modal.size} onClose={closeOverlay}>
          {modal.node}
        </ModalFrame>
      )}
      <SettingsDrawer open={isSettings} onClose={closeOverlay} />
    </div>
  )
}
