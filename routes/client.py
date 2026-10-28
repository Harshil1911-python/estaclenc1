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


client = Blueprint('client', __name__)

@client.route('/client')
@login_required
@role_required('customer')
def client_dashboard():
    db = get_db()
    migrate_db()
    currency = get_setting('currency', 'INR')
    stats = {
        'available_properties': db.execute("SELECT COUNT(*) FROM properties WHERE status = 'available'").fetchone()[0],
        'my_appointments': db.execute(
            "SELECT COUNT(*) FROM appointments a JOIN clients c ON a.client_id = c.id WHERE c.email = ?",
            (session.get('email'),)
        ).fetchone()[0],
    }
    recent = db.execute(
        "SELECT id, title, price, city, property_type, listing_type, photos, status FROM properties WHERE status = 'available' ORDER BY created_at DESC LIMIT 6"
    ).fetchall()
    return render_template('client.html', stats=stats, recent=recent, currency=currency, format_money=format_money)


@client.route('/client/browse')
@login_required
@role_required('customer')
def client_browse():
    db = get_db()
    migrate_db()
    q = request.args.get('q', '').strip()
    listing_type = request.args.get('listing_type', '').strip()
    prop_type = request.args.get('property_type', '').strip()
    city = request.args.get('city', '').strip()
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()
    bedrooms = request.args.get('bedrooms', '').strip()
    sql = "SELECT * FROM properties WHERE status = 'available'"
    params = []
    if q:
        sql += " AND (title LIKE ? OR city LIKE ? OR address LIKE ? OR description LIKE ?)"
        params.extend([f'%{q}%'] * 4)
    if listing_type in ('sale', 'rent'):
        sql += " AND listing_type = ?"
        params.append(listing_type)
    if prop_type:
        sql += " AND property_type = ?"
        params.append(prop_type)
    if city:
        sql += " AND city LIKE ?"
        params.append(f'%{city}%')
    if min_price:
        try:
            sql += " AND price >= ?"
            params.append(float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            sql += " AND price <= ?"
            params.append(float(max_price))
        except ValueError:
            pass
    if bedrooms:
        try:
            sql += " AND bedrooms >= ?"
            params.append(int(bedrooms))
        except ValueError:
            pass
    sql += " ORDER BY created_at DESC"
    properties = db.execute(sql, params).fetchall()
    currency = get_setting('currency', 'INR')
    filters = {
        'q': q, 'listing_type': listing_type, 'property_type': prop_type, 'city': city,
        'min_price': min_price, 'max_price': max_price, 'bedrooms': bedrooms
    }
    saved = db.execute(
        'SELECT id, name, filters FROM saved_searches WHERE user_id = ? ORDER BY created_at DESC',
        (session['user_id'],)
    ).fetchall()
    return render_template(
        'client_browse.html',
        properties=properties,
        currency=currency,
        format_money=format_money,
        filters=filters,
        saved_searches=saved
    )


@client.route('/client/saved-search', methods=['POST'])
@login_required
@role_required('customer')
def client_save_search():
    import json
    name = request.form.get('name', '').strip() or 'My Search'
    filters = {
        'q': request.form.get('q', ''),
        'listing_type': request.form.get('listing_type', ''),
        'property_type': request.form.get('property_type', ''),
        'city': request.form.get('city', ''),
        'min_price': request.form.get('min_price', ''),
        'max_price': request.form.get('max_price', ''),
        'bedrooms': request.form.get('bedrooms', ''),
    }
    db = get_db()
    migrate_db()
    db.execute(
        'INSERT INTO saved_searches (user_id, name, filters) VALUES (?, ?, ?)',
        (session['user_id'], name, json.dumps(filters))
    )
    db.commit()
    flash(f'Search "{name}" saved.', 'success')
    return redirect(url_for('client.client_browse', **{k: v for k, v in filters.items() if v}))


@client.route('/client/saved-search/<int:sid>/delete', methods=['POST'])
@login_required
@role_required('customer')
def client_delete_saved_search(sid):
    db = get_db()
    db.execute('DELETE FROM saved_searches WHERE id = ? AND user_id = ?', (sid, session['user_id']))
    db.commit()
    flash('Saved search removed.', 'info')
    return redirect(url_for('client.client_browse'))


@client.route('/client/saved-search/<int:sid>')
@login_required
@role_required('customer')
def client_apply_saved_search(sid):
    import json
    db = get_db()
    row = db.execute(
        'SELECT filters FROM saved_searches WHERE id = ? AND user_id = ?',
        (sid, session['user_id'])
    ).fetchone()
    if not row:
        flash('Saved search not found.', 'warning')
        return redirect(url_for('client.client_browse'))
    filters = json.loads(row['filters'])
    return redirect(url_for('client.client_browse', **{k: v for k, v in filters.items() if v}))


@client.route('/client/property/<int:prop_id>')
@login_required
@role_required('customer')
def client_property(prop_id):
    db = get_db()
    migrate_db()
    prop = db.execute(
        "SELECT p.*, u.full_name as agent_name FROM properties p LEFT JOIN users u ON p.agent_id = u.id WHERE p.id = ? AND p.status = 'available'",
        (prop_id,)
    ).fetchone()
    if not prop:
        flash('Property not found or unavailable.', 'warning')
        return redirect(url_for('client.client_browse'))
    photos = [p.strip() for p in (prop['photos'] or '').split(',') if p.strip()]
    currency = get_setting('currency', 'INR')
    return render_template('client_property.html', prop=prop, photos=photos, currency=currency, format_money=format_money)


@client.route('/client/request-viewing/<int:prop_id>', methods=['POST'])
@login_required
@role_required('customer')
def client_request_viewing(prop_id):
    db = get_db()
    prop = db.execute("SELECT id, title, agent_id FROM properties WHERE id = ? AND status = 'available'", (prop_id,)).fetchone()
    if not prop:
        flash('Property not available.', 'danger')
        return redirect(url_for('client.client_browse'))
    # Find or create client record for this user
    client = db.execute("SELECT id FROM clients WHERE email = ?", (session.get('email'),)).fetchone()
    if not client:
        db.execute(
            "INSERT INTO clients (full_name, email, phone, status, notes) VALUES (?, ?, ?, 'lead', 'Portal customer')",
            (session.get('full_name'), session.get('email'), '')
        )
        db.commit()
        client = db.execute("SELECT id FROM clients WHERE email = ?", (session.get('email'),)).fetchone()
    preferred = request.form.get('preferred_date', '').strip()
    notes = request.form.get('notes', '').strip()
    db.execute(
        "INSERT INTO appointments (client_id, property_id, agent_id, appointment_date, status, notes) VALUES (?, ?, ?, ?, 'scheduled', ?)",
        (client['id'], prop_id, prop['agent_id'], preferred or None, notes or 'Viewing requested via client portal')
    )
    db.commit()
    log_activity('Viewing requested', 'property', prop_id, prop['title'])
    flash('Viewing request submitted. An agent will contact you soon.', 'success')
    return redirect(url_for('client.client_appointments'))


@client.route('/client/appointments')
@login_required
@role_required('customer')
def client_appointments():
    db = get_db()
    rows = db.execute(
        """SELECT a.*, p.title as property_title, p.city as property_city
           FROM appointments a
           JOIN clients c ON a.client_id = c.id
           LEFT JOIN properties p ON a.property_id = p.id
           WHERE c.email = ?
           ORDER BY a.appointment_date DESC""",
        (session.get('email'),)
    ).fetchall()
    return render_template('client_appointments.html', appointments=rows)


@client.route('/client/profile', methods=['GET', 'POST'])
@login_required
@role_required('customer')
def client_profile():
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '').strip()
        if not full_name:
            flash('Name is required.', 'danger')
            return redirect(url_for('client.client_profile'))
        if password:
            db.execute('UPDATE users SET full_name=?, phone=?, password=? WHERE id=?',
                       (full_name, phone, generate_password_hash(password), session['user_id']))
        else:
            db.execute('UPDATE users SET full_name=?, phone=? WHERE id=?',
                       (full_name, phone, session['user_id']))
        db.commit()
        session['full_name'] = full_name
        flash('Profile updated.', 'success')
        return redirect(url_for('client.client_profile'))
    return render_template('client_profile.html', user=user)


