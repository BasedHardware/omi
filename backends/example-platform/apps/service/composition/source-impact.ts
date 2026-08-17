// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { isProxy } from "node:util/types";

import type { GraphSnapshot } from "../../../core/retrieve";
import {
  assertSourceImpactPageRequest,
  computeAuthorizedSourceImpactInputDigest,
  enumerateAuthorizedSourceImpact,
  type SourceImpactCodecs,
  type SourceImpactPage,
  type SourceImpactPageRequest,
} from "../../../core/retrieve/source-impact";
import {
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../../core/retrieve/authorization-boundary";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";
import {
  inspectProductProjectionReadRepository,
  type AuthorizedProductProjectionReadSet,
  type ProductProjectionReadRepository,
} from "../stores/product-projection-repository";

const READER_PORT: unique symbol = Symbol("authorized-source-impact-reader");
const MIN_ROOT_SECRET_BYTES = 32;
const MAX_ROOT_SECRET_BYTES = 4_096;
const MAX_TIMEZONE_CODE_UNITS = 256;

export type SourceImpactServiceErrorCode =
  | "invalid_config"
  | "read_unavailable"
  | "read_invalidated";

export class SourceImpactServiceError extends Error {
  constructor(readonly code: SourceImpactServiceErrorCode) {
    super(code);
    this.name = "SourceImpactServiceError";
  }
}

export interface SourceImpactCoherentLoad {
  readonly durable_snapshot: GraphSnapshot; // storage-provenance-ok(the only consumer passes this directly through the positive authorization projection)
  readonly account_timezone: string;
}

export interface AuthorizedSourceImpactReaderConfig {
  readonly resolveAuthorization: () => ApplicationMemoryReadAuthorizationRequest;
  readonly loadCoherent: () => SourceImpactCoherentLoad | Promise<SourceImpactCoherentLoad>;
  readonly productProjectionRepository: ProductProjectionReadRepository;
  readonly codecRootSecret: Uint8Array;
}

export interface AuthorizedSourceImpactReader {
  readonly [READER_PORT]: true;
  read(request: SourceImpactPageRequest): Promise<SourceImpactPage>;
}

type Callable = (...args: never[]) => unknown;

const fail = (code: SourceImpactServiceErrorCode): never => {
  throw new SourceImpactServiceError(code);
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
): Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("invalid_config");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")) fail("invalid_config");
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail("invalid_config");
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("invalid_config");
  }
  return descriptors as Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;
};

const callable = (value: unknown): Callable => {
  if (typeof value !== "function" || isProxy(value)) fail("invalid_config");
  return value as Callable;
};

const copyRootSecret = (value: unknown): Uint8Array => {
  if (!(value instanceof Uint8Array) || isProxy(value)
    || (Object.getPrototypeOf(value) !== Uint8Array.prototype && !Buffer.isBuffer(value))
    || value.buffer instanceof SharedArrayBuffer
    || value.byteLength < MIN_ROOT_SECRET_BYTES
    || value.byteLength > MAX_ROOT_SECRET_BYTES) fail("invalid_config");
  const bytes = value as Uint8Array;
  const copied = new Uint8Array(bytes.byteLength);
  copied.set(bytes);
  return copied;
};

const coherentLoad = (value: unknown): SourceImpactCoherentLoad => {
  let descriptors: Readonly<Record<string, PropertyDescriptor & { readonly value: unknown }>>;
  try {
    descriptors = exactRecord(value, ["durable_snapshot", "account_timezone"]); // storage-provenance-ok(the wrapper is validated before its snapshot enters the positive authorization projection)
  } catch {
    return fail("read_unavailable");
  }
  const timezone = descriptors["account_timezone"]!.value;
  if (typeof timezone !== "string" || timezone.length < 1
    || timezone.length > MAX_TIMEZONE_CODE_UNITS || timezone.includes("\0")) {
    fail("read_unavailable");
  }
  return Object.freeze({
    durable_snapshot: descriptors["durable_snapshot"]!.value as GraphSnapshot, // storage-provenance-ok(this exact value is handed directly to the positive authorization projection)
    account_timezone: timezone,
  });
};

interface CompleteAuthorizedLoad {
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly products: AuthorizedProductProjectionReadSet;
  readonly input_digest: string;
}

