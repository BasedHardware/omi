# ClinicalTrials.gov Omi App

Search public ClinicalTrials.gov study registrations from Omi conversations.

This is a standalone no-auth integration. It requires no environment variables,
OAuth connection, API key, or user account.

## Tools

- `search_clinical_trials`: search by condition, intervention, location,
  recruitment status, and phase.
- `find_recruiting_trials`: find currently recruiting studies by condition and
  optional location.
- `get_clinical_trial`: retrieve a concise public summary by NCT identifier.

## Example requests

```bash
curl -X POST http://localhost:8080/tools/search_clinical_trials \
  -H "Content-Type: application/json" \
  -d '{"condition":"type 2 diabetes","location":"Boston","page_size":3}'
```

```bash
curl -X POST http://localhost:8080/tools/get_clinical_trial \
  -H "Content-Type: application/json" \
  -d '{"nct_id":"NCT04280705"}'
```

## Privacy

Only the condition, intervention, location, status, phase, or NCT identifier
needed for the request is forwarded to ClinicalTrials.gov. Omi user identifiers
are not sent or stored.

## Medical disclaimer

This app returns public study-registration information. It does not provide
medical advice, determine eligibility, or recommend participation. Users should
discuss any study with a qualified clinician and the study team.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Run the hermetic tests:

```bash
python test_main.py
```

Health check: `GET /health`

Tool manifest: `GET /.well-known/omi-tools.json`
