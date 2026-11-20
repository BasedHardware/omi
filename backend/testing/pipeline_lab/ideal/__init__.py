"""Hand-reviewed ideal outcomes for a corpus day, and scoring any result against them.

- :mod:`packet` exports a day's speech as numbered lines (the drafting input; no audio, no results).
- :mod:`schema` is the ideal file format and its validator.
- :mod:`score` scores a set of conversations (production's, a replay's, another draft) against an ideal.

Packets and ideals hold the owner's transcripts: they live under the lab root (0700), never in git.
"""
