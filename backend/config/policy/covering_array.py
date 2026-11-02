"""Small deterministic all-pairs covering-array builder for constrained factors."""

from __future__ import annotations

from array import array
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import random
from typing import Hashable


@dataclass(frozen=True)
class CoveringArray:
    rows: tuple[dict[str, Hashable], ...]
    factor_count: int
    feasible_pair_count: int
    covered_pair_count: int
    candidate_count: int


def pairwise_covering_array(
    factors: Mapping[str, Sequence[Hashable]],
    *,
    valid: Callable[[Mapping[str, Hashable]], bool],
    partial_valid: Callable[[Mapping[str, Hashable]], bool],
    seed: int = 1,
    seed_rows: Sequence[Mapping[str, Hashable]] = (),
    random_candidates: int = 96,
) -> CoveringArray:
    """Build an exact constrained pairwise array using a compact greedy set cover.

    Random valid candidates cover common interactions; constraint-aware
    backtracking proves each remaining interaction feasible or infeasible and
    adds a completion when needed. A greedy pass then chooses valid rows that
    cover the remaining interactions. Constraints are supplied by the owning
    policy types; no Cartesian product or dependency is needed.
    """
    names = tuple(factors)
    domains = tuple(tuple(dict.fromkeys(factors[name])) for name in names)
    if not names or any(not domain for domain in domains):
        raise ValueError('covering array needs at least one nonempty factor')
    if len(set(names)) != len(names):
        raise ValueError('factor names must be unique')

    levels = tuple({value: level for level, value in enumerate(domain)} for domain in domains)
    rng = random.Random(seed)
    candidates: list[tuple[int, ...]] = []
    candidate_ids: dict[tuple[int, ...], int] = {}
    seeded_ids: list[int] = []

    def add(row: Mapping[str, Hashable], *, seeded: bool = False) -> int | None:
        if set(row) != set(names) or not valid(row):
            return None
        try:
            codes = tuple(levels[index][row[name]] for index, name in enumerate(names))
        except (KeyError, TypeError):
            return None
        candidate_id = candidate_ids.get(codes)
        if candidate_id is None:
            candidate_id = len(candidates)
            candidate_ids[codes] = candidate_id
            candidates.append(codes)
        if seeded and candidate_id not in seeded_ids:
            seeded_ids.append(candidate_id)
        return candidate_id

    for row in seed_rows:
        if add(row, seeded=True) is None:
            raise ValueError('invalid seed row in covering array')

    check_partial = partial_valid

    def complete(fixed: Mapping[str, Hashable]) -> dict[str, Hashable] | None:
        partial = dict(fixed)
        remaining = [name for name in names if name not in partial]

        def search(position: int) -> dict[str, Hashable] | None:
            if position == len(remaining):
                return dict(partial) if valid(partial) else None
            name = remaining[position]
            values = list(factors[name])
            rng.shuffle(values)
            for value in values:
                partial[name] = value
                if check_partial(partial):
                    completed = search(position + 1)
                    if completed is not None:
                        return completed
            del partial[name]
            return None

        if not check_partial(partial):
            return None
        return search(0)

    # Constrained completions give a broad pool of valid rows cheaply. Exact
    # feasibility checks below only run for interactions those rows miss.
    for _ in range(max(0, random_candidates)):
        row = complete({})
        if row is not None:
            add(row)

    def interactions(codes: Sequence[int]):
        for left in range(len(names)):
            for right in range(left + 1, len(names)):
                yield left, right, codes[left], codes[right]

    feasible_seen = {interaction for codes in candidates for interaction in interactions(codes)}

    # Prove every pair-level combination that has not already appeared in a
    # valid row. Successful completions also establish their other interactions.
    for left in range(len(names)):
        for right in range(left + 1, len(names)):
            for left_level, left_value in enumerate(domains[left]):
                for right_level, right_value in enumerate(domains[right]):
                    interaction = left, right, left_level, right_level
                    if interaction in feasible_seen:
                        continue
                    fixed = {names[left]: left_value, names[right]: right_value}
                    row = complete(fixed)
                    if row is not None:
                        candidate_id = add(row)
                        if candidate_id is None:
                            raise AssertionError('valid completed row was rejected by the candidate registry')
                        feasible_seen.update(interactions(candidates[candidate_id]))

    if not candidates:
        raise ValueError('no valid rows found for covering array')

    offsets: dict[tuple[int, int], int] = {}
    offset = 0
    for left in range(len(names)):
        for right in range(left + 1, len(names)):
            offsets[left, right] = offset
            offset += len(domains[left]) * len(domains[right])

    row_pairs: list[array] = []
    row_pair_masks: list[int] = []
    coverers: dict[int, array] = {}
    for candidate_id, codes in enumerate(candidates):
        pairs = array('I')
        pair_mask = 0
        for left in range(len(names)):
            for right in range(left + 1, len(names)):
                pair_id = offsets[left, right] + codes[left] * len(domains[right]) + codes[right]
                pairs.append(pair_id)
                pair_mask |= 1 << pair_id
                coverers.setdefault(pair_id, array('I')).append(candidate_id)
        row_pairs.append(pairs)
        row_pair_masks.append(pair_mask)

    uncovered = set(coverers)
    uncovered_mask = sum(1 << pair_id for pair_id in uncovered)
    selected = list(seeded_ids)
    for candidate_id in selected:
        uncovered.difference_update(row_pairs[candidate_id])
        uncovered_mask &= ~row_pair_masks[candidate_id]
    while uncovered:
        rarest = min(uncovered, key=lambda pair_id: (len(coverers[pair_id]), pair_id))
        best_score = -1
        best_candidates: list[int] = []
        for candidate_id in coverers[rarest]:
            score = (row_pair_masks[candidate_id] & uncovered_mask).bit_count()
            if score > best_score:
                best_score = score
                best_candidates = [candidate_id]
            elif score == best_score:
                best_candidates.append(candidate_id)
        chosen = rng.choice(best_candidates)
        selected.append(chosen)
        uncovered.difference_update(row_pairs[chosen])
        uncovered_mask &= ~row_pair_masks[chosen]

    rows = tuple(
        {name: domains[index][codes[index]] for index, name in enumerate(names)}
        for candidate_id in selected
        for codes in (candidates[candidate_id],)
    )
    return CoveringArray(
        rows=rows,
        factor_count=len(names),
        feasible_pair_count=len(coverers),
        covered_pair_count=len(coverers) - len(uncovered),
        candidate_count=len(candidates),
    )
