"""Bound lexical candidates to one occurrence; this never proves audio custody."""

from dataclasses import dataclass

# Matched speech in the owner replay commonly differs by 26 seconds. Larger
# offsets abstain; a shift is usable only with three ordered neighbouring matches
# whose start/end residuals all agree within two seconds.
MAX_CLOCK_OFFSET_SECONDS = 30.0
PLACEMENT_TOLERANCE_SECONDS = 2.0
EXACT_PLACEMENT_SECONDS = 0.01
OCCURRENCE_WINDOW_SECONDS = 90.0


@dataclass(frozen=True)
class OccurrenceMatch:
    incoming_start: float
    incoming_end: float
    reference_start: float
    reference_end: float
    reference_parts: frozenset[int]
    duration_consistent: bool
    exact_text: bool


def aligned_occurrence_indices(
    options: dict[int, list[OccurrenceMatch]],
    signatures: dict[int, tuple[tuple[str, ...], float | None]],
) -> frozenset[int]:
    """Abstain on repeated phrases and competing or non-monotonic matches.

    An exact phrase repeated in either input within the discovery window is
    ambiguous, even if one occurrence fails the duration test. Overlapping
    alternative windows may describe one reference occurrence; disjoint ones
    cannot. No reference segment may certify two incoming segments.
    """
    phrases: dict[tuple[str, ...], list[int]] = {}
    for index, (tokens, _) in signatures.items():
        if tokens:
            phrases.setdefault(tokens, []).append(index)
    ambiguous = set()
    for indices in phrases.values():
        if any(signatures[index][1] is None for index in indices):
            ambiguous.update(indices)
            continue
        ordered = sorted(indices, key=lambda index: signatures[index][1] or 0.0)
        for left, right in zip(ordered, ordered[1:]):
            a, b = signatures[left][1], signatures[right][1]
            if a is None or b is None or abs(a - b) <= OCCURRENCE_WINDOW_SECONDS:
                ambiguous.update((left, right))

    unique: dict[int, OccurrenceMatch] = {}
    owners: dict[int, set[int]] = {}
    for index, candidates in options.items():
        for candidate in candidates:
            for part in candidate.reference_parts:
                owners.setdefault(part, set()).add(index)
        selected = next((candidate for candidate in candidates if candidate.duration_consistent), None)
        if (
            selected is not None
            and index not in ambiguous
            and all(candidate.reference_parts & selected.reference_parts for candidate in candidates)
        ):
            unique[index] = selected
    unique = {
        index: match
        for index, match in unique.items()
        if all(len(owners[part]) == 1 for candidate in options[index] for part in candidate.reference_parts)
    }

    aligned = {
        index
        for index, match in unique.items()
        if match.exact_text
        and max(
            abs(match.incoming_start - match.reference_start),
            abs(match.incoming_end - match.reference_end),
        )
        <= EXACT_PLACEMENT_SECONDS
    }
    for index in sorted(unique):
        if index + 1 not in unique or index + 2 not in unique:
            continue
        chain = [unique[index + offset] for offset in range(3)]
        if any(
            left.incoming_end > right.incoming_start
            or left.reference_end > right.reference_start
            or right.incoming_start - left.incoming_end > 15.0
            or right.reference_start - left.reference_end > 15.0
            for left, right in zip(chain, chain[1:])
        ):
            continue
        offsets = [
            delta
            for match in chain
            for delta in (
                match.incoming_start - match.reference_start,
                match.incoming_end - match.reference_end,
            )
        ]
        if max(map(abs, offsets)) <= MAX_CLOCK_OFFSET_SECONDS and (
            max(offsets) - min(offsets) <= PLACEMENT_TOLERANCE_SECONDS
        ):
            aligned.update(range(index, index + 3))
    return frozenset(aligned)
