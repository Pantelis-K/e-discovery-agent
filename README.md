# E-Discovery Agent

This repository now includes a basic full-stack skeleton:

- React + Vite + MUI frontend in `frontend/`
- Django REST API backend in `backend/`

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173/.
