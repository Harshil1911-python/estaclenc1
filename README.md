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

## Navigation (persistent sidebar)

Pages are still normal server-rendered Flask pages. `static/js/app-nav.js` (loaded by the sidebar
partials) intercepts internal links and forms, fetches the same URL, and swaps only the content
next to the sidebar, so the sidebar is never rebuilt. URLs, back/forward, refresh and bookmarks
work as before, and without JavaScript everything falls back to normal navigation.

- Add `data-no-ajax` to a link or form to force a normal page load.
- Inline page scripts are re-run on each visit inside a block: use `function name(){}` (not a
  top-level `const name = () => {}`) for anything called from inline `onclick="..."` attributes.
- Active item = the link the server marked `active` for that page, else the longest matching URL
  prefix; only one item is ever active. `.open` (expanded) and `.has-active` (current section) are
  separate classes.

## Stack

Flask, Jinja2, SQLite, plain CSS, Chart.js
