/**
 * Build one command's child environment without changing the caller.
 *
 * Provenance deliberately treats OMI_CORE_ROOT as the repository root. A
 * small set of legacy generators interpret the same name as the nested core
 * directory, so lane steps that execute them carry a scoped override. Keeping
 * the merge here makes that exception observable and prevents it from leaking
 * into later steps or receipt stamping.
 */
export function laneStepEnvironment({ callerEnv, stepEnv = undefined, l3RunDir = null }) {
  const childEnv = { ...callerEnv, ...(stepEnv ?? {}) };
  if (l3RunDir !== null) childEnv.OMI_DEV_STACK_RUNDIR = l3RunDir;
  return childEnv;
}
