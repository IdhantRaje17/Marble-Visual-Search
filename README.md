# Marble AI — Visual Tile Search System

AI-powered marble and tile inventory search system.
Upload a photo of any tile → get exact match, shelf location, and stock level in under 3 seconds.

## Tech Stack
- **Backend**: Python, FastAPI, PostgreSQL, pgvector
- **AI**: OpenCLIP (ViT-B-32), OpenCV
- **Frontend**: Next.js, Tailwind CSS

## Project Structure
```
marble-ai/
├── backend/    → FastAPI + AI pipeline
└── frontend/   → Next.js dashboard
```

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your DB credentials
python migrate_account_roles.py
python run_server.py
```

For an existing database, run `python migrate_tile_texture.py` once from the
`backend` directory before starting the updated application. This additive,
idempotent migration adds the optional manually entered tile texture field and
preserves existing records. Order tracking tables are created by the existing
metadata initialization.

Public registration creates a `user` account. Run
`python migrate_account_roles.py` to preserve existing `admin` and `user` roles,
add account token revocation, and promote the existing `iduraje@gmail.com`
account to Super Admin. The migration does not create accounts; if that email
does not exist, first independently verify account ownership, create the account,
and rerun the migration. Only Super Admins can manage user roles or account
status. Admins and Super Admins share the same operational features; users
retain customer features only.
To bootstrap an additional operational administrator, set
`MARBLE_ADMIN_EMAIL` and `MARBLE_ADMIN_PASSWORD` in the environment (optionally
`MARBLE_ADMIN_NAME`) and run `python seed.py`; do not put these values in source
control. Search history remains scoped to its owning account.
Authentication tokens and roles are stored per browser tab using
`sessionStorage`; each tab validates its identity and permissions against
`/api/auth/me`, allowing separate tabs or browser profiles to use different
accounts independently.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables
See `backend/.env.example`