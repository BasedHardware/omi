export interface PostgresMigrationManifestEntry {
  readonly version: number;
  readonly name: string;
  readonly fileName: string;
  /** SHA-256 over the migration file's exact bytes. */
  readonly sha256: string;
}

export const POSTGRES_MIGRATIONS: readonly PostgresMigrationManifestEntry[] = Object.freeze([
  Object.freeze({
    version: 1,
    name: "account-control",
    fileName: "0001-account-control.sql",
    sha256: "086d58e5afc03fdad18665ba8c5b1c565960bb5b570f89704240cef531f3b5ff",
  }),
  Object.freeze({
    version: 2,
    name: "memory-ledger",
    fileName: "0002-memory-ledger.sql",
    sha256: "5081f78cce9b32b3e6c3258a838330fd57b4f031e4eff756e8c1fd6f54e14555",
  }),
  Object.freeze({
    version: 3,
    name: "formation-outcomes",
    fileName: "0003-formation-outcomes.sql",
    sha256: "527a619cb7739e0f9f858b528da800f48bfef2cd5963ecb83789beb22834ff15",
  }),
  Object.freeze({
    version: 4,
    name: "durable-memory-work",
    fileName: "0004-durable-memory-work.sql",
    sha256: "053a19ddc283152162b2a67bd2a48f04ca0e4a42b3611ca0a86dd1d858e9a8d8",
  }),
  Object.freeze({
    version: 5,
    name: "product-memory-projections",
    fileName: "0005-product-memory-projections.sql",
    sha256: "8bfc7384fdfdea00973981a8dd1f0c5e2513d0343481d7da7c9acc49c8f651d6",
  }),
  Object.freeze({
    version: 6,
    name: "durable-work-success",
    fileName: "0006-durable-work-success.sql",
    sha256: "68319bd35a212f825237cc54fe98a53072cc0ade98f8823a983cccc40545529e",
  }),
  Object.freeze({
    version: 7,
    name: "durable-work-result-staging",
    fileName: "0007-durable-work-result-staging.sql",
    sha256: "bcc3131f3c7da923d1faaaa6d2874ad963e90579d105c48cb19eb65d7f304a36",
  }),
  Object.freeze({
    version: 8,
    name: "memory-strategy-assignments",
    fileName: "0008-memory-strategy-assignments.sql",
    sha256: "1d0d76885d5edb6f35bac57df7f05f86e5126bd7f8e9c9f0cfb14c15c0a0e141",
  }),
  Object.freeze({
    version: 9,
    name: "memory-shadow-results",
    fileName: "0009-memory-shadow-results.sql",
    sha256: "8e3441e062c0347f7c3187d5028cada138186456f9a7feb75a21e85ff116ad3e",
  }),
  Object.freeze({
    version: 10,
    name: "read-side-experiment-strategies",
    fileName: "0010-read-side-experiment-strategies.sql",
    sha256: "f3918ca5844602670a12678f2aef13ab7eef5c8a8caae2487829ace042673690",
  }),
  Object.freeze({
    version: 11,
    name: "memory-read-grounding-artifacts",
    fileName: "0011-memory-read-grounding-artifacts.sql",
    sha256: "455b9ca2f2902b62d692d78aee414881eed62b8e2792568fffe688a774d90a39",
  }),
  Object.freeze({
    version: 12,
    name: "firebase-credential-bindings",
    fileName: "0012-firebase-credential-bindings.sql",
    sha256: "4f1fc55e079f0c58e424c4cd6bf9b85a7d420b6627997cf1a9bf960723649b26",
  }),
  Object.freeze({
    version: 13,
    name: "atomic-liveness-frontier",
    fileName: "0013-atomic-liveness-frontier.sql",
    sha256: "faa364231f4003bb4be4e939a47a3862c5f109a3fce6d3c5fb32dc5e2fa63673",
  }),
  Object.freeze({
    version: 14,
    name: "durable-work-acceptance-runtime",
    fileName: "0014-durable-work-acceptance-runtime.sql",
    sha256: "9ea369e8bbe082673b626449133fdf755156aff3eb09af8e4a2165b7013b6271",
  }),
  Object.freeze({
    version: 15,
    name: "durable-work-execution-policies",
    fileName: "0015-durable-work-execution-policies.sql",
    sha256: "e2c6b52b397f95d47552e91b4987edba0740484ece49d10181f99891929356d4",
  }),
  Object.freeze({
    version: 16,
    name: "durable-work-execution-runtime",
    fileName: "0016-durable-work-execution-runtime.sql",
    sha256: "e9e496712bd10227d9bea641399fd3582e8b8e74c3a3b18efb46dc16f26bd3f7",
  }),
  Object.freeze({
    version: 17,
    name: "durable-work-result-runtime",
    fileName: "0017-durable-work-result-runtime.sql",
    sha256: "5e073d43545e26328f13bb20dfe3655092cb2abd3f6bed024d205589074ce6bf",
  }),
  Object.freeze({
    version: 18,
    name: "durable-work-success-runtime",
    fileName: "0018-durable-work-success-runtime.sql",
    sha256: "187cf8b9282b8beba490a90ad09cbdd51d545012ee4cd791ddb210625446708a",
  }),
  Object.freeze({
    version: 19,
    name: "formation-work-input-runtime",
    fileName: "0019-formation-work-input-runtime.sql",
    sha256: "c8de0a646ddfe0b015a437718cabd69fabdf2f5888055c9b780c48be84a7897e",
  }),
  Object.freeze({
    version: 20,
    name: "predicate-batch-work-input",
    fileName: "0020-predicate-batch-work-input.sql",
    sha256: "9ba91102f09dd3d29e4b601ea11d51eb837d824c4b79dbb3e825f1af23ee3547",
  }),
  Object.freeze({
    version: 21,
    name: "product-projection-runtime",
    fileName: "0021-product-projection-runtime.sql",
    sha256: "6cf363c08e51820b633ca42cd1f3df3fb325cb1ab0c73674cace68d492940f4b",
  }),
  Object.freeze({
    version: 22,
    name: "product-projection-writer-grants",
    fileName: "0022-product-projection-writer-grants.sql",
    sha256: "0541f1c78f91e175ce6ca32d806a85c8d4147de1ae8728330b8b0ad2a5557499",
  }),
  Object.freeze({
    version: 23,
    name: "memory-experiment-runtime",
    fileName: "0023-memory-experiment-runtime.sql",
    sha256: "1e0ca4fc4cad4e170a67fd112c9f8244367a19563cf47651ae926811d4e316cc",
  }),
  Object.freeze({
    version: 24,
    name: "memory-query-evaluation-input",
    fileName: "0024-memory-query-evaluation-input.sql",
    sha256: "58640fdd710371cf5f336158e671c199b1bf95dd0182818876360fcbe44ba307",
  }),
  Object.freeze({
    version: 25,
    name: "account-deletion-cleanup-runtime",
    fileName: "0025-account-deletion-cleanup-runtime.sql",
    sha256: "357fb3625e10d157d0a951067966aa2c1c5c2330af3041015026c26331dac7d9",
  }),
  Object.freeze({
    version: 26,
    name: "postgres-tombstone-restore-target",
    fileName: "0026-postgres-tombstone-restore-target.sql",
    sha256: "32244da6a077e6232c854858150b8c6c28084d684629611cb58b678875c3b02e",
  }),
  Object.freeze({
    version: 27,
    name: "restore-replay-checkpoint-candidates",
    fileName: "0027-restore-replay-checkpoint-candidates.sql",
    sha256: "ad6a52c08d618cc0de1fd77919e2d392aa75bf5161ca1950c97a896b9bd7f403",
  }),
  Object.freeze({
    version: 28,
    name: "restored-terminal-application-gate",
    fileName: "0028-restored-terminal-application-gate.sql",
    sha256: "ce7fa406eee3cc1acd3906acbfe411f44c187da25fbee9ce6f0352938baabb9c",
  }),
  Object.freeze({
    version: 29,
    name: "restored-generation-application-gate",
    fileName: "0029-restored-generation-application-gate.sql",
    sha256: "9a7792ad4493594e288e659d92be431d39a3887826efc90de705b0e29ba73ca9",
  }),
  Object.freeze({
    version: 30,
    name: "listen-capture-finalization",
    fileName: "0030-listen-capture-finalization.sql",
    sha256: "3391f212826a62711516f00f46705d017dea4ebd6ac718935ae9b983f417dc8d",
  }),
  Object.freeze({
    version: 31,
    name: "listen-formation-outbox-delivery",
    fileName: "0031-listen-formation-outbox-delivery.sql",
    sha256: "e60559cbb6c7f9b3881e4d1a0d05daa4233474f57a4715937b6e2a9d275ff86f",
  }),
  Object.freeze({
    version: 32,
    name: "listen-attribution-belief-inputs",
    fileName: "0032-listen-attribution-belief-inputs.sql",
    sha256: "c75fd81bf00cefac72c9e652f3c5e0e470f2418ba5a62243a535d44c851f3d78",
  }),
  Object.freeze({
    version: 33,
    name: "legacy-proposition-migration-runtime",
    fileName: "0033-legacy-proposition-migration-runtime.sql",
    sha256: "bb218bcb672734902f09eaa287dd7df9fe7a7304e786e2ddb21fd867c25a2fb5",
  }),
  Object.freeze({
    version: 34,
    name: "internal-worker-restore-gate",
    fileName: "0034-internal-worker-restore-gate.sql",
    sha256: "7f23f709a22e5d705279ab094d00c107955d7be3b54995c56c0dacb3a8f7c2cd",
  }),
  Object.freeze({
    version: 35,
    name: "production-runtime-readiness",
    fileName: "0035-production-runtime-readiness.sql",
    sha256: "0fa72a8def09da66d2f36be8c9e334877e83595d0150467794ae476e3123d89e",
  }),
  Object.freeze({
    version: 36,
    name: "gcp-operator-restore-admission",
    fileName: "0036-gcp-operator-restore-admission.sql",
    sha256: "ab6b18bff5d8a28a7e38d2946b2a39ce5e0b67c3eaa596c6ed4bda3ce333250f",
  }),
]);
