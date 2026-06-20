import { Component, type ErrorInfo, type ReactNode } from 'react'
import {
  errorToObservabilityPayload,
  sanitizeObservabilityValue
} from '../../../../shared/observabilityRedaction'
import { captureRendererException } from '../../lib/observability'

type Props = {
  children: ReactNode
  // Rendered in place of the subtree when it throws. Kept simple (no retry) —
  // callers pass a quiet placeholder so a failure degrades rather than crashes.
  fallback?: ReactNode
  // Optional label so the logged error says which boundary caught it.
  label?: string
}
type State = { failed: boolean }

// Generic render error boundary. A throw anywhere below (including a failed
// React.lazy chunk load or a WebGL/three init failure) is contained here, so it
// degrades the wrapped subtree to `fallback` instead of unmounting the whole app.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    captureRendererException('renderer.react_error_boundary', error, {
      label: this.props.label,
      componentStack: info.componentStack
    })
    console.error(
      `[ErrorBoundary${this.props.label ? `:${this.props.label}` : ''}]`,
      errorToObservabilityPayload(error),
      sanitizeObservabilityValue({ componentStack: info.componentStack })
    )
  }

  render(): ReactNode {
    if (this.state.failed) return this.props.fallback ?? null
    return this.props.children
  }
}