const sourceImpactCodecs = (
  rootSecret: Uint8Array,
  readerProjectionDigest: string,
): SourceImpactCodecs => {
  const opaque = createReaderScopedOpaqueCodecs({
    root_secret: rootSecret,
    reader_projection_digest: readerProjectionDigest,
  });
  const codecs: SourceImpactCodecs = {
    encode_ref: ({ kind, internal_ref }) => opaque.encodeSourceImpactRef(kind, internal_ref),
    verify_cursor: ({ cursor, binding_digest, after_key }) =>
      opaque.verifySourceImpactCursor(cursor, binding_digest, after_key),
    issue_cursor: ({ binding_digest, after_key }) =>
      opaque.issueSourceImpactCursor(binding_digest, after_key),
  };
  return Object.freeze(codecs);
};

/**
 * The single production-neutral source-impact composition. It creates no route
 * and owns no store; transports may call only the returned reader.
 */
export const createAuthorizedSourceImpactReader = (
  configValue: AuthorizedSourceImpactReaderConfig,
): AuthorizedSourceImpactReader => {
  const config = exactRecord(configValue, [
    "resolveAuthorization", "loadCoherent", "productProjectionRepository", "codecRootSecret",
  ]);
  const resolveAuthorization = callable(config["resolveAuthorization"]!.value);
  const loadCoherent = callable(config["loadCoherent"]!.value);
  let productRepository: ProductProjectionReadRepository;
  try {
    productRepository = inspectProductProjectionReadRepository(
      config["productProjectionRepository"]!.value,
    );
  } catch {
    return fail("invalid_config");
  }
  const rootSecret = copyRootSecret(config["codecRootSecret"]!.value);

  const loadComplete = async (): Promise<CompleteAuthorizedLoad> => {
    try {
      const authorizationBefore = Reflect.apply(
        resolveAuthorization,
        undefined,
        [],
      ) as ApplicationMemoryReadAuthorizationRequest;
      const loaded = coherentLoad(await Reflect.apply(loadCoherent, undefined, []));
      const project = (authorization: ApplicationMemoryReadAuthorizationRequest) =>
        readAfterApplicationAuthorization(authorization, () => ({
          // storage-provenance-ok(the durable snapshot is handed directly to the positive authorization projection; only its branded projection reaches the repository/paginator)
          snapshot: loaded.durable_snapshot,
          options: { account_timezone: loaded.account_timezone },
        }));
      const projectedBefore = project(authorizationBefore);
      const products = await productRepository.loadAuthorized(projectedBefore);

      // No asynchronous edge occurs after this second live authorization
      // resolution. Revocation while product I/O was pending therefore denies
      // before any codec or output construction.
      const authorizationAfter = Reflect.apply(
        resolveAuthorization,
        undefined,
        [],
      ) as ApplicationMemoryReadAuthorizationRequest;
      const projectedAfter = project(authorizationAfter);
      const beforeDigest = computeAuthorizedSourceImpactInputDigest(
        projectedBefore,
        products.authorized_projections,
      );
      const afterDigest = computeAuthorizedSourceImpactInputDigest(
        projectedAfter,
        products.authorized_projections,
      );
      if (beforeDigest !== afterDigest) fail("read_unavailable");
      return Object.freeze({ projected: projectedAfter, products, input_digest: afterDigest });
    } catch (error) {
      if (error instanceof SourceImpactServiceError) throw error;
      return fail("read_unavailable");
    }
  };

  const reader: AuthorizedSourceImpactReader = Object.freeze({
    [READER_PORT]: true as const,
    async read(requestValue: SourceImpactPageRequest): Promise<SourceImpactPage> {
      const request = assertSourceImpactPageRequest(requestValue);
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const prepared = await loadComplete();
        const revalidated = await loadComplete();
        if (prepared.input_digest !== revalidated.input_digest) {
          if (attempt === 0) continue;
          return fail("read_invalidated");
        }
        return enumerateAuthorizedSourceImpact(
          revalidated.projected,
          revalidated.products.authorized_projections,
          request,
          sourceImpactCodecs(rootSecret, revalidated.projected.reader_projection_digest),
        );
      }
      return fail("read_invalidated");
    },
  });
  return reader;
};
