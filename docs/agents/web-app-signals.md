# web/app — moonshine signals

The Home hub's data layer in `web/app` runs on [`@tschk/moonshine`](https://www.npmjs.com/package/@tschk/moonshine)'s
signal kernel rather than React state. This page explains what to use and why,
so the next person does not reintroduce the pattern it replaced.

## What to use

| Need | Use |
|---|---|
| Read something from the API | `useAsyncResource(key, fetcher)` (`web/app/src/hooks/useAsyncResource.ts`) |
| A list that is also written optimistically | A signal store — see `createGoalsStore` in `web/app/src/hooks/useGoals.ts` |
| Subscribe a component to a raw signal | `useSignal` / `useResource` from `@tschk/moonshine-react` |

`useAsyncResource` is keyed: change the key and it refetches, pass `null` and it
holds without fetching. `fetcher` is read when the request runs, so it does not
need to be memoized.

## Why signals here

`createResource` keeps a request and its loading/error state in signals outside
React; components subscribe through `useSyncExternalStore`. Two consequences:

- **No React state is set from an effect.** The `react-hooks/set-state-in-effect`
  rule — 48 of the remaining lint errors elsewhere in this app — cannot arise in
  signal-backed code. A response arriving after unmount updates a signal nobody
  reads, so the hand-rolled `mounted` flag guard is unnecessary rather than
  merely correct.
- **Rollback can read the committed value synchronously.** `signal.peek()`
  returns the current value at call time. Capturing the pre-write value inside a
  React state updater does not work: React runs updaters during the next render,
  which is after a rejected request's `catch` has already run, so the captured
  value is still `undefined` and the rollback silently does nothing. That was a
  real bug, caught by `useGoals.test.tsx`.

Start the load from an effect, not from the store factory or `immediate: true`.
`useMemo` may run more than once per commit (StrictMode renders twice), and
fetching in the factory fires one request per discarded store. Writing signals
from an effect is fine — it is not React state.

## Which package to import

Import the signal kernel from `@tschk/moonshine` and the React bridges
(`useSignal`, `useResource`) from `@tschk/moonshine-react`.

Historical note: while `web/app` was still on Next, `@tschk/moonshine-react`
could not be imported at all — its entry pulls in an SSR renderer and island
hydration that call `import(specifier)` with a runtime variable, which Turbopack
cannot resolve, so the build failed with module-not-found. That forced a local
`useSyncExternalStore` shim. Moonshine's own compiler handles those dynamic
imports, so the shim is gone and the official bridge is used directly.
