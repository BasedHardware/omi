import { createHash } from "node:crypto";
import budget from "./connection-budget.json";

const project = "based-hardware-dev";
const service = "omi-platform-dev";
const sqlConnection = `${project}:us-central1:omi-platform-dev-pg18`;
const fail = (): never => {
  throw new Error("invalid_release_candidate_input");
};
const object = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    return fail();
  return value as Record<string, unknown>;
};
const text = (value: unknown, pattern: RegExp): string =>
  typeof value === "string" && pattern.test(value) ? value : fail();
const integer = (value: unknown, max: number): number =>
  typeof value === "number" &&
  Number.isSafeInteger(value) &&
  value > 0 &&
  value <= max
    ? value
    : fail();

export function prepareCandidate(
  value: unknown,
  currentService: unknown | null
) {
  const input = object(value);
  const keys = [
    "mode",
    "image",
    "sourceCommit",
    "applicationId",
    "databaseGeneration",
    "accountTimezone",
    "gatewayUrl",
    "renderLane",
    "transcriptionModel",
    "secretVersions",
    "residentRevisions",
  ];
  if (Object.keys(input).some((key) => !keys.includes(key))) fail();
  const mode = input.mode;
  if (mode !== "initial-dev" && mode !== "blue-green") fail();
  const image = text(
    input.image,
    /^us-central1-docker\.pkg\.dev\/based-hardware-dev\/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$/
  );
  const sourceCommit = text(input.sourceCommit, /^[0-9a-f]{40}$/);
  const applicationId = text(input.applicationId, /^[!-~]{1,256}$/);
  const databaseGeneration = text(input.databaseGeneration, /^[0-9a-f]{64}$/);
  const accountTimezone = text(
    input.accountTimezone,
    /^[A-Za-z0-9_+/-]{1,100}$/
  );
  new Intl.DateTimeFormat("en", { timeZone: accountTimezone }).format(0);
  const gatewayUrl = new URL(text(input.gatewayUrl, /^https:\/\/[!-~]+$/));
  if (
    gatewayUrl.username ||
    gatewayUrl.password ||
    gatewayUrl.search ||
    gatewayUrl.hash
  )
    fail();
  const renderLane = text(
    input.renderLane,
    /^omi:auto:[a-z0-9][a-z0-9-]{0,95}$/
  );
  const secretVersions = object(input.secretVersions);
  const transcriptionModel = text(input.transcriptionModel, /^[a-z0-9][a-z0-9.-]{0,63}$/);
  const secretNames = {
    OMI_DATABASE_URL: "omi-platform-dev-database-url",
    OMI_CODEC_KEY_HEX: "omi-platform-dev-codec-key",
    OMI_CURSOR_KEY_HEX: "omi-platform-dev-cursor-key",
    OMI_LLM_GATEWAY_SERVICE_TOKEN: "jit-qa-gateway-token",
    OMI_TRANSCRIPTION_API_KEY: "DEEPGRAM_API_KEY",
  };
  if (Object.keys(secretVersions).length !== Object.keys(secretNames).length)
    fail();
  const secrets = Object.entries(secretNames).map(([name, secret]) => ({
    name,
    valueFrom: {
      secretKeyRef: {
        name: secret,
        key: text(secretVersions[name], /^[1-9][0-9]*$/),
      },
    },
  }));
  const configurationDigest = createHash("sha256")
    .update(
      JSON.stringify({
        image,
        sourceCommit,
        applicationId,
        databaseGeneration,
        accountTimezone,
        gatewayUrl: gatewayUrl.href,
        renderLane,
        transcriptionModel,
        secrets,
      })
    )
    .digest("hex");
  const revision = `${service}-r-${configurationDigest.slice(0, 16)}`;
  if (!Array.isArray(input.residentRevisions)) fail();
  const residents = (input.residentRevisions as unknown[]).map((raw) => {
    const item = object(raw);
    return {
      name: text(item.name, /^omi-platform-dev-[a-z0-9-]+$/),
      maxInstances: integer(item.maxInstances, budget.revision_instance_cap),
      poolMax: integer(item.poolMax, budget.api_pool_max),
    };
  });
  if (
    new Set(residents.map((item) => item.name)).size !== residents.length ||
    residents.some((item) => item.name === revision)
  )
    fail();
  if (residents.length + 1 > budget.concurrent_revisions) fail();
  let traffic: Array<{ revisionName: string; percent: number; tag?: string }>;
  let baselineResourceVersion: string | null = null;
  if (mode === "initial-dev") {
    if (currentService !== null || residents.length !== 0) fail();
    traffic = [{ revisionName: revision, percent: 100 }];
  } else {
    const current = object(currentService);
    const metadata = object(current.metadata);
    const spec = object(current.spec);
    const status = object(current.status);
    if (
      metadata.name !== service ||
      !["based-hardware-dev", "1031333818730"].includes(
        String(metadata.namespace)
      )
    )
      fail();
    baselineResourceVersion = text(metadata.resourceVersion, /^[!-~]{1,256}$/);
    if (!Array.isArray(spec.traffic) || spec.traffic.length === 0) fail();
    traffic = (spec.traffic as unknown[]).map((raw) => {
      const item = object(raw);
      const revisionName = text(
        item.latestRevision === true
          ? status.latestReadyRevisionName
          : item.revisionName,
        /^omi-platform-dev-[a-z0-9-]+$/
      );
      if (!residents.some((resident) => resident.name === revisionName)) fail();
      const percent = item.percent ?? 0;
      if (
        typeof percent !== "number" ||
        !Number.isInteger(percent) ||
        percent < 0 ||
        percent > 100
      )
        return fail();
      const tag =
        item.tag === undefined
          ? undefined
          : text(item.tag, /^[a-z][a-z0-9-]{0,62}$/);
      return {
        revisionName,
        percent,
        ...(tag !== undefined && tag !== "candidate" ? { tag } : {}),
      };
    });
    if (traffic.reduce((sum, item) => sum + item.percent, 0) !== 100) fail();
    traffic.push({ revisionName: revision, percent: 0, tag: "candidate" });
  }
  const connections =
    residents.reduce((sum, item) => sum + item.maxInstances * item.poolMax, 0) +
    budget.api_pool_max * budget.revision_instance_cap +
    budget.job_connections +
    budget.migration_reserve +
    budget.operator_reserve;
  if (
    connections > budget.approved_connections ||
    budget.approved_connections >=
      budget.database_max_connections - budget.provider_reserved_connections
  )
    fail();
  const env = {
    OMI_FIREBASE_PROJECT_ID: project,
    OMI_APPLICATION_ID: applicationId,
    OMI_DATABASE_GENERATION_DIGEST: databaseGeneration,
    OMI_ACCOUNT_TIMEZONE: accountTimezone,
    OMI_LLM_GATEWAY_URL: gatewayUrl.href,
    OMI_MEMORY_RENDER_LANE: renderLane,
    OMI_TRANSCRIPTION_MODEL: transcriptionModel,
    OMI_DATABASE_SOCKET_DIRECTORY: `/cloudsql/${sqlConnection}`,
  };
  return {
    release: {
      project,
      service,
      mode,
      sourceCommit,
      image,
      revision,
      baselineResourceVersion,
      connections,
      poolMax: budget.api_pool_max,
      maxInstances: budget.revision_instance_cap,
      residentRevisions: residents,
    },
    manifest: {
      apiVersion: "serving.knative.dev/v1",
      kind: "Service",
      metadata: {
        name: service,
        namespace: project,
        ...(baselineResourceVersion
          ? { resourceVersion: baselineResourceVersion }
          : {}),
        annotations: {
          "run.googleapis.com/ingress": "all",
          "run.googleapis.com/invoker-iam-disabled": "false",
        },
      },
      spec: {
        template: {
          metadata: {
            name: revision,
            annotations: {
              "autoscaling.knative.dev/minScale": "0",
              "autoscaling.knative.dev/maxScale": String(
                budget.revision_instance_cap
              ),
              "run.googleapis.com/cloudsql-instances": sqlConnection,
              "run.googleapis.com/execution-environment": "gen2",
            },
          },
          spec: {
            serviceAccountName:
              "omi-platform-dev-runtime@based-hardware-dev.iam.gserviceaccount.com",
            containerConcurrency: 2,
            timeoutSeconds: 150,
            containers: [
              {
                image,
                ports: [{ containerPort: 8080 }],
                command: ["bun"],
                args: ["production-server.js"],
                resources: { limits: { cpu: "1", memory: "512Mi" } },
                env: [
                  ...Object.entries(env).map(([name, value]) => ({
                    name,
                    value,
                  })),
                  ...secrets,
                ],
                startupProbe: {
                  httpGet: { path: "/ready", port: 8080 },
                  periodSeconds: 10,
                  timeoutSeconds: 5,
                  failureThreshold: 12,
                },
              },
            ],
          },
        },
        traffic,
      },
    },
  };
}

if (import.meta.main) {
  try {
    const [inputFile, outputDirectory, ...extra] = Bun.argv.slice(2);
    if (!inputFile || !outputDirectory || extra.length)
      throw new Error("usage");
    const input: unknown = await Bun.file(inputFile).json();
    const observed = Bun.spawn(
      [
        "gcloud",
        "run",
        "services",
        "list",
        "--project=based-hardware-dev",
        "--region=us-central1",
        "--filter=metadata.name=omi-platform-dev",
        "--format=json",
      ],
      { stdout: "pipe", stderr: "pipe" }
    );
    const [output, , code] = await Promise.all([
      new Response(observed.stdout).text(),
      new Response(observed.stderr).text(),
      observed.exited,
    ]);
    if (code !== 0) throw new Error("cloud_run_observation_failed");
    const services: unknown = JSON.parse(output);
    if (!Array.isArray(services) || services.length > 1) fail();
    const current: unknown | null = (services as unknown[])[0] ?? null;
    const candidate = prepareCandidate(input, current);
    const { mkdir, writeFile } = await import("node:fs/promises");
    await mkdir(outputDirectory, { recursive: true, mode: 0o700 });
    await writeFile(
      `${outputDirectory}/service.json`,
      JSON.stringify(candidate.manifest, null, 2),
      { mode: 0o600, flag: "wx" }
    );
    await writeFile(
      `${outputDirectory}/release.json`,
      JSON.stringify(candidate.release, null, 2),
      { mode: 0o600, flag: "wx" }
    );
    console.log(
      "Prepared candidate files; no deployment or IAM changes performed."
    );
  } catch {
    console.error(
      "Candidate preparation failed. Supply validated release inputs and a new output directory; Cloud Run observation must succeed."
    );
    process.exitCode = 1;
  }
}
