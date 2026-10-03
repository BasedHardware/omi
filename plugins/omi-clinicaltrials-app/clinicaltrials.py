from __future__ import annotations

from typing import Any, Optional

import httpx

from models import RecruitingTrialsRequest, SearchTrialsRequest


BASE_URL = "https://clinicaltrials.gov/api/v2"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_SUMMARY_CHARS = 700


class ClinicalTrialsError(Exception):
    """A safe, user-facing provider or payload error."""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _format_enum(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return "unknown"
    return text.replace("_", " ").title()


def _format_date(value: Any) -> str:
    return _clean_text(_as_dict(value).get("date"), 40) or "unknown"


async def _get_json(
    client: httpx.AsyncClient,
    path: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    try:
        response = await client.get(f"{BASE_URL}{path}", params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise ClinicalTrialsError("ClinicalTrials.gov study not found") from exc
        raise ClinicalTrialsError(f"ClinicalTrials.gov returned HTTP {status}") from exc
    except httpx.RequestError as exc:
        raise ClinicalTrialsError(
            f"ClinicalTrials.gov request failed: {type(exc).__name__}"
        ) from exc

    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ClinicalTrialsError("ClinicalTrials.gov response exceeded the size limit")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ClinicalTrialsError("ClinicalTrials.gov returned malformed JSON") from exc

    if not isinstance(payload, dict):
        raise ClinicalTrialsError(
            "ClinicalTrials.gov returned an unexpected response shape"
        )
    return payload


def _search_params(request: SearchTrialsRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "pageSize": request.page_size,
        "countTotal": "true",
    }
    if request.condition:
        params["query.cond"] = request.condition
    if request.intervention:
        params["query.intr"] = request.intervention
    if request.location:
        params["query.locn"] = request.location
    if request.status:
        params["filter.overallStatus"] = request.status
    if request.phase:
        params["filter.advanced"] = f"AREA[Phase]({request.phase})"
    return params


def _format_location(location: Any) -> str:
    location = _as_dict(location)
    parts = [
        _clean_text(location.get("facility"), 100),
        _clean_text(location.get("city"), 60),
        _clean_text(location.get("state"), 60),
        _clean_text(location.get("country"), 60),
    ]
    return ", ".join(part for part in parts if part) or "location not listed"


def _protocol(study: Any) -> dict[str, Any]:
    return _as_dict(_as_dict(study).get("protocolSection"))


def _format_study_search_row(study: Any) -> str:
    protocol = _protocol(study)
    identification = _as_dict(protocol.get("identificationModule"))
    status = _as_dict(protocol.get("statusModule"))
    conditions = _as_dict(protocol.get("conditionsModule"))
    design = _as_dict(protocol.get("designModule"))
    contacts = _as_dict(protocol.get("contactsLocationsModule"))

    nct_id = _clean_text(identification.get("nctId"), 20) or "NCT unknown"
    title = (
        _clean_text(
            identification.get("briefTitle") or identification.get("officialTitle"),
            180,
        )
        or "Untitled study"
    )
    status_name = _format_enum(status.get("overallStatus"))
    condition_text = ", ".join(
        _clean_text(item, 60)
        for item in _as_list(conditions.get("conditions"))[:4]
        if _clean_text(item, 60)
    )
    phases = ", ".join(
        _format_enum(item) for item in _as_list(design.get("phases"))[:2]
    )
    locations = _as_list(contacts.get("locations"))
    location_text = "; ".join(_format_location(item) for item in locations[:2])

    lines = [
        f"- {nct_id}: {title}",
        f"  Status: {status_name}",
    ]
    if condition_text:
        lines.append(f"  Conditions: {condition_text}")
    if phases:
        lines.append(f"  Phase: {phases}")
    if location_text:
        lines.append(f"  Locations: {location_text}")
    return "\n".join(lines)


def _format_study_details(study: Any) -> str:
    protocol = _protocol(study)
    identification = _as_dict(protocol.get("identificationModule"))
    status = _as_dict(protocol.get("statusModule"))
    sponsor = _as_dict(protocol.get("sponsorCollaboratorsModule"))
    description = _as_dict(protocol.get("descriptionModule"))
    conditions = _as_dict(protocol.get("conditionsModule"))
    design = _as_dict(protocol.get("designModule"))
    enrollment = _as_dict(design.get("enrollmentInfo"))
    eligibility = _as_dict(protocol.get("eligibilityModule"))
    contacts = _as_dict(protocol.get("contactsLocationsModule"))

    nct_id = _clean_text(identification.get("nctId"), 20) or "NCT unknown"
    title = (
        _clean_text(
            identification.get("officialTitle") or identification.get("briefTitle"),
            260,
        )
        or "Untitled study"
    )
    summary = _clean_text(description.get("briefSummary"), MAX_SUMMARY_CHARS)
    condition_text = ", ".join(
        _clean_text(item, 70)
        for item in _as_list(conditions.get("conditions"))[:8]
        if _clean_text(item, 70)
    )
    phases = ", ".join(_format_enum(item) for item in _as_list(design.get("phases")))
    lead_sponsor = _clean_text(_as_dict(sponsor.get("leadSponsor")).get("name"), 140)
    locations = _as_list(contacts.get("locations"))

    lines = [
        f"{nct_id}: {title}",
        f"Status: {_format_enum(status.get('overallStatus'))}",
        f"Study type: {_format_enum(design.get('studyType'))}",
        f"Phase: {phases or 'not applicable'}",
        f"Conditions: {condition_text or 'not listed'}",
        f"Lead sponsor: {lead_sponsor or 'not listed'}",
        (
            "Enrollment: "
            f"{enrollment.get('count', 'unknown')} "
            f"({_format_enum(enrollment.get('type'))})"
        ),
        f"Start: {_format_date(status.get('startDateStruct'))}",
        f"Primary completion: {_format_date(status.get('primaryCompletionDateStruct'))}",
        (
            "Eligibility: "
            f"{_clean_text(eligibility.get('sex'), 30) or 'any sex'}, "
            f"minimum age {_clean_text(eligibility.get('minimumAge'), 30) or 'not listed'}"
        ),
    ]
    if locations:
        lines.append("Locations:")
        lines.extend(f"- {_format_location(item)}" for item in locations[:5])
        if len(locations) > 5:
            lines.append(f"- ...and {len(locations) - 5} more")
    if summary:
        lines.append(f"Summary: {summary}")
    lines.append(f"Source: https://clinicaltrials.gov/study/{nct_id}")
    lines.append("This is study information, not medical advice.")
    return "\n".join(lines)


async def search_trials(client: httpx.AsyncClient, request: SearchTrialsRequest) -> str:
    payload = await _get_json(client, "/studies", _search_params(request))
    studies = payload.get("studies")
    if studies is not None and not isinstance(studies, list):
        raise ClinicalTrialsError(
            "ClinicalTrials.gov returned an unexpected studies payload"
        )
    studies = _as_list(studies)
    total = payload.get("totalCount")
    if not isinstance(total, int):
        total = len(studies)

    if not studies:
        return (
            "No ClinicalTrials.gov studies matched the request. "
            "Try broadening the condition, location, status, or phase."
        )

    terms = [
        label
        for label in (
            request.condition,
            request.intervention,
            request.location,
        )
        if label
    ]
    lines = [
        f"Found {total} matching studies; showing {len(studies)} for "
        + ", ".join(terms)
        + ".",
        *(_format_study_search_row(study) for study in studies),
        "Source: ClinicalTrials.gov. This is study information, not medical advice.",
    ]
    return "\n".join(lines)


async def find_recruiting_trials(
    client: httpx.AsyncClient, request: RecruitingTrialsRequest
) -> str:
    return await search_trials(
        client,
        SearchTrialsRequest(
            condition=request.condition,
            location=request.location,
            status="RECRUITING",
            page_size=request.page_size,
        ),
    )


async def get_trial(client: httpx.AsyncClient, nct_id: str) -> str:
    payload = await _get_json(client, f"/studies/{nct_id}")
    protocol = _protocol(payload)
    if not protocol:
        raise ClinicalTrialsError(
            "ClinicalTrials.gov returned no protocol data for the study"
        )
    return _format_study_details(payload)
