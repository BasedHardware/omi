"""The stale-contract hint must name the surface it regenerates (#10217).

`--surface` defaults to `public`, so a hint that prints only `--write <path>` sends the
reader to overwrite a NON-public contract with the public surface. Following it verbatim
does not refresh that file, it guts it — the app-client spec lost ~53k lines exactly that
way. These pin the surface into every regenerate hint the checker emits.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_openapi.py"
_spec = importlib.util.spec_from_file_location("export_openapi_under_test", SCRIPT)
assert _spec is not None and _spec.loader is not None
export_openapi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_openapi)

SURFACES = ("public", "app-client", "integration-public")


@pytest.mark.parametrize("surface", SURFACES)
def test_hint_names_its_own_surface_and_path(surface):
    path = export_openapi.default_spec_path(surface)
    hint = export_openapi.regenerate_hint(path, surface)

    assert f"--surface {surface}" in hint
    assert str(path) in hint


@pytest.mark.parametrize("surface", SURFACES)
def test_missing_and_stale_errors_both_carry_the_surface(tmp_path, surface):
    path = tmp_path / "contract.json"

    with pytest.raises(export_openapi.OpenAPIContractError) as missing:
        export_openapi.check_spec(path, "{}\n", surface=surface)
    assert f"--surface {surface}" in str(missing.value)

    path.write_text("{}\n")
    with pytest.raises(export_openapi.OpenAPIContractError) as stale:
        export_openapi.check_spec(path, '{"different": true}\n', surface=surface)
    assert f"--surface {surface}" in str(stale.value)


def test_check_spec_stays_callable_without_surface(tmp_path):
    """Backward compatibility: check_spec must remain callable without `surface`.

    Making `surface` keyword-only-required broke existing callers
    (test_openapi_contract.py::test_check_spec_detects_stale_file) with a
    TypeError. It defaults to 'public' — matching the --surface default — while
    the production caller still passes surface explicitly.
    """
    path = tmp_path / "openapi.json"
    path.write_text("stale\n")

    with pytest.raises(export_openapi.OpenAPIContractError) as stale:
        export_openapi.check_spec(path, "fresh\n")  # no surface kwarg
    assert "is stale" in str(stale.value)
    assert "--surface public" in str(stale.value)


def test_a_non_public_hint_is_never_the_bare_public_default():
    """The regression itself: the app-client hint must not be a command that writes public.

    Before the fix the hint was `--write <app-client path>`, and because --surface defaults
    to public, running it produced the public surface in the app-client file.
    """
    app_client_path = export_openapi.default_spec_path("app-client")
    hint = export_openapi.regenerate_hint(app_client_path, "app-client")

    assert "--surface public" not in hint
    assert hint != f"backend/scripts/export_openapi.py --write {app_client_path}"
