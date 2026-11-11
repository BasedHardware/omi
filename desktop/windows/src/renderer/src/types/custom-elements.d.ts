import type { HTMLAttributes, Ref } from 'react'

declare global {
  namespace JSX {
    interface IntrinsicElements {
      'pose-viewer': HTMLAttributes<HTMLElement> & {
        src?: string | ArrayBuffer | null
        renderer?: string
        ref?: Ref<HTMLElement>
      };
    }
  }
}

declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'pose-viewer': HTMLAttributes<HTMLElement> & {
        src?: string | ArrayBuffer | null
        renderer?: string
        ref?: Ref<HTMLElement>
      }
    }
  }
}

export {}
