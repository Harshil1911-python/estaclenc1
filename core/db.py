import sqlite3
import os
from flask import g, current_app
from werkzeug.security import generate_password_hash


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'agent', 'customer')),
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            property_type TEXT NOT NULL,
            status TEXT DEFAULT 'available',
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            bedrooms INTEGER,
            bathrooms REAL,
            area_sqft REAL,
            agent_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            status TEXT DEFAULT 'lead',
            notes TEXT,
            agent_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            property_id INTEGER,
            agent_id INTEGER,
            appointment_date TIMESTAMP,
            status TEXT DEFAULT 'scheduled',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients (id),
            FOREIGN KEY (property_id) REFERENCES properties (id),
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            assigned_to INTEGER,
            related_client_id INTEGER,
            related_property_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to) REFERENCES users (id),
            FOREIGN KEY (related_client_id) REFERENCES clients (id),
            FOREIGN KEY (related_property_id) REFERENCES properties (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            property_id INTEGER,
            client_id INTEGER,
            agent_id INTEGER,
            stage TEXT DEFAULT 'offer',
            value REAL DEFAULT 0,
            commission_rate REAL DEFAULT 2.5,
            expected_close TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (property_id) REFERENCES properties (id),
            FOREIGN KEY (client_id) REFERENCES clients (id),
            FOREIGN KEY (agent_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            doc_type TEXT,
            related_type TEXT,
            related_id INTEGER,
            expiry_date TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    db.commit()

    cursor = db.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        users = [
            ('admin@estacle.com', generate_password_hash('admin123'), 'System Admin', 'admin', '+1-555-0100'),
            ('agent@estacle.com', generate_password_hash('agent123'), 'John Agent', 'agent', '+1-555-0101'),
            ('customer@estacle.com', generate_password_hash('customer123'), 'Sarah Customer', 'customer', '+1-555-0102'),
        ]
        db.executemany(
            'INSERT INTO users (email, password, full_name, role, phone) VALUES (?, ?, ?, ?, ?)',
            users
        )
        db.commit()
        print("Default users created successfully!")
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('currency', 'INR')")
        db.commit()

    if not db.execute("SELECT value FROM settings WHERE key = 'currency'").fetchone():
        db.execute("INSERT INTO settings (key, value) VALUES ('currency', 'INR')")
        db.commit()


def migrate_db():
    """Add extra columns / tables if missing."""
    db = get_db()
    cols = {r[1] for r in db.execute('PRAGMA table_info(properties)').fetchall()}
    extras = [
        ('category', 'TEXT DEFAULT "sale"'),
        ('listing_type', 'TEXT DEFAULT "sale"'),
        ('floor', 'TEXT'),
        ('carpet_area', 'REAL'),
        ('furnishing', 'TEXT'),
        ('parking', 'TEXT'),
        ('amenities', 'TEXT'),
        ('seller_name', 'TEXT'),
        ('seller_phone', 'TEXT'),
        ('monthly_rent', 'REAL'),
        ('security_deposit', 'REAL'),
        ('maintenance', 'REAL'),
        ('per_sqft', 'REAL'),
        ('latitude', 'TEXT'),
        ('longitude', 'TEXT'),
        ('photos', 'TEXT'),
        ('year_built', 'TEXT'),
        ('facing', 'TEXT'),
    ]
    for name, typedef in extras:
        if name not in cols:
            try:
                db.execute(f'ALTER TABLE properties ADD COLUMN {name} {typedef}')
            except Exception:
                pass
    db.commit()
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    db.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        property_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, property_id),
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (property_id) REFERENCES properties (id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        source TEXT,
        interest TEXT,
        budget REAL,
        status TEXT DEFAULT 'new',
        notes TEXT,
        assigned_to INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (assigned_to) REFERENCES users (id)
    )""")
    if not db.execute("SELECT value FROM settings WHERE key = 'currency'").fetchone():
        db.execute("INSERT INTO settings (key, value) VALUES ('currency', 'INR')")
    db.execute("""CREATE TABLE IF NOT EXISTS saved_searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        filters TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS inquiries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        property_id INTEGER,
        user_id INTEGER,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        message TEXT NOT NULL,
        status TEXT DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (property_id) REFERENCES properties (id),
        FOREIGN KEY (user_id) REFERENCES users (id)
    )""")
    ucols = {r[1] for r in db.execute('PRAGMA table_info(users)').fetchall()}
    if 'avatar' not in ucols:
        try:
            db.execute('ALTER TABLE users ADD COLUMN avatar TEXT')
        except Exception:
            pass
    if 'last_seen' not in ucols:
        try:
            db.execute('ALTER TABLE users ADD COLUMN last_seen TIMESTAMP')
        except Exception:
            pass
    db.commit()
