{{/* Optional balanced-pool machinery divides the shared durable queue across
pool-pinned HPAs. The production cutover is a single OD HPA and never depends
on Spot capacity. */}}
{{- define "batch-pipeline-worker.instances" -}}
{{- $min := int .Values.autoscaling.minReplicas -}}
{{- $max := int .Values.autoscaling.maxReplicas -}}
{{- $target := int .Values.autoscaling.targetQueuedUnitsPerWorker -}}
{{- if and .Values.autoscaling.balancedPools.enabled (or (eq .Values.stage "prod") (eq .Values.namespace "batch_pipeline_prod") (eq .Release.Namespace "prod-omi-backend")) -}}
{{- fail "balancedPools is machinery-only outside production; production requires a single OD-pinned HPA" -}}
{{- end -}}
{{- if and .Values.autoscaling.enabled (lt $target 1) -}}
{{- fail "a qualified positive targetQueuedUnitsPerWorker is required" -}}
{{- end -}}
{{- if and .Values.autoscaling.enabled (or (lt $min 1) (lt $max $min)) -}}
{{- fail "queue sampling runs in workers: minReplicas must be >=1 and maxReplicas >= minReplicas; scale-to-zero needs an independent sampler" -}}
{{- end -}}
{{- $instances := list (dict "name" .Release.Name "nodeSelector" .Values.nodeSelector "minReplicas" $min "maxReplicas" $max "capacityTarget" $target) -}}
{{- if .Values.autoscaling.balancedPools.enabled -}}
{{- if or (not .Values.autoscaling.enabled) (lt $min 2) (ne (mod $min 2) 0) (ne (mod $max 2) 0) -}}
{{- fail "balancedPools requires autoscaling and even total minReplicas >=2 / maxReplicas" -}}
{{- end -}}
{{- $od := required "balancedPools.onDemandNodePool required" .Values.autoscaling.balancedPools.onDemandNodePool -}}
{{- $spot := required "balancedPools.spotNodePool required" .Values.autoscaling.balancedPools.spotNodePool -}}
{{- if eq $od $spot -}}{{- fail "balancedPools requires distinct on-demand and Spot node pools" -}}{{- end -}}
{{- $instances = list
    (dict "name" .Release.Name "nodeSelector" (mergeOverwrite (deepCopy .Values.nodeSelector) (dict "cloud.google.com/gke-nodepool" $od)) "minReplicas" (div $min 2) "maxReplicas" (div $max 2) "capacityTarget" (mul $target 2))
    (dict "name" (printf "%s-spot" .Release.Name) "nodeSelector" (mergeOverwrite (deepCopy .Values.nodeSelector) (dict "cloud.google.com/gke-nodepool" $spot)) "minReplicas" (div $min 2) "maxReplicas" (div $max 2) "capacityTarget" (mul $target 2)) -}}
{{- end -}}
{{- with .Values.borrowedNodePools -}}
{{- if .enabled -}}
{{- $own := index $.Values.nodeSelector "cloud.google.com/gke-nodepool" | default "" -}}
{{- $pools := .pools | default list -}}
{{- if or (not $.Values.autoscaling.enabled) $.Values.autoscaling.balancedPools.enabled (not $own) (empty $pools) -}}
{{- fail "borrowedNodePools needs autoscaling, no balancedPools, a nodeSelector pool and a non-empty pools list" -}}
{{- end -}}
{{- range $pools -}}
{{- if or (eq . $own) (contains "spot" .) -}}
{{- fail "borrowedNodePools.pools must be other on-demand pools" -}}
{{- end -}}
{{- end -}}
{{- $grace := int .terminationGracePeriodSeconds -}}
{{- if or (lt $grace 1) (gt $grace 300) -}}
{{- fail "borrowedNodePools.terminationGracePeriodSeconds must be in [1, 300] so the owner gets its node back fast" -}}
{{- end -}}
{{- $max := int .maxReplicas -}}
{{- if lt $max 1 -}}{{- fail "borrowedNodePools.maxReplicas must be >= 1" -}}{{- end -}}
{{- /* Its own HPA on the shared queue: at most maxReplicas extra workers,
on nodes the owner left free. The OD instance above is unchanged. */ -}}
{{- $instances = append $instances (dict
    "name" (printf "%s-borrow" $.Release.Name)
    "nodeSelector" (omit $.Values.nodeSelector "cloud.google.com/gke-nodepool" "service")
    "borrowedPools" $pools
    "terminationGracePeriodSeconds" $grace
    "minReplicas" 1 "maxReplicas" $max "baselineReplicas" 1
    "capacityTarget" $target) -}}
{{- end -}}
{{- end -}}
{{- toYaml $instances -}}
{{- end -}}
