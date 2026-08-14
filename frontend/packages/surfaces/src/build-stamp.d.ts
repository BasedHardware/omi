// LIFECYCLE: permanent
//
// Ambient type for the build-time provenance stamp injected by vite.config.ts via
// `define`. Shape matches `worktreeStamp()`'s success return
// (integration/lib/provenance.mjs) OR its `unavailable` failure shape — never assume
// the success fields are present without checking.
declare const __OMI_BUILD_STAMP__:
  | {
      readonly schema: number;
      readonly repo: string;
      readonly artifact: string;
      readonly branch: string;
      readonly commit: string;
      readonly treeHash: string;
      readonly dirty: boolean;
      readonly roots: readonly string[];
      readonly stampedAt: string;
    }
  | {
      readonly schema: number;
      readonly repo: string;
      readonly artifact: string;
      readonly unavailable: string;
    };
