"""Validate a proposed hardware job without executing any hardware or commands.
A plan never grants permission; live reconciliation remains mandatory.
"""
from pathlib import Path
import argparse,hashlib,json,math,re
from artifact_preflight import evaluate,digest,strict_json

def plan(job_path,profile_path,contract_path):
    j=Path(job_path);p=Path(profile_path);job_bytes=j.read_bytes();profile_bytes=p.read_bytes();job=strict_json(job_bytes);profile=strict_json(profile_bytes);errors=[]
    if type(job) is not dict or type(profile) is not dict:raise ValueError('job and profile must be objects')
    def need(condition,code):
        if not condition:errors.append(code)
    need(type(job.get('schema')) is int and job.get('schema')==1,'schema')
    allowed={'schema','operation','probe_serial','external_target_identity_sha256','deadline_seconds','on_failure','retries','power_cycle','reset_after_verify','lease_scope','evidence_policy','artifact_manifest'}
    need(set(job)<=allowed,'unknown_job_fields')
    need(job.get('operation') in ('reviewed_swd_app_only','reviewed_swd_baseline_restore'),'operation_not_reviewed')
    serial=lambda s:type(s) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}',s) is not None
    need(set(profile)<={'probe_serial','external_target_identity_sha256'},'unknown_profile_fields')
    need(serial(profile.get('probe_serial')) and serial(job.get('probe_serial')) and job.get('probe_serial')==profile.get('probe_serial'),'probe_mismatch')
    target=profile.get('external_target_identity_sha256','')
    need(type(target) is str and len(target)==64 and all(c in '0123456789abcdef' for c in target) and job.get('external_target_identity_sha256')==target,'external_identity_missing_or_mismatch')
    timeout=job.get('deadline_seconds')
    need(type(timeout) in (int,float) and math.isfinite(timeout) and 0<timeout<=300,'unbounded_deadline')
    need(job.get('on_failure')=='stop_preserve_receipts','failure_policy')
    need(type(job.get('retries')) is int and job.get('retries')==0,'automatic_retries_forbidden')
    need(job.get('power_cycle') is False,'power_cycle_not_qualified')
    need(job.get('reset_after_verify') is False,'reset_requires_separate_reviewed_step')
    need(job.get('lease_scope')=='whole_cv1_bench','exclusive_scope_required')
    need(job.get('evidence_policy')=='local_unique_no_truncate','evidence_policy')
    need(not any(k in job for k in ('command','shell','script','sign','publish','deploy','recover','unlock','erase_all')),'arbitrary_or_irreversible_action')
    artifact=None
    try:
        path=(j.parent/job['artifact_manifest']).resolve()
        need(j.parent.resolve() in path.parents,'artifact_manifest_path_escape')
        if j.parent.resolve() in path.parents:
            artifact=evaluate(path,contract_path)
            need(artifact['eligible_for_live_identity_gate'],'offline_preflight_failed')
            need(artifact.get('validated_operation')==job.get('operation'),'operation_role_mismatch')
    except (KeyError,OSError,TypeError,ValueError):errors.append('artifact_manifest_invalid')
    return dict(schema=1,layer='offline hardware-job/release-policy dry run',job_sha256=digest(job_bytes),profile_sha256=digest(profile_bytes),plan_valid=not errors,execution_enabled=False,hardware_authorized=False,release_authorized=False,errors=errors,artifact_preflight=artifact,required_live_steps=['Acquire existing whole-bench exclusive lease; refuse another owner or uncertain previous operation.','Re-enumerate pinned probe and read external target factory identity; compare hash, never probe serial alone.','Verify target route and standing-power assumptions; no automatic power cycles.','Rehash artifacts and exact baseline contract immediately before reviewed command.','Bound each command, preserve unique receipts, stop on first protection/error/timeout; reconcile uncertain outcome before retry.'],warning='Overwrite-only MCUboot has no automatic old-image revert. SWD restore is not OTA rollback. This planner cannot sign, publish, deploy or operate a device.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job');p.add_argument('--profile',required=True);p.add_argument('--contract',required=True);a=p.parse_args()
    try:r=plan(a.job,a.profile,a.contract)
    except (OSError,ValueError,KeyError,TypeError,OverflowError,RecursionError) as ex:r=dict(plan_valid=False,execution_enabled=False,hardware_authorized=False,errors=[str(ex)])
    print(json.dumps(r,indent=2));return 0 if r['plan_valid'] else 2
if __name__=='__main__':raise SystemExit(main())
