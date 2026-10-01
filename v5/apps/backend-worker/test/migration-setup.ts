import { applyD1Migrations } from "cloudflare:test";
import { env } from "cloudflare:workers";
import type { D1Migration } from "@cloudflare/vitest-pool-workers";
import { beforeAll } from "vitest";

beforeAll(async () => {
  await applyD1Migrations(
    env.DB,
    Reflect.get(env, "TEST_MIGRATIONS") as D1Migration[]
  );
});
