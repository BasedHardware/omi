import { registerHubHomeWidgets } from './hubHomeWidgetsSlot'
import { HomeGoalsChips } from '../HomeGoalsChips'

// Register the focused-goals chip row as the resting Hub's home-widget row.
//
// EAGER (unlike connections/register.ts's React.lazy): HomeHub mounts this widget
// directly in the resting cluster, with no Suspense boundary, so a lazy component
// would throw on first render. The module is small and its deps (goal libs, api
// client, firebase) are already in the main bundle, so eager import costs nothing
// extra. The widget only *fetches* when the hub actually mounts it on the main
// window — registration alone does no work.
registerHubHomeWidgets(HomeGoalsChips)
