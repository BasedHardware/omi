import { registerHubHomeWidgets } from './hubHomeWidgetsSlot'
import { registerHubKnows } from './hubKnowsSlot'
import { CanonicalGoalsChips } from '../goals/CanonicalGoalsChips'
import { HomeKnowsList } from '../knows/HomeKnowsList'

// Register the goals chip row and the knows list as the resting Hub's
// intelligence surfaces.
//
// EAGER (unlike connections/register.ts's React.lazy): HomeHub mounts these
// directly in the resting cluster, with no Suspense boundary, so a lazy
// component would throw on first render. The modules are small and their deps
// (goal libs, api client, firebase) are already in the main bundle, so eager
// import costs nothing extra. The widgets only *fetch* when the hub actually
// mounts them on the main window — registration alone does no work.
//
// CanonicalGoalsChips renders the canonical FOCUSED subset for accounts inside
// the intelligence rollout and falls back to the legacy HomeGoalsChips row for
// everyone else, so registration is safe across the rollout boundary.
registerHubHomeWidgets(CanonicalGoalsChips)
registerHubKnows(HomeKnowsList)
