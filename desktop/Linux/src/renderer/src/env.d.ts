/// <reference types="vite/client" />

import type { OmiBridge } from '../../preload/index'

declare global {
  interface Window {
    omi: OmiBridge
  }
}

declare module '*.png' {
  const src: string
  export default src
}

declare module '*.webp' {
  const src: string
  export default src
}

export {}
