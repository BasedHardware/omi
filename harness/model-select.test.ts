import { afterEach, describe, expect, test } from "bun:test";

import {
  liveModelVersion,
  MODEL_PROFILES,
  modelForProfile,
  modelProfileCacheNamespace,
  profileApiKey,
  selectModel,
} from "./model-select";

const ENV_KEYS = [
  "GLM_API_KEY", "ZAI_API_KEY", "OMI_BENCH_OPENAI_API_KEY",
  "OMI_BENCH_OPENAI_MODEL", "OPENCODE_GO_API_KEY", "OMI_BOUNDARY_VERSION",
] as const;
const original = Object.fromEntries(ENV_KEYS.map((key) => [key, process.env[key]]));

afterEach(() => {
  for (const key of ENV_KEYS) {
    const value = original[key];
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

describe("offline model profile registry", () => {
  test("keeps DeepSeek and GLM as distinct explicit OpenAI-compatible resources", () => {
    expect(MODEL_PROFILES["glm"]).toMatchObject({ model_id: "glm-4.7" });
    expect(MODEL_PROFILES["deepseek-flash"]).toEqual({
      model_id: "deepseek-v4-flash",
      base_url: "https://opencode.ai/zen/go/v1",
      api_key_env: ["OPENCODE_GO_API_KEY"],
      prompt_env_defaults: { OMI_BOUNDARY_VERSION: "v5" },
    });
    expect(modelProfileCacheNamespace(["--model", "glm"]))
      .toBe("glm:glm-4.7");
    expect(modelProfileCacheNamespace(["--model", "deepseek-flash"]))
      .toBe("deepseek-flash:deepseek-v4-flash");
    expect(liveModelVersion(["--model", "deepseek-flash"]))
      .toBe("deepseek-v4-flash");
  });

  test("resolves credentials only from the profile and preserves explicit prompt settings", () => {
    process.env["GLM_API_KEY"] = "glm-secret";
    delete process.env["OPENCODE_GO_API_KEY"];
    expect(profileApiKey(MODEL_PROFILES["deepseek-flash"]!)).toBeUndefined();
    expect(() => modelForProfile("deepseek-flash"))
      .toThrow("requires one of OPENCODE_GO_API_KEY");

    process.env["OPENCODE_GO_API_KEY"] = "deepseek-secret";
    process.env["OMI_BOUNDARY_VERSION"] = "explicit-version";
    expect(modelForProfile("deepseek-flash")).toBeDefined();
    expect(process.env["OMI_BOUNDARY_VERSION"]).toBe("explicit-version");
  });

  test("an explicit unknown model fails instead of silently becoming a fake", () => {
    expect(() => selectModel(["--model"], {}))
      .toThrow("requires a named profile");
    expect(() => selectModel(["--model", "unknown-provider"], {}))
      .toThrow("unknown model profile");
    expect(() => modelForProfile("unknown-provider"))
      .toThrow("known: glm, deepseek-flash");
    expect(selectModel([], { local: true }).live).toBe(false);
  });

  test("GLM model-id overrides change both provider provenance and cache namespace", () => {
    process.env["OMI_BENCH_OPENAI_MODEL"] = "glm-qualified-variant";
    expect(liveModelVersion(["--model", "glm"])).toBe("glm-qualified-variant");
    expect(modelProfileCacheNamespace(["--model", "glm"]))
      .toBe("glm:glm-qualified-variant");
  });
});
