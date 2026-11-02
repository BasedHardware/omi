"""Proposed personal-OTA state contract, NOT firmware/emulation/cryptography.

Inputs such as owner authorization and intact recovery are assumptions supplied
by tests. This model cannot establish them on a device or authorize operations.
"""
from dataclasses import dataclass, field, replace


class Rejected(ValueError):
    pass


STOCK_IMAGE_CAP_BYTES = 393216  # 384KiB whole NS stock container, same bound as upload


def check_regions(regions, start, end, alignment=4096):
    if type(alignment) is not int or alignment < 1 or start % alignment or end % alignment:
        raise Rejected("alignment or budget endpoints unaligned")
    cursor = start
    for name, low, high in regions:
        if not isinstance(name, str) or type(low) is not int or type(high) is not int:
            raise Rejected("region schema")
        if low != cursor or high <= low or low % alignment or high % alignment:
            raise Rejected("gap, overlap or alignment")
        cursor = high
    if cursor != end:
        raise Rejected("region budget mismatch")


@dataclass(frozen=True)
class State:
    phase: str = "stock"
    owner: bool = False
    generation: int = 0
    candidate: str = ""
    active: str = "stock"
    previous: str = "stock"
    recovery_intact: bool = True
    hardware_authorized: bool = field(default=False, init=False)
    cryptographic_verification_performed: bool = field(default=False, init=False)


def step(state, event, *, physical=False, authorized=False, digest="",
         generation=None, signature=False, board=False, abi=False,
         size=0, cap=393216, role="app", supervisor_health=False,
         maintainer_signature=False):
    """Symbolic transitions for option A; never uses actual keys or device APIs."""
    if any(type(flag) is not bool for flag in (physical, authorized, signature, board, abi, supervisor_health, maintainer_signature)):
        raise Rejected("boolean assumptions required")
    if generation is not None and type(generation) is not int:
        raise Rejected("integer generation required")
    if event == "enroll":
        if not physical or not authorized or state.phase not in ("stock", "recovery"):
            raise Rejected("enrollment needs protected gesture and owner proof")
        return replace(state, owner=True, generation=state.generation + 1)
    if event == "upload":
        if not state.owner or not authorized or not signature or not board or not abi:
            raise Rejected("owner/image compatibility assumptions not satisfied")
        if role != "app" or type(size) is not int or not 0 < size <= cap:
            raise Rejected("first stage is bounded app-only")
        if state.phase not in ("stock", "personal", "recovery") or type(digest) is not str or not digest:
            raise Rejected("wrong phase or missing digest")
        return replace(state, phase="staged", candidate=digest, previous=state.active)
    if event == "activate":
        if state.phase != "staged" or not state.recovery_intact:
            raise Rejected("no verified stage or independent recovery")
        return replace(state, phase="copy_candidate")
    if event == "copy_complete":
        if state.phase == "copy_stock":
            return replace(state, phase="stock", active="stock", candidate="")
        if state.phase == "copy_candidate":
            return replace(state, phase="trial", active=state.candidate)
        if state.phase == "copy_previous":
            return replace(state, phase="stock" if state.previous == "stock" else "personal",
                           active=state.previous, candidate="")
        raise Rejected("no copy transaction")
    if event == "owner_confirm":
        if state.phase != "trial" or not authorized or not supervisor_health:
            raise Rejected("confirmation not from protected owner/health path")
        if digest != state.candidate or generation != state.generation:
            raise Rejected("stale/substituted confirmation")
        return replace(state, phase="personal", candidate="")
    if event in ("candidate_self_confirm", "disconnect"):
        return state
    if event in ("watchdog", "trial_timeout"):
        if state.phase != "trial":
            raise Rejected("not a trial")
        return replace(state, phase="copy_previous")
    if event == "power_cut":
        if state.phase == "trial":
            return replace(state, phase="copy_previous")
        return state  # Durable copy journal resumes; never jumps to a partial image.
    if event == "gesture":
        if not physical or not state.recovery_intact:
            raise Rejected("protected recovery not available")
        return replace(state, phase="recovery", candidate="")
    if event == "owner_reset":
        if state.phase != "recovery" or not physical:
            raise Rejected("lost-phone reset requires protected physical recovery")
        return replace(state, owner=False, generation=state.generation + 1, candidate="")
    if event == "stock_restore_verified":
        if state.phase != "recovery" or not maintainer_signature or not board or not abi:
            raise Rejected("stock restore needs protected recovery and compatible maintainer image")
        if role != "app" or type(size) is not int or not 0 < size <= STOCK_IMAGE_CAP_BYTES:
            raise Rejected("stock restore is bounded app-only")
        return replace(state, phase="copy_stock", candidate="")
    if event in ("write_supervisor", "write_owner_journal", "write_uicr", "stop_secure_watchdog"):
        raise Rejected("required isolation contract; denial is assumed, not hardware-proven")
    raise Rejected("unsupported event")
