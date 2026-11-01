{{/* Optional balanced-pool machinery divides the shared durable queue across
pool-pinned HPAs. The production cutover is a single OD HPA and never depends
on Spot capacity. */}}
{{- define "batch-pipeline-worker.instances" -}}
{{- $min := int .Values.autoscaling.minReplicas -}}
{{- $max := int .Values.autoscaling.maxReplicas -}}
{{- $readyTarget := int .Values.autoscaling.targetQueuedUnitsPerWorker -}}
{{- $chainTarget := float64 .Values.autoscaling.targetChainBusyPerWorker -}}
{{- $downStab := int .Values.autoscaling.scaleDownStabilizationSeconds -}}
{{- if and .Values.autoscaling.balancedPools.enabled (or (eq .Values.stage "prod") (eq .Values.namespace "batch_pipeline_prod") (eq .Release.Namespace "prod-omi-backend")) -}}
{{- fail "balancedPools is machinery-only outside production; production requires a single OD-pinned HPA" -}}
{{- end -}}
{{- if and .Values.autoscaling.enabled (lt $readyTarget 1) -}}
{{- fail "a qualified positive targetQueuedUnitsPerWorker is required" -}}
{{- end -}}
{{- if and .Values.autoscaling.enabled (or (le $chainTarget 0.0) (gt $chainTarget 1.0)) -}}
{{- fail "a qualified targetChainBusyPerWorker in (0,1] is required" -}}
{{- end -}}
{{- if and .Values.autoscaling.enabled (or (lt $min 1) (lt $max $min)) -}}
{{- fail "queue sampling runs in workers: minReplicas must be >=1 and maxReplicas >= minReplicas; scale-to-zero needs an independent sampler" -}}
{{- end -}}
{{- $instances := list (dict "name" .Release.Name "nodeSelector" .Values.nodeSelector "minReplicas" $min "maxReplicas" $max "capacityTarget" $readyTarget "chainTarget" $chainTarget "scaleDownStabilizationSeconds" $downStab) -}}
{{- if .Values.autoscaling.balancedPools.enabled -}}
{{- if or (not .Values.autoscaling.enabled) (lt $min 2) (ne (mod $min 2) 0) (ne (mod $max 2) 0) -}}
{{- fail "balancedPools requires autoscaling and even total minReplicas >=2 / maxReplicas" -}}
{{- end -}}
{{- $od := required "balancedPools.onDemandNodePool required" .Values.autoscaling.balancedPools.onDemandNodePool -}}
{{- $spot := required "balancedPools.spotNodePool required" .Values.autoscaling.balancedPools.spotNodePool -}}
{{- if eq $od $spot -}}{{- fail "balancedPools requires distinct on-demand and Spot node pools" -}}{{- end -}}
{{/* Both pool deployments export the same worker_release and one namespace's
     chain metric covers the whole fleet, so balanced mode doubles both
     per-worker targets: each pool HPA buys half of either demand instead of
     buying it twice (same division the shared queue count needed). */}}
{{- $instances = list
    (dict "name" .Release.Name "nodeSelector" (mergeOverwrite (deepCopy .Values.nodeSelector) (dict "cloud.google.com/gke-nodepool" $od)) "minReplicas" (div $min 2) "maxReplicas" (div $max 2) "capacityTarget" (mul $readyTarget 2) "chainTarget" (mulf $chainTarget 2.0) "scaleDownStabilizationSeconds" $downStab)
    (dict "name" (printf "%s-spot" .Release.Name) "nodeSelector" (mergeOverwrite (deepCopy .Values.nodeSelector) (dict "cloud.google.com/gke-nodepool" $spot)) "minReplicas" (div $min 2) "maxReplicas" (div $max 2) "capacityTarget" (mul $readyTarget 2) "chainTarget" (mulf $chainTarget 2.0) "scaleDownStabilizationSeconds" $downStab) -}}
{{- end -}}
{{- toYaml $instances -}}
{{- end -}}
