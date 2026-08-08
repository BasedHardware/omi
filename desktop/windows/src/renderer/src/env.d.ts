/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public share origin for conversation links (#4339). Default https://h.omi.me */
  readonly VITE_OMI_SHARE_BASE_URL?: string
}
