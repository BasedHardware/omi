import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
  children: ReactNode
  // Rendered in place of the subtree when it throws. Kept simple (no retry) —
  // callers pass a quiet placeholder so a failure degrades rather than crashes.
  fallback?: ReactNode
  // Optional label so the logged error says which boundary caught it.
  label?: string
  // When any value in this array changes, a failed boundary re-attempts its
  // subtree. Pass a stable signal (e.g. the data that drives the child), NOT
  // `children`, whose element identity changes on every render.
  resetKeys?: unknown[]
}
type State = { failed: boolean }

// Shallow array compare: did any resetKey change between renders?
function resetKeysChanged(prev: unknown[] | undefined, next: unknown[] | undefined): boolean {
  if (prev === next) return false
  if (!prev || !next) return prev !== next
  if (prev.length !== next.length) return true
  return prev.some((v, i) => !Object.is(v, next[i]))
}

// Generic render error boundary. A throw anywhere below (including a failed
// React.lazy chunk load or a WebGL/three init failure) is contained here, so it
// degrades the wrapped subtree to `fallback` instead of unmounting the whole app.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(
      `[ErrorBoundary${this.props.label ? `:${this.props.label}` : ''}]`,
      error,
      info.componentStack
    )
  }

  componentDidUpdate(prevProps: Props): void {
    // Re-attempt the subtree only when the caller's resetKeys change, NOT on every
    // re-render. The `children` element identity changes each render, so keying on
    // it would churn throw/catch/log for a persistent error. A transient failure
    // (WebGL context loss, a one-time lazy-chunk rejection) recovers when the keyed
    // data next changes, instead of leaving a blank pane forever.
    if (this.state.failed && resetKeysChanged(prevProps.resetKeys, this.props.resetKeys)) {
      this.setState({ failed: false })
    }
  }

  render(): ReactNode {
    if (this.state.failed) return this.props.fallback ?? null
    return this.props.children
  }
}
