import os
import base64
import hashlib
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.agreement import RentalAgreement
from app.models.photo import IdentityPhoto

photo_bp = Blueprint('photo', __name__, url_prefix='/photos')

MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5MB


@photo_bp.route('/capture/<int:agreement_id>')
@login_required
def capture_photo(agreement_id):
    agreement = RentalAgreement.query.get_or_404(agreement_id)
    if current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.home'))

    existing = IdentityPhoto.query.filter_by(
        user_id=current_user.id, agreement_id=agreement_id).first()

    return render_template('photos/capture_photo.html',
                           agreement=agreement,
                           existing_photo=existing)


@photo_bp.route('/save/<int:agreement_id>', methods=['POST'])
@login_required
def save_photo(agreement_id):
    agreement = RentalAgreement.query.get_or_404(agreement_id)
    if current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        return jsonify({'success': False, 'message': 'Access denied.'}), 403

    consent = request.form.get('consent') == 'true' or request.form.get('consent') == 'on'
    if not consent:
        return jsonify({'success': False, 'message': 'Consent is required to capture photo.'}), 400

    photo_data = request.form.get('photo_data') or ''
    if not photo_data:
        return jsonify({'success': False, 'message': 'No photo data received.'}), 400

    # Strip data URL header if present
    if ',' in photo_data:
        photo_data = photo_data.split(',', 1)[1]

    try:
        photo_bytes = base64.b64decode(photo_data)
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid photo data.'}), 400

    if len(photo_bytes) > MAX_PHOTO_SIZE:
        return jsonify({'success': False, 'message': 'Photo too large (max 5MB).'}), 400

    # Save photo
    photos_dir = current_app.config['PHOTOS_DIR']
    Path(photos_dir).mkdir(parents=True, exist_ok=True)

    filename = f"photo_{current_user.id}_{agreement_id}.jpg"
    photo_path = os.path.join(photos_dir, filename)

    with open(photo_path, 'wb') as f:
        f.write(photo_bytes)

    photo_hash = hashlib.sha256(photo_bytes).hexdigest()

    # Update or create record
    existing = IdentityPhoto.query.filter_by(
        user_id=current_user.id, agreement_id=agreement_id).first()

    if existing:
        existing.photo_encrypted_path = photo_path
        existing.photo_hash_sha256 = photo_hash
        existing.consent_given = True
    else:
        record = IdentityPhoto(
            user_id=current_user.id,
            agreement_id=agreement_id,
            photo_encrypted_path=photo_path,
            photo_hash_sha256=photo_hash,
            consent_given=True,
            purpose='agreement_evidence',
        )
        db.session.add(record)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Photo captured and saved successfully.'})


@photo_bp.route('/view/<int:photo_id>')
@login_required
def serve_photo(photo_id):
    """Serve a stored identity photo — only accessible to parties of the agreement."""
    from flask import send_file, abort
    photo = IdentityPhoto.query.get_or_404(photo_id)

    # Only the agreement parties can view photos
    agreement = RentalAgreement.query.get(photo.agreement_id)
    if not agreement or current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        abort(403)

    if not photo.photo_encrypted_path or not os.path.exists(photo.photo_encrypted_path):
        abort(404)

    return send_file(photo.photo_encrypted_path, mimetype='image/jpeg')
