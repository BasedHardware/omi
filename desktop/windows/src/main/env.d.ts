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
    /** Test/dev override for machines where nvidia-smi is unavailable. */
    OMI_LOCAL_STT_ASSUME_NVIDIA?: string
    /** Test/dev escape hatch: install CPU Parakeet when nvidia-smi is absent. */
    OMI_LOCAL_STT_ALLOW_NON_NVIDIA?: string
    /** Test/dev escape hatch: exercise installer logic outside Windows. */
    OMI_LOCAL_STT_ALLOW_NON_WINDOWS?: string
    /** Test/dev override for the app-owned Parakeet runtime cache root. */
    OMI_LOCAL_STT_RUNTIME_ROOT?: string
    /** Test/dev override for runtime flavor; production auto-selects CUDA on NVIDIA Windows. */
    OMI_LOCAL_STT_RUNTIME_VARIANT?: 'cuda' | 'cpu'
    /** Test/dev override for parakeet.cpp release version, e.g. v0.3.2. */
    OMI_LOCAL_STT_PARAKEET_CPP_VERSION?: string
    /** Test/dev override for parakeet.cpp release asset base URL. */
    OMI_LOCAL_STT_RELEASE_BASE?: string
    /** Test/dev override for the GGUF model filename. */
    OMI_LOCAL_STT_MODEL_NAME?: string
    /** Test/dev override for the GGUF model URL. */
    OMI_LOCAL_STT_MODEL_URL?: string
    /** Disable the Windows local Kokoro TTS adapter entirely. */
    OMI_LOCAL_TTS_DISABLED?: string
    /** Test/dev escape hatch: exercise Kokoro status/synthesis logic outside Windows. */
    OMI_LOCAL_TTS_ALLOW_NON_WINDOWS?: string
    /** Test/dev override for the app-owned Kokoro runtime/model cache root. */
    OMI_LOCAL_TTS_RUNTIME_ROOT?: string
    /** Test/dev override for the Hugging Face Kokoro ONNX model id. */
    OMI_LOCAL_TTS_MODEL_ID?: string
    /** Test/dev override for the Kokoro voice id, e.g. af_heart. */
    OMI_LOCAL_TTS_VOICE?: string
    /** Test/dev override for Kokoro ONNX quantization. Defaults to q8. */
    OMI_LOCAL_TTS_DTYPE?: 'fp32' | 'fp16' | 'q8' | 'q4' | 'q4f16'
    /** The desktop-automation bridge (snapshot → plan → approve → execute real
     *  Windows UI actions) is ON by default. Set OMI_AUTOMATION='0' to disable it
     *  (kill-switch for builds that don't want the experimental feature). */
    OMI_AUTOMATION?: string
  }
}
