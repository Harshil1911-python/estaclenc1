from functools import wraps
from flask import session, flash, redirect, url_for
from core.db import get_db


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('auth.role_redirect'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_setting(key, default=''):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        (key, value)
    )
    db.commit()


def format_money(amount, currency=None):
    if amount is None:
        return '—'
    currency = currency or get_setting('currency', 'INR')
    symbols = {'USD': '$', 'INR': '₹', 'AED': 'AED '}
    sym = symbols.get(currency, currency + ' ')
    try:
        return f"{sym}{float(amount):,.0f}"
    except (TypeError, ValueError):
        return str(amount)


def log_activity(action, entity_type=None, entity_id=None, details=None):
    try:
        db = get_db()
        uid = session.get('user_id')
        db.execute(
            'INSERT INTO activity_log (user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)',
            (uid, action, entity_type, entity_id, details)
        )
        db.commit()
    except Exception:
        pass


def get_redirect_for_role(role):
    if role == 'admin':
        return url_for('admin.admin_dashboard')
    elif role == 'agent':
        return url_for('agent.agent_dashboard')
    else:
        return url_for('client.client_dashboard')


def highlight_match(text, query):
    """Wrap case-insensitive matches of query inside text with a yellow highlight span."""
    if text is None:
        return ''
    text = str(text)
    if not query or not text:
        return text
    import re
    from markupsafe import Markup, escape
    pattern = re.compile(re.escape(query), re.IGNORECASE)

    def repl(m):
        return f'<mark class="search-hl">{escape(m.group(0))}</mark>'

    return Markup(pattern.sub(repl, escape(text)))
