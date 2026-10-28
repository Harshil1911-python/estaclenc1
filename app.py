from flask import Flask
import os

from core.db import get_db, close_db, init_db, migrate_db
from routes.auth import auth as auth_bp
from routes.admin import admin as admin_bp
from routes.agent import agent as agent_bp
from routes.client import client as client_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = 'estacle_secret_key_change_in_production_2026'
    app.config['DATABASE'] = os.path.join(app.instance_path, 'estacle.db')
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads', 'properties')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'static', 'uploads', 'avatars'), exist_ok=True)

    app.teardown_appcontext(close_db)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(client_bp)

    with app.app_context():
        init_db()
        migrate_db()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
