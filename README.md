# Read Between the Lines

An AI Conversation Intelligence Assistant that helps users review conversation patterns, maintain evidence-based communication profiles, and generate context-aware reply suggestions.

## Project status

Currently in the foundation stage. Application features have not been implemented yet.

## Planned technology stack

- Frontend: React, TypeScript, and Vite
- Backend: Python, FastAPI, and Pydantic
- Database: PostgreSQL with SQLAlchemy and Alembic
- Vector search: pgvector
- Local language model: Ollama
- Machine learning: scikit-learn
- Testing: pytest and frontend checks
- Development environment: Git and Docker Compose

## Project structure

- `backend/`: API and backend logic
- `frontend/`: web interface
- `data/synthetic/`: synthetic conversation data for demonstrations
- `docs/`: documentation and design decisions
- `infra/`: infrastructure configuration

## Privacy

Use synthetic conversation data in public demonstrations. Never commit real credentials or private conversation logs.

## Current environment

- Python: 3.13.5
- Node.js: 22.19.0
- npm: 10.9.3
- Git: 2.40.0

## Next steps

1. Verify the project foundation.
2. Build a minimal FastAPI endpoint.
3. Create a minimal React interface.
4. Add persistence, conversation analysis, retrieval, and personalised reply suggestions incrementally.
