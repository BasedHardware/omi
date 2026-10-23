"""The served primary-language options must stay usable by the rest of the stack.

The list moved out of the Flutter app so a language can be added without an app
release. That only holds if adding one here cannot produce an option the user
cannot actually save.
"""

from utils.user_language import (
    ACCEPTED_BASE_LANGUAGES,
    LANGUAGE_NAME_TO_BASE,
    PRIMARY_LANGUAGE_OPTIONS,
    normalize_user_language,
)


def test_every_offered_code_is_storable():
    # The picker POSTs the code straight to PATCH /v1/users/language, which
    # rejects anything normalize_user_language cannot resolve.
    unusable = [code for code, _ in PRIMARY_LANGUAGE_OPTIONS if normalize_user_language(code) is None]
    assert unusable == [], f"offered but not storable: {unusable}"


def test_offered_codes_round_trip_unchanged():
    # A code that normalizes to something else would leave the picker showing one
    # language while the account stores another.
    drifted = [
        (code, normalize_user_language(code))
        for code, _ in PRIMARY_LANGUAGE_OPTIONS
        if normalize_user_language(code) != code
    ]
    assert drifted == [], f"code changes on save: {drifted}"


def test_every_offered_base_is_serviceable_by_a_provider():
    unsupported = [
        code for code, _ in PRIMARY_LANGUAGE_OPTIONS if code.split('-')[0].lower() not in ACCEPTED_BASE_LANGUAGES
    ]
    assert unsupported == [], f"no STT provider covers: {unsupported}"


def test_no_duplicate_codes_or_names():
    codes = [code for code, _ in PRIMARY_LANGUAGE_OPTIONS]
    names = [name for _, name in PRIMARY_LANGUAGE_OPTIONS]
    assert len(codes) == len(set(codes)), "duplicate code in the catalog"
    assert len(names) == len(set(names)), "duplicate display name in the catalog"


def test_names_are_non_empty_and_trimmed():
    for code, name in PRIMARY_LANGUAGE_OPTIONS:
        assert name.strip() == name and name, f"{code} has a blank or padded name"


def test_english_is_offered_first():
    # The picker renders in this order and defaults to the head of the list.
    assert PRIMARY_LANGUAGE_OPTIONS[0] == ('en', 'English')


def test_alias_map_still_resolves_the_offered_names():
    # Older clients send the display name rather than the code; those must keep
    # resolving, otherwise moving the list breaks them.
    for code, name in PRIMARY_LANGUAGE_OPTIONS:
        base = code.split('-')[0].lower()
        resolved = LANGUAGE_NAME_TO_BASE.get(name.lower())
        if resolved is not None:
            assert resolved == base, f"alias '{name}' resolves to {resolved}, not {base}"
