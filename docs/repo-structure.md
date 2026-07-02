# Repo Structure

Living document — update as the structure evolves.
Last Updated: 02/07/2026

```
e-discovery-agent/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── e_discovery_backend/
│   │   ├── __init__.py
│   │   ├── asgi.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── manage.py
│   ├── requirements.txt
│   └── db.sqlite3
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       └── main.jsx
├── docs/
│   ├── decisions.md
│   ├── ediscovery-technical-spec.md
│   └── repo-structure.md
├── .gitignore
├── CLAUDE.md
└── README.md
```