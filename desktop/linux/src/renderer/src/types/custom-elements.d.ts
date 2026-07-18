import type { HTMLAttributes, Ref } from 'react'

declare global {
  namespace JSX {
    interface IntrinsicElements {
      'pose-viewer': HTMLAttributes<HTMLElement> & {
        src?: string | ArrayBuffer | null
        renderer?: string
        ref?: Ref<any>
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
        ref?: Ref<any>
      }
    }
  }
}

export {}