@client.route('/client/favorites')
@login_required
@role_required('customer')
def client_favorites():
    db = get_db()
    migrate_db()
    rows = db.execute(
        """SELECT p.* FROM favorites f JOIN properties p ON f.property_id = p.id
           WHERE f.user_id = ? ORDER BY f.created_at DESC""",
        (session['user_id'],)
    ).fetchall()
    currency = get_setting('currency', 'INR')
    return render_template('client_favorites.html', properties=rows, currency=currency, format_money=format_money)


@client.route('/client/favorites/toggle/<int:prop_id>', methods=['POST'])
@login_required
@role_required('customer')
def client_toggle_favorite(prop_id):
    db = get_db()
    migrate_db()
    existing = db.execute(
        "SELECT id FROM favorites WHERE user_id = ? AND property_id = ?",
        (session['user_id'], prop_id)
    ).fetchone()
    if existing:
        db.execute("DELETE FROM favorites WHERE id = ?", (existing['id'],))
        flash('Removed from favorites.', 'success')
    else:
        db.execute(
            "INSERT OR IGNORE INTO favorites (user_id, property_id) VALUES (?, ?)",
            (session['user_id'], prop_id)
        )
        flash('Saved to favorites.', 'success')
    db.commit()
    return redirect(request.referrer or url_for('client.client_browse'))


@client.route('/client/inquiry/<int:prop_id>', methods=['POST'])
@login_required
@role_required('customer')
def client_inquiry(prop_id):
    db = get_db()
    migrate_db()
    prop = db.execute("SELECT id, title FROM properties WHERE id = ? AND status = 'available'", (prop_id,)).fetchone()
    if not prop:
        flash('Property not found.', 'warning')
        return redirect(url_for('client.client_browse'))
    message = request.form.get('message', '').strip()
    phone = request.form.get('phone', '').strip() or session.get('email', '')
    if not message:
        flash('Please write a message.', 'danger')
        return redirect(url_for('client.client_property', prop_id=prop_id))
    db.execute(
        '''INSERT INTO inquiries (property_id, user_id, full_name, email, phone, message)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (prop_id, session['user_id'], session.get('full_name', ''), session.get('email', ''), phone, message)
    )
    db.commit()
    log_activity('Property inquiry', 'property', prop_id, prop['title'])
    flash('Your inquiry was sent. An agent will contact you soon.', 'success')
    return redirect(url_for('client.client_property', prop_id=prop_id))



