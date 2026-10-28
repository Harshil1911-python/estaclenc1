from flask import Blueprint
from flask import (
    render_template, request, redirect, url_for, session, flash,
    current_app, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
import csv
import io

from core.db import get_db, migrate_db
from core.helpers import (
    login_required, role_required, get_setting, set_setting,
    format_money, log_activity, get_redirect_for_role
)


agent = Blueprint('agent', __name__)

@agent.route('/agent')
@login_required
@role_required('agent')
def agent_dashboard():
    db = get_db()
    migrate_db()
    agent_id = session['user_id']
    currency = get_setting('currency', 'INR')
    stats = {
        'my_properties': db.execute('SELECT COUNT(*) FROM properties WHERE agent_id = ?', (agent_id,)).fetchone()[0],
        'my_clients': db.execute('SELECT COUNT(*) FROM clients WHERE agent_id = ?', (agent_id,)).fetchone()[0],
        'appointments': db.execute('SELECT COUNT(*) FROM appointments WHERE agent_id = ?', (agent_id,)).fetchone()[0],
        'available': db.execute("SELECT COUNT(*) FROM properties WHERE agent_id = ? AND status = 'available'", (agent_id,)).fetchone()[0],
        'pending_tasks': db.execute("SELECT COUNT(*) FROM tasks WHERE assigned_to = ? AND status = 'pending'", (agent_id,)).fetchone()[0],
        'open_deals': db.execute("SELECT COUNT(*) FROM deals WHERE agent_id = ? AND stage NOT IN ('closed', 'lost')", (agent_id,)).fetchone()[0],
        'new_leads': db.execute("SELECT COUNT(*) FROM leads WHERE assigned_to = ? AND status = 'new'", (agent_id,)).fetchone()[0],
    }
    my_properties = db.execute('''
        SELECT id, title, price, status, city, property_type, listing_type, created_at
        FROM properties WHERE agent_id = ? ORDER BY created_at DESC LIMIT 8
    ''', (agent_id,)).fetchall()
    upcoming = db.execute('''
        SELECT a.*, c.full_name as client_name, p.title as property_title
        FROM appointments a
        LEFT JOIN clients c ON a.client_id = c.id
        LEFT JOIN properties p ON a.property_id = p.id
        WHERE a.agent_id = ? AND a.status = 'scheduled'
        ORDER BY a.appointment_date ASC LIMIT 6
    ''', (agent_id,)).fetchall()
    my_tasks = db.execute('''
        SELECT * FROM tasks WHERE assigned_to = ? AND status != 'completed'
        ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC LIMIT 6
    ''', (agent_id,)).fetchall()
    recent_leads = db.execute('''
        SELECT * FROM leads WHERE assigned_to = ? ORDER BY created_at DESC LIMIT 5
    ''', (agent_id,)).fetchall()
    return render_template('agent.html', stats=stats, my_properties=my_properties,
                           upcoming=upcoming, my_tasks=my_tasks, recent_leads=recent_leads,
                           currency=currency, format_money=format_money)



@agent.route('/agent/properties')
@login_required
@role_required('agent')
def agent_properties():
    db = get_db()
    migrate_db()
    agent_id = session['user_id']
    currency = get_setting('currency', 'INR')
    properties = db.execute('''
        SELECT * FROM properties WHERE agent_id = ? ORDER BY created_at DESC
    ''', (agent_id,)).fetchall()
    return render_template('agent_properties.html', properties=properties, currency=currency, format_money=format_money)



