# Estacle — Real Estate CRM

Python · Flask · HTML · CSS · SQLite

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5001**

## Demo logins

| Role     | Email                  | Password     |
|----------|------------------------|--------------|
| Admin    | admin@estacle.com      | admin123     |
| Agent    | agent@estacle.com      | agent123     |
| Customer | customer@estacle.com   | customer123  |

## Project structure

```
estacle/
├── app.py                 # App factory, registers blueprints
├── core/
│   ├── db.py              # Database connection, init, migrations
│   └── helpers.py         # Auth decorators, money, activity log
├── routes/
│   ├── auth.py            # Login, logout, redirects
│   ├── admin.py           # Admin dashboard & all admin features
│   ├── agent.py           # Agent dashboard
│   └── client.py          # Client portal
├── templates/             # Jinja2 templates
├── static/                # CSS, images, uploads
└── instance/              # SQLite database (created at runtime)
```

## Stack

Flask, Jinja2, SQLite, plain CSS, Chart.js
