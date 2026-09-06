import { expect, test } from "bun:test";
import { prepareCandidate } from "./release-candidate";

const input = () => ({
  mode: "initial-dev",
  image: `us-central1-docker.pkg.dev/based-hardware-dev/platform/runtime@sha256:${"a".repeat(
    64
  )}`,
  sourceCommit: "b".repeat(40),
  applicationId: "dev-test-application",
  databaseGeneration: "c".repeat(64),
  accountTimezone: "UTC",
  gatewayUrl: "https://gateway.example.test",
  renderLane: "omi:auto:memory-render",
  transcriptionModel: "nova-3",
  secretVersions: {
    OMI_DATABASE_URL: "1",
    OMI_CODEC_KEY_HEX: "2",
    OMI_CURSOR_KEY_HEX: "3",
    OMI_LLM_GATEWAY_SERVICE_TOKEN: "4",
    OMI_TRANSCRIPTION_API_KEY: "5",
  },
  residentRevisions: [] as Array<{
    name: string;
    maxInstances: number;
    poolMax: number;
  }>,
});
const current = () => ({
  metadata: {
    name: "omi-platform-dev",
    namespace: "based-hardware-dev",
    resourceVersion: "123",
  },
  spec: { traffic: [{ latestRevision: true, percent: 100 }] },
  status: { latestReadyRevisionName: "omi-platform-dev-old" },
});

test("initial private development service declares actual first-revision traffic and complete runtime bindings", () => {
  const prepared = prepareCandidate(input(), null);
  const manifest = prepared.manifest;
  expect(manifest.spec.traffic).toEqual([
    { revisionName: prepared.release.revision, percent: 100 },
  ]);
  expect(
    manifest.metadata.annotations["run.googleapis.com/invoker-iam-disabled"]
  ).toBe("false");
  expect(manifest.spec.template.spec.serviceAccountName).toBe(
    "omi-platform-dev-runtime@based-hardware-dev.iam.gserviceaccount.com"
  );
  expect(manifest.spec.template.spec.containerConcurrency).toBe(2);
  expect(manifest.spec.template.spec.timeoutSeconds).toBe(150);
  expect(
    manifest.spec.template.metadata.annotations[
      "autoscaling.knative.dev/maxScale"
    ]
  ).toBe("2");
  expect(
    manifest.spec.template.metadata.annotations[
      "run.googleapis.com/cloudsql-instances"
    ]
  ).toBe("based-hardware-dev:us-central1:omi-platform-dev-pg18");
  expect(manifest.spec.template.spec.containers[0].env).toContainEqual({
    name: "OMI_DATABASE_SOCKET_DIRECTORY",
    value: "/cloudsql/based-hardware-dev:us-central1:omi-platform-dev-pg18",
  });
  expect(prepared.release.poolMax).toBe(4);
  expect(
    manifest.spec.template.spec.containers[0]!.env.filter(
      (item) => "valueFrom" in item
    )
  ).toHaveLength(5);
  expect(
    manifest.spec.template.spec.containers[0]!.startupProbe.httpGet.path
  ).toBe("/ready");
});

test("blue-green pins previous latest traffic and creates only a zero-percent candidate tag", () => {
  const options = {
    ...input(),
    mode: "blue-green",
    residentRevisions: [
      { name: "omi-platform-dev-old", maxInstances: 2, poolMax: 4 },
    ],
  };
  const prepared = prepareCandidate(options, current());
  expect(prepared.manifest.spec.traffic).toEqual([
    { revisionName: "omi-platform-dev-old", percent: 100 },
    { revisionName: prepared.release.revision, percent: 0, tag: "candidate" },
  ]);
  expect(prepared.manifest.metadata.resourceVersion).toBe("123");
  expect(prepared.release.connections).toBe(28);
});

test("refuses unobserved resident revision capacity and unsafe initial replacement", () => {
  expect(() =>
    prepareCandidate({ ...input(), mode: "blue-green" }, current())
  ).toThrow();
  expect(() => prepareCandidate(input(), current())).toThrow();
  expect(() =>
    prepareCandidate({ ...input(), mode: "blue-green" }, null)
  ).toThrow();
  expect(() =>
    prepareCandidate(
      {
        ...input(),
        mode: "blue-green",
        residentRevisions: [
          { name: "omi-platform-dev-old", maxInstances: 3, poolMax: 4 },
        ],
      },
      current()
    )
  ).toThrow();
});

test("refuses mutable images, secret aliases, missing authority and secret payloads", () => {
  expect(() =>
    prepareCandidate({ ...input(), image: "runtime:latest" }, null)
  ).toThrow();
  expect(() =>
    prepareCandidate(
      {
        ...input(),
        image: input().image.replace("based-hardware-dev", "based-hardware"),
      },
      null
    )
  ).toThrow();
  expect(() =>
    prepareCandidate(
      {
        ...input(),
        secretVersions: {
          ...input().secretVersions,
          OMI_CODEC_KEY_HEX: "latest",
        },
      },
      null
    )
  ).toThrow();
  expect(() =>
    prepareCandidate({ ...input(), databaseGeneration: "" }, null)
  ).toThrow();
  expect(() =>
    prepareCandidate({ ...input(), accountTimezone: "not-a-timezone" }, null)
  ).toThrow();
  expect(() =>
    prepareCandidate({ ...input(), password: "forbidden" }, null)
  ).toThrow();
});

test("secret-version changes create a distinct immutable revision name without changing image", () => {
  const one = prepareCandidate(input(), null);
  const two = prepareCandidate(
    {
      ...input(),
      secretVersions: { ...input().secretVersions, OMI_CODEC_KEY_HEX: "5" },
    },
    null
  );
  expect(two.release.revision).not.toBe(one.release.revision);
});
