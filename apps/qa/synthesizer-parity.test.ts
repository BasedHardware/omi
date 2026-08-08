// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
import { describe, expect, test } from "bun:test";

import { createQaDeterministicSynthesizer as serviceSynthesizer } from "../service/composition/qa-synthesizer";
import { createQaDeterministicSynthesizer as sharedSynthesizer } from "./synthesizer";

/**
 * Drift detector for the two copies of the QA synthesizer.
 *
 * `apps/qa/synthesizer.ts` is the canonical one; `apps/service/composition/
 * qa-synthesizer.ts` is BE-SURFACE's original, which should become a re-export
 * of it. Until that lands, two copies exist, and two copies that agree today are
 * two copies that disagree after the next edit.
 *
 * This matters more than a normal duplication: the synthesizer's output is
 * hashed into `render_hash` → candidate ref → public item id, so the moment they
 * diverge the two doors return different ids for the same memory — and the
 * node-level cross-door assertion keeps passing while it happens. That is
 * precisely the failure mode the granularity ruling exists to prevent.
 *
 * red-proof: change a single character of the summary phrasing in either file
 * and this fails.
 *
 * DELETE THIS FILE once `apps/service/composition/qa-synthesizer.ts` re-exports
 * the shared one — at that point it asserts a tautology.
 */

interface Case {
  readonly name: string;
  readonly input: unknown;
}

const claim = (id: string, predicate: string, observedAt: string, refs: string[], args: unknown[]) => ({
  claim_revision_id: id,
  predicate,
  observed_at: observedAt,
  evidence_refs: refs,
  arguments: args,
});

const cases: readonly Case[] = [
  {
    name: "single claim with an entity argument",
    input: {
      node: { node_id: "n1", view_kind: "temporal", anchor_key: "year:2026/month:08/day:07" },
      claims: [claim("c1", "attended", "2026-08-07T12:00:00.000Z", ["e1"], [
        { role: "subject", value: { kind: "entity_ref", ref: "entity:alice" } },
      ])],
    },
  },
  {
    name: "multiple claims sort by revision id, citations dedupe and sort",
    input: {
      node: { node_id: "n2", view_kind: "temporal", anchor_key: "year:2026" },
      claims: [
        claim("c9", "said", "2026-08-09T00:00:00.000Z", ["e2", "e1"], [
          { role: "subject", value: { kind: "literal", value: "a note" } },
        ]),
        claim("c2", "met", "2026-08-02T00:00:00.000Z", ["e1"], [
          { role: "subject", value: { kind: "entity_ref", ref: "entity:bob" } },
        ]),
      ],
    },
  },
  {
    name: "claim with no renderable argument falls back to the unnamed subject",
    input: {
      node: { node_id: "n3", view_kind: "source", anchor_key: "capture:s1" },
      claims: [claim("c3", "noted", "2026-08-03T00:00:00.000Z", ["e3"], [
        { role: "subject", value: { kind: "source_local_ref", ref: "src:1" } },
      ])],
    },
  },
  {
    name: "empty claim set",
    input: { node: { node_id: "n4", view_kind: "entity", anchor_key: "entity:x" }, claims: [] },
  },
];

describe("QA synthesizer parity across the two doors", () => {
  for (const testCase of cases) {
    test(`identical output — ${testCase.name}`, async () => {
      const shared = await sharedSynthesizer().render({
        strategy: "application-read-qa", version: "qa-deterministic-synthesizer-v1",
        input: testCase.input,
      });
      const service = await serviceSynthesizer().render({
        strategy: "application-read-qa", version: "qa-deterministic-synthesizer-v1",
        input: testCase.input,
      });
      expect(shared.summary_text).toBe(service.summary_text);
      expect([...shared.citations]).toEqual([...service.citations]);
      // Non-vacuity: the summary must actually say something.
      expect(shared.summary_text.length).toBeGreaterThan(0);
    });
  }

  test("the summary never carries an internal structural node id", async () => {
    // The frontend contract forbids exposing internal IDs. An earlier MCP-side
    // synthesizer put `retrieval-node-v1:<hash>` straight into wire text.
    // red-proof: interpolate node.node_id into the summary and this fails.
    const shared = await sharedSynthesizer().render({
      strategy: "application-read-qa", version: "qa-deterministic-synthesizer-v1",
      input: {
        node: { node_id: "retrieval-node-v1:deadbeef", view_kind: "temporal", anchor_key: "year:2026" },
        claims: [claim("c1", "attended", "2026-08-07T12:00:00.000Z", ["e1"], [
          { role: "subject", value: { kind: "entity_ref", ref: "entity:alice" } },
        ])],
      },
    });
    expect(shared.summary_text).not.toContain("retrieval-node-v1");
    expect(shared.summary_text).not.toContain("deadbeef");
  });
});
