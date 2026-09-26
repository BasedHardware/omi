-- Omi GCP unit-cost component classifier.
-- Source: `based-hardware.gcp_billing_export.gcp_billing_export_resource_v1_01B287_9348DC_02D256`
-- (the 01B896_918303_539138 account is the PREDECESSOR account; it has no data after 2026-07-01.)
--
-- Requires these expressions in scope (define in a WITH or repeat inline):
--   node_pool  = (SELECT l.value FROM UNNEST(labels) l WHERE l.key='goog-k8s-node-pool-name' LIMIT 1)
--   res_name   = IFNULL(resource.global_name, resource.name)
--
-- Ordering is load-bearing:
--   * Cloud Run is matched by RESOURCE before Compute Engine is matched by SERVICE, because
--     "Compute Flexible Committed Use Discounts - 3 Year" rows carry service.description='Compute Engine'
--     while their resource is a Cloud Run service (goog-originating-service-id=152E-C115-5142).
--   * Cloud Storage is matched before the generic network SKU rule so bucket replication/egress
--     stays with the bucket that caused it.
--   * Firestore is matched by SKU, never by service name (it bills under service 'App Engine').

CASE
  ---------------------------------------------------------------- one-off charges
  -- Injected from one_time_events.json by pull_gcp.py. Dated, resource-scoped rules only.
  -- These land in their own `one_time_*` component, are reported with method='one_time',
  -- and are excluded from every per-user allocation pool.
{{ONE_TIME_RULES}}
  ---------------------------------------------------------------- overhead
  WHEN service.description = 'BigQuery' THEN 'bigquery'

  ---------------------------------------------------------------- firestore
  WHEN sku.description = 'Cloud Firestore Read Ops' THEN 'firestore_reads'
  WHEN LOWER(sku.description) LIKE '%firestore%'
    OR service.description = 'Cloud Firestore'                     THEN 'firestore_other'

  ---------------------------------------------------------------- model serving
  -- 5-GSU gemini-flash flat reservation, ~$298/day net, unit = seconds
  WHEN sku.description LIKE 'Vertex AI: Provisioned Throughput%'   THEN 'vertex_pt_reservation'
  WHEN LOWER(sku.description) LIKE '%embedding%'
    OR LOWER(sku.description) LIKE '%embedcontent%'                THEN 'embeddings'
  WHEN service.description IN ('Vertex AI','Gemini API',
                               'Generative Language API',
                               'Vertex AI Search','Vertex AI Agent Builder')
    OR LOWER(sku.description) LIKE '%gemini%'
    OR LOWER(sku.description) LIKE '%generative%'                  THEN 'vertex_paygo'

  ---------------------------------------------------------------- simple service buckets
  WHEN service.description IN ('Translate','Cloud Translation')    THEN 'translate'
  WHEN service.description IN ('Cloud Logging','Cloud Monitoring','Cloud Trace',
                               'Stackdriver Logging','Stackdriver Monitoring',
                               'Cloud Profiler','Error Reporting')  THEN 'logging_monitoring'
  WHEN service.description = 'Cloud Pub/Sub'                        THEN 'pubsub'

  ---------------------------------------------------------------- storage (before network rule)
  WHEN service.description IN ('Cloud Storage','Storage Insights')
       AND ( IFNULL(resource.global_name, resource.name) LIKE '%/buckets/omi-private-cloud-sync%'
          OR IFNULL(resource.global_name, resource.name) LIKE '%/buckets/omi-dev-private-cloud-sync%'
          OR IFNULL(resource.global_name, resource.name) LIKE '%/buckets/syncing-local%' )
                                                                    THEN 'storage_audio'
  WHEN service.description IN ('Cloud Storage','Storage Insights')  THEN 'storage_other'

  ---------------------------------------------------------------- Cloud Run (before Compute Engine)
  WHEN IFNULL(resource.global_name, resource.name) LIKE '//run.googleapis.com/%/services/desktop-backend'
                                                                    THEN 'cloud_run_desktop_backend'
  WHEN IFNULL(resource.global_name, resource.name) LIKE '//run.googleapis.com/%'
    OR IFNULL(resource.global_name, resource.name) LIKE '//cloudfunctions.googleapis.com/%'
    OR service.description IN ('Cloud Run','Cloud Run Functions','Cloud Functions')
                                                                    THEN 'cloud_run_other'

  ---------------------------------------------------------------- network
  WHEN service.description IN ('Networking','Network Security','Cloud DNS',
                               'Network Topology','Cloud Load Balancing','Network Intelligence Center')
                                                                    THEN 'network'
  WHEN service.description = 'Compute Engine'
       AND ( sku.description LIKE 'Network%'
          OR sku.description LIKE '%Data Transfer%'
          OR sku.description LIKE '%External IP%'
          OR sku.description LIKE '%Forwarding Rule%'
          OR sku.description LIKE '%Load Balanc%' )                 THEN 'network'

  ---------------------------------------------------------------- ASR / STT GPU fleet
  WHEN REGEXP_CONTAINS(
         IFNULL((SELECT l.value FROM UNNEST(labels) l
                  WHERE l.key='goog-k8s-node-pool-name' LIMIT 1),''),
         r'(?i)parakeet|nllb|diariz|vad|(^|-)asr|hpfasr|deepgram|whisper|stt')
                                                                    THEN 'asr_gpu_fleet'
  WHEN service.description IN ('Compute Engine','Kubernetes Engine')
       AND ( LOWER(sku.description) LIKE '%gpu%'
          OR LOWER(sku.description) LIKE '%nvidia%'
          OR sku.description LIKE 'G2 Instance%' )                  THEN 'asr_gpu_fleet'

  ---------------------------------------------------------------- remaining compute
  WHEN service.description IN ('Compute Engine','Kubernetes Engine',
                               'Deep Learning VM','Container Registry Vulnerability Scanning')
                                                                    THEN 'gke_other_compute'

  ELSE 'other_gcp'
END AS component,

CASE
  WHEN <component> = 'vertex_pt_reservation'                        THEN 'fixed'
  WHEN <component> IN ('embeddings','cloud_run_desktop_backend')    THEN 'desktop'
  WHEN <component> IN ('asr_gpu_fleet','storage_audio')             THEN 'mobile'
  WHEN <component> = 'bigquery'                                     THEN 'overhead'
  ELSE 'shared'
END AS platform_structural
