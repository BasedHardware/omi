# Omi OpenAlex Scholar Integration App

[![Omi Chat Tools](https://img.shields.io/badge/Omi-Chat_Tools_Plugin-blue)](https://omi.me)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-brightgreen.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-teal.svg)](https://fastapi.tiangolo.com)
[![OpenAlex API](https://img.shields.io/badge/API-OpenAlex-orange)](https://openalex.org)

A community Omi integration app connecting Omi smart wearables (glasses, audio necklaces, and apps) to the **OpenAlex Global Scholarly Knowledge Graph** — the world's most comprehensive open index of scientific research with over **250 million research papers**, **90 million authors**, and **100,000 institutions**.

Provides **zero-authentication**, instant voice-guided scientific search, researcher metrics, academic institution rankings, and topic exploration.

---

## 🛠️ Registered Omi Chat Tools

Exposed via `GET /.well-known/omi-tools.json`:

| Tool Name | Endpoint | Method | Example Voice Queries |
|---|---|---|---|
| `search_research_papers` | `/tools/search_research_papers` | `POST` | *"Find recent research papers on transformer neural networks"*, *"What are the most cited papers on CRISPR Cas9?"* |
| `get_author_profile` | `/tools/get_author_profile` | `POST` | *"Who is Yann LeCun and what is his h-index?"*, *"Look up research metrics for Geoffrey Hinton"* |
| `get_institution_summary` | `/tools/get_institution_summary` | `POST` | *"How many papers has Stanford University published?"*, *"What are the top research outputs of MIT?"* |
| `explore_academic_topic` | `/tools/explore_academic_topic` | `POST` | *"Explain the research field of Quantum Computing"*, *"What domain does Epigenetics belong to?"* |

---

## 🚀 Key Features

1. **Zero Auth / No API Keys Required**:
   - Uses OpenAlex's public unauthenticated REST API. Works instantly out of the box.
2. **Strict Omi Protocol Compliance**:
   - Strict `ChatToolResponse` contract (`result: Optional[str] = None`, `error: Optional[str] = None`).
   - Pydantic v2 input validation with automatic whitespace trimming and boundary bounds.
3. **Rich Academic Metadata**:
   - Paper searches filter for verified academic articles, preprints, and reviews (`filter=type:article|preprint|review`), reporting title, authors, publication year, citation counts, DOI, and direct open-access PDF links (`best_oa_location.pdf_url`).
   - Author lookups provide h-index, i10-index, 2-year mean citedness, last known institutional affiliation(s), and primary research topics.
   - Institution summaries include classification, ROR ID, country, total publications, and global citation counts.
   - Topic exploration uses OpenAlex's modern `/topics` taxonomy with domain, field, subfield hierarchy, descriptions, and keywords.
4. **Live Smoke Tested**:
   - Full live test suite in `smoke_test.py` validates all endpoints, manifest schema, and edge cases.

---

## 💻 Local Setup & Testing

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Live Smoke Tests
```bash
python smoke_test.py
```

### 3. Run Development Server
```bash
uvicorn main:app --reload --port 8080
```

---

## ☁️ Deployment

Deployable on Railway, Render, or any container host:
- **Railway**: Uses the provided `railway.toml` with Nixpacks builder.
- **Docker / Cloud Run**: Uses the standard `Procfile` (`web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}`).
