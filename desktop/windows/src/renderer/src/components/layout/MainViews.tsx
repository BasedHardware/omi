import { memo, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Home } from '../../pages/Home'
import { Conversations } from '../../pages/Conversations'
import { Memories } from '../../pages/Memories'
import { Settings } from '../../pages/Settings'
import { ConversationDetail } from '../../pages/ConversationDetail'
import { Tasks } from '../../pages/Tasks'
import { Goals } from '../../pages/Goals'
import { Apps } from '../../pages/Apps'
import { Rewind } from '../../pages/Rewind'
import { Insights } from '../../pages/Insights'
import { Focus } from '../../pages/Focus'
import { LiveConversation } from '../../pages/LiveConversation'
import { Chat } from '../../pages/Chat'
import { Persona } from '../../pages/Persona'
import { Permissions } from '../../pages/Permissions'
import { Help } from '../../pages/Help'
import { ChatLab } from '../../pages/ChatLab'
import { People } from '../../pages/People'

// Every page stays mounted (inactive ones are just hidden) so switching tabs is
// instant. But the pages take no props, so without memo they ALL re-render on
// every navigation (MainViews re-renders when the pathname changes) — and that
// re-render reconciles heavy subtrees like the Memories brain map (an R3F scene)
// or large memory/conversation lists, which is what made tab switches lag.
// memo() makes a page re-render only from its OWN hooks/state, never from a
// parent navigation, so changing tabs just toggles the wrapper's visibility.
const HomePanel = memo(Home)
const ConversationsPanel = memo(Conversations)
const MemoriesPanel = memo(Memories)
const SettingsPanel = memo(Settings)
const TasksPanel = memo(Tasks)
const GoalsPanel = memo(Goals)
const AppsPanel = memo(Apps)
const RewindPanel = memo(Rewind)
const InsightsPanel = memo(Insights)
const FocusPanel = memo(Focus)
const ChatPanel = memo(Chat)
const PersonaPanel = memo(Persona)
const PermissionsPanel = memo(Permissions)
const HelpPanel = memo(Help)
const ChatLabPanel = memo(ChatLab)
const PeoplePanel = memo(People)

function panelClass(active: boolean): string {
  return active ? 'flex h-full min-h-0 flex-col' : 'hidden'
}

export function MainViews(): React.JSX.Element {
  const { pathname } = useLocation()
  const navigate = useNavigate()

  // Mounting every panel up front (incl. the heavy Memories R3F brain map) on
  // first render blocks the main thread during the startup entrance animations
  // — a ~133ms frame stall (npm run bench:anim). Defer the inactive panels until
  // AFTER the animations have played. NOTE: requestIdleCallback is wrong here —
  // CSS animations run on the compositor, so the main thread looks idle *during*
  // them and the callback fires mid-animation, causing the very stall we're
  // avoiding. A fixed timeout that lands after the animations is what we want.
  // The active panel always mounts; any panel mounts on demand if navigated to
  // before hydration, so tab-switching stays instant once warmed.
  const [hydrateAll, setHydrateAll] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setHydrateAll(true), 1800)
    return () => clearTimeout(timer)
  }, [])

  // Fix blank startup: redirect '/' to '/home' via effect so content renders
  // immediately on the same frame instead of returning a Navigate (which leaves
  // the main pane blank for one render cycle before the route updates).
  useEffect(() => {
    if (pathname === '/') navigate('/home', { replace: true })
  }, [pathname, navigate])

  if (pathname === '/conversations/live' || pathname === '/live') {
    return <LiveConversation />
  }

  const detailMatch = pathname.match(/^\/conversations\/([^/]+)$/)
  if (detailMatch) {
    return <ConversationDetail conversationId={detailMatch[1]} />
  }

  const isHome = pathname === '/home' || pathname === '/'
  const isConversations = pathname === '/conversations'
  const isMemories = pathname === '/memories'
  const isSettings = pathname === '/settings'
  const isTasks = pathname === '/tasks'
  const isGoals = pathname === '/goals'
  const isApps = pathname === '/apps'
  const isRewind = pathname === '/rewind'
  const isInsights = pathname === '/insights'
  const isFocus = pathname === '/focus'
  const isChat = pathname === '/chat'
  const isPersona = pathname === '/persona'
  const isPermissions = pathname === '/permissions'
  const isHelp = pathname === '/help'
  const isChatLab = pathname === '/chatlab'
  const isPeople = pathname === '/people'

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={panelClass(isHome)}>{(isHome || hydrateAll) && <HomePanel />}</div>
      <div className={panelClass(isConversations)}>
        {(isConversations || hydrateAll) && <ConversationsPanel />}
      </div>
      <div className={panelClass(isMemories)}>
        {(isMemories || hydrateAll) && <MemoriesPanel />}
      </div>
      <div className={panelClass(isSettings)}>
        {(isSettings || hydrateAll) && <SettingsPanel />}
      </div>
      <div className={panelClass(isTasks)}>{(isTasks || hydrateAll) && <TasksPanel />}</div>
      <div className={panelClass(isGoals)}>{(isGoals || hydrateAll) && <GoalsPanel />}</div>
      <div className={panelClass(isApps)}>{(isApps || hydrateAll) && <AppsPanel />}</div>
      <div className={panelClass(isRewind)}>{(isRewind || hydrateAll) && <RewindPanel />}</div>
      <div className={panelClass(isInsights)}>{(isInsights || hydrateAll) && <InsightsPanel />}</div>
      <div className={panelClass(isFocus)}>{(isFocus || hydrateAll) && <FocusPanel />}</div>
      <div className={panelClass(isChat)}>{(isChat || hydrateAll) && <ChatPanel />}</div>
      <div className={panelClass(isPersona)}>{(isPersona || hydrateAll) && <PersonaPanel />}</div>
      <div className={panelClass(isPermissions)}>
        {(isPermissions || hydrateAll) && <PermissionsPanel />}
      </div>
      <div className={panelClass(isHelp)}>{(isHelp || hydrateAll) && <HelpPanel />}</div>
      <div className={panelClass(isChatLab)}>{(isChatLab || hydrateAll) && <ChatLabPanel />}</div>
      <div className={panelClass(isPeople)}>{(isPeople || hydrateAll) && <PeoplePanel />}</div>
    </div>
  )
}
