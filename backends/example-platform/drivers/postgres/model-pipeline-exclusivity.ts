import {
  defineModelPipelineExclusivity,
  type ModelPipelineExclusivity,
} from "../../apps/service/workers/model-pipeline-exclusivity";
import {
  bindModelPipelineResourceAdmission,
  defineModelPipelineResourceAdmission,
  type AdmittedModelPipelineExclusivity,
} from "../../apps/service/workers/model-pipeline-resource-admission";
import {
  assertProductionQualificationManifestReceipt,
  type ProductionQualificationManifestReceipt,
} from "../../scripts/production-qualification-manifest";
import type { PostgresSessionAdvisoryLockPool } from "./connection";

const signedInt32 = (hex: string): number => {
  const value = Number.parseInt(hex, 16);
  return value > 0x7fffffff ? value - 0x100000000 : value;
};

/**
 * A 64-bit advisory key can conservatively collide and serialize two distinct
 * resources, but a collision can never permit overlap for one resource.
 */
export const createPostgresProductionModelPipelineExclusivity = (
  pool: PostgresSessionAdvisoryLockPool,
  receiptValue: Readonly<ProductionQualificationManifestReceipt>,
): AdmittedModelPipelineExclusivity => {
  const receipt = assertProductionQualificationManifestReceipt(receiptValue);
  const admission = defineModelPipelineResourceAdmission(receipt.manifest.model_resources);
  const exclusivity: ModelPipelineExclusivity = defineModelPipelineExclusivity(async (resource, callback) => {
    try {
      const result = await pool.tryWithSessionAdvisoryLock([
        signedInt32(resource.resource_digest.slice(0, 8)),
        signedInt32(resource.resource_digest.slice(8, 16)),
      ], callback);
      return result.acquired
        ? Object.freeze({ kind: "completed" as const, value: result.value })
        : Object.freeze({ kind: "busy" as const });
    } catch {
      return Object.freeze({ kind: "unavailable" as const });
    }
  });
  return bindModelPipelineResourceAdmission(exclusivity, admission);
};
