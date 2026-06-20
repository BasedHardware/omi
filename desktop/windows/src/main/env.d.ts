/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly MAIN_VITE_GOOGLE_CLIENT_ID?: string
  readonly MAIN_VITE_GOOGLE_CLIENT_SECRET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare namespace NodeJS {
  interface ProcessEnv {
    /** '1' enables bench mode: run the fixed workload after load, then quit. */
    OMI_BENCH?: string
    /** '1' enables animation bench: record startup-animation jank, then quit
     *  (skips the DB/IPC workload so it can't pollute frame timing). */
    OMI_ANIM_BENCH?: string
    /** Absolute path to the perf JSONL log. When unset, perf marks are no-ops. */
    OMI_PERF_LOG?: string
    /** Override the SQLite file path (used to point at the throwaway bench DB). */
    OMI_DB_PATH?: string
    /** Force hosted/cloud STT even when a local Parakeet runtime is healthy. */
    OMI_FORCE_CLOUD_STT?: string
    /** Test hook mirroring macOS: make local Parakeet report unavailable. */
    OMI_FORCE_PARAKEET_FAIL?: string
    /** Disable the Windows local Parakeet STT adapter entirely. */
    OMI_LOCAL_STT_DISABLED?: string
    /** Base URL for the local Parakeet service, e.g. http://127.0.0.1:8765. */
    OMI_LOCAL_PARAKEET_URL?: string
    /** Alias for OMI_LOCAL_PARAKEET_URL. */
    OMI_PARAKEET_URL?: string
    /** Test/dev override for machines where nvidia-smi is unavailable. */
    OMI_LOCAL_STT_ASSUME_NVIDIA?: string
    /** Allow a healthy Parakeet runtime even when nvidia-smi is absent. */
    OMI_LOCAL_STT_ALLOW_NON_NVIDIA?: string
    /** The desktop-automation bridge (snapshot → plan → approve → execute real
     *  Windows UI actions) is ON by default. Set OMI_AUTOMATION='0' to disable it
     *  (kill-switch for builds that don't want the experimental feature). */
    OMI_AUTOMATION?: string
  }
}
