# Memory atlas

LIFECYCLE: permanent

Draws the knowledge graph as a map: entities grouped into named regions with
coastlines, rather than a node-link ball. Ported from macOS
`MainWindow/Pages/MemoryGraph/`.

## The problem it answers

`components/graph/KnowledgeGraphViewer.tsx` states the measurement in its own
header: a real account is around 188 nodes and 474 edges with one 226-degree hub
and roughly 40% degree-1 leaves, and drawn whole it is an unreadable, laggy
hairball.

The existing graph view keeps that legible by **hiding** nodes: a default cap on
the most connected, with a "Show all" escape hatch. The atlas takes the opposite
approach to the same problem. It hides nothing, and instead groups entities into
regions whose names say what each part of the map is about. Both views ship; the
Brain Map page toggles between them.

## Pipeline

```
relatedness  ->  communities  ->  layout  ->  coastlines  ->  territories
```

| Module | Answers |
|---|---|
| `relatedness.ts` | How strongly are two entities related? |
| `communities.ts` | Which entities belong together? |
| `atlasLayout.ts` | Where does each entity go? |
| `islands.ts` | What shape is a group's land? |
| `territories.ts` | Which groups are places, and what are they called? |
| `zoomPolicy.ts` | What is visible at this magnification? |
| `buildAtlas.ts` | Runs the above, in this order. |

Communities are detected **before** positions are computed, which is the reverse
of the obvious order. The layout needs them: see below.

## The rules that carry the weight

**Relatedness is two signals.** Edges the graph states outright, weighted
logarithmically in the memories behind them, plus entities that keep appearing in
the same memory. Each memory divides one unit of relatedness among its
participants, and each participant is weighted by how rare it is, so two entities
that only ever co-occur inside one ubiquitous entity's memories are not treated
as related. A memory naming more than 20 entities is skipped: it relates
everything to everything, which is the same information as relating nothing.

**A community must be denser than the map to have land.** A coastline is drawn
where a community's own scalar field beats the sea level. This is why
`atlasLayout.ts` exists rather than reusing the app's `computeLayout`: that
layout spreads entities evenly, which is right for a node-link graph and fatal
here. Wired to it, two of three obvious clusters produced no land at all.

**Three constants shape every coastline.** The sea level sits above 1 because a
lone entity's bump peaks at exactly 1, so one entity can never mint a territory.
The decisive margin means a cell only belongs to the leader if it beats the
runner-up by a quarter, so contested ground stays water. Reach is not an absolute
distance but the map's own median nearest-neighbour spacing times 2.5, because
the same spacing means "tight" on a dense map and "scattered" on a sparse one.

**Marching squares stitches by integer edge identity**, not by coordinate.
Comparing interpolated coordinates leaves hairline gaps wherever two cells
disagree in the last bit, and a ring with a gap cannot be filled.

**A region the map cannot name is not drawn.** An unnamed shape is noise, and the
entities inside it are still drawn as entities.

**Determinism is a contract.** Every traversal that can affect an output walks a
sorted array, a tied Louvain candidate cannot pull a node, and the layout seeds
from a phyllotaxis spiral by index with a fixed tick count. The graph is merged
from an onboarding floor plus a server fetch whose interleaving is not fixed, so
without this the map would rearrange itself between runs for no visible reason.

## Deliberate divergences from macOS

| Divergence | Why |
|---|---|
| One added force on the existing d3 engine, not a 1,600-line bespoke relaxation | The bespoke layout exists to pack communities; one community-attraction force achieves what the island algorithm needs. |
| A purity floor is **enforced**, not just asserted | macOS asserts in tests that every drawn region holds its own members, because its relaxation packs tightly enough that it is always true. Here it can fail, and a region drawn over ground none of its entities stand on is worse than no region. |
| No playback | Playback replays the map growing over time, and `graphDisplay.ts` records that the server graph carries no per-node timestamp. Deriving one from each node's memories is possible but is its own change. |
| No render-plan or snapshot cache | Those exist for a 4,000-line SwiftUI canvas under continuous camera motion; this redraws a few hundred shapes. |
| `ForceDirectedSimulation.swift` not ported | It is the legacy 3D engine for the old page, has no Atlas references, and uses a random source, which would break determinism. |

## Guards that cannot be observed in the output

Two rules here are defence in depth rather than load-bearing today, and the code
says so where they sit:

- Island ownership ties resolve to the lowest group id. A cell where two
  communities peak identically has `best == runnerUp`, so it fails the decisive
  margin and becomes water whichever community owns it.
- The eager-versus-lazy edge crossing in marching squares. The two cells sharing
  an edge read the same corner values, so they always agree on whether the
  contour crosses it, and a NaN for a non-crossing edge is never referenced.

Both are kept so that a later change to the surrounding rule cannot silently
start depending on the wrong behaviour.
