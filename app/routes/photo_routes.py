import os
import base64
import hashlib
from pathlib import Path
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app, jsonify, send_file, abort)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.agreement import RentalAgreement
from app.models.photo import IdentityPhoto

photo_bp = Blueprint('photo', __name__, url_prefix='/photos')

MAX_PHOTO_SIZE = 5 * 1024 * 1024   # 5 MB
MAX_DOC_SIZE   = 8 * 1024 * 1024   # 8 MB
ALLOWED_DOC_EXTS = {'jpg', 'jpeg', 'png', 'pdf'}

DOCUMENT_TYPES = [
    ('citizenship',     'Citizenship Certificate (नागरिकता)'),
    ('passport',        'Passport (राहदानी)'),
    ('driving_license', 'Driving License (सवारी चालक अनुमतिपत्र)'),
    ('voter_id',        'Voter ID Card (मतदाता परिचयपत्र)'),
    ('national_id',     'National ID Card (राष्ट्रिय परिचयपत्र)'),
]


def _assert_party(agreement):
    if current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        abort(403)


@photo_bp.route('/capture/<int:agreement_id>')
@login_required
def capture_photo(agreement_id):
    agreement = RentalAgreement.query.get_or_404(agreement_id)
    _assert_party(agreement)

    existing = IdentityPhoto.query.filter_by(
        user_id=current_user.id, agreement_id=agreement_id).first()
    is_tenant = current_user.id == agreement.tenant_id

    return render_template('photos/capture_photo.html',
                           agreement=agreement,
                           existing_photo=existing,
                           is_tenant=is_tenant,
                           document_types=DOCUMENT_TYPES)


@photo_bp.route('/save/<int:agreement_id>', methods=['POST'])
@login_required
def save_photo(agreement_id):
    agreement = RentalAgreement.query.get_or_404(agreement_id)
    _assert_party(agreement)

    consent = request.form.get('consent') in ('true', 'on')
    if not consent:
        return jsonify({'success': False, 'message': 'Consent is required.'}), 400

    photo_data = request.form.get('photo_data', '')
    if not photo_data:
        return jsonify({'success': False, 'message': 'No photo data received.'}), 400

    if ',' in photo_data:
        photo_data = photo_data.split(',', 1)[1]

    try:
        photo_bytes = base64.b64decode(photo_data)
    except Exception:
        return jsonify({'success': False, 'message': 'Invalid photo data.'}), 400

    if len(photo_bytes) > MAX_PHOTO_SIZE:
        return jsonify({'success': False, 'message': 'Photo too large (max 5 MB).'}), 400

    photos_dir = current_app.config['PHOTOS_DIR']
    Path(photos_dir).mkdir(parents=True, exist_ok=True)

    photo_filename = f"photo_{current_user.id}_{agreement_id}.jpg"
    photo_path = os.path.join(photos_dir, photo_filename)
    with open(photo_path, 'wb') as f:
        f.write(photo_bytes)
    photo_hash = hashlib.sha256(photo_bytes).hexdigest()

    # ── Document upload (tenant only, optional but strongly encouraged) ───────
    doc_file = request.files.get('document_file')
    doc_path_saved = None
    doc_type = request.form.get('document_type', '').strip()

    is_tenant = current_user.id == agreement.tenant_id
    if is_tenant and doc_file and doc_file.filename:
        ext = doc_file.filename.rsplit('.', 1)[-1].lower()
        if ext not in ALLOWED_DOC_EXTS:
            return jsonify({'success': False,
                            'message': 'Document must be JPG, PNG, or PDF.'}), 400
        doc_bytes = doc_file.read()
        if len(doc_bytes) > MAX_DOC_SIZE:
            return jsonify({'success': False,
                            'message': 'Document too large (max 8 MB).'}), 400

        docs_dir = os.path.join(photos_dir, 'documents')
        Path(docs_dir).mkdir(parents=True, exist_ok=True)
        doc_filename = f"doc_{current_user.id}_{agreement_id}.{ext}"
        doc_path_saved = os.path.join(docs_dir, doc_filename)
        with open(doc_path_saved, 'wb') as f:
            f.write(doc_bytes)

    # ── Persist ──────────────────────────────────────────────────────────────
    existing = IdentityPhoto.query.filter_by(
        user_id=current_user.id, agreement_id=agreement_id).first()

    if existing:
        existing.photo_encrypted_path = photo_path
        existing.photo_hash_sha256 = photo_hash
        existing.consent_given = True
        if doc_path_saved:
            existing.document_path = doc_path_saved
            existing.document_type = doc_type
            existing.document_approved = False   # reset approval when re-uploaded
            existing.document_approved_at = None
            existing.document_approved_by = None
    else:
        record = IdentityPhoto(
            user_id=current_user.id,
            agreement_id=agreement_id,
            photo_encrypted_path=photo_path,
            photo_hash_sha256=photo_hash,
            consent_given=True,
            purpose='agreement_evidence',
            document_path=doc_path_saved,
            document_type=doc_type if doc_path_saved else None,
        )
        db.session.add(record)

    db.session.commit()

    # ── Post a chat notification so landlord can see & approve ───────────────
    if is_tenant and doc_path_saved:
        _post_doc_chat_notification(agreement, doc_type)

    return jsonify({'success': True, 'message': 'Photo and document saved successfully.'})


def _post_doc_chat_notification(agreement, doc_type):
    """Post an encrypted system message notifying landlord that document was uploaded."""
    from app.models.request import AgreementRequest
    from app.models.chat import ChatThread
    from app.services.chat_service import encrypt_message
    from app.models.chat import ChatMessage

    req = AgreementRequest.query.filter_by(agreement_id=agreement.id).first()
    if not req:
        return
    thread = req.chat_thread
    if not thread:
        return

    doc_label = dict(DOCUMENT_TYPES).get(doc_type, doc_type or 'Identity Document')
    text = (
        f"📋 {current_user.full_name} (Tenant) has uploaded their identity photo "
        f"and {doc_label}. "
        f"Please review and approve the document from the Agreement page."
    )
    try:
        ct, nonce, h = encrypt_message(thread.encrypted_thread_key, text)
        msg = ChatMessage(thread_id=thread.id, sender_id=current_user.id,
                          ciphertext_b64=ct, nonce_b64=nonce,
                          message_hash=h, is_system=True)
        db.session.add(msg)
        db.session.commit()
    except Exception:
        pass


@photo_bp.route('/approve-document/<int:agreement_id>', methods=['POST'])
@login_required
def approve_document(agreement_id):
    """Landlord approves the tenant's uploaded identity document."""
    agreement = RentalAgreement.query.get_or_404(agreement_id)
    if current_user.id != agreement.landlord_id:
        flash('Only the landlord can approve documents.', 'error')
        return redirect(url_for('agreement.view_agreement', agreement_id=agreement_id))

    tenant_photo = IdentityPhoto.query.filter_by(
        user_id=agreement.tenant_id, agreement_id=agreement_id).first()
    if not tenant_photo or not tenant_photo.document_path:
        flash('No tenant document to approve.', 'error')
        return redirect(url_for('agreement.view_agreement', agreement_id=agreement_id))

    from datetime import datetime
    tenant_photo.document_approved = True
    tenant_photo.document_approved_at = datetime.utcnow()
    tenant_photo.document_approved_by = current_user.id
    db.session.commit()

    # Post approval notification to chat
    from app.models.request import AgreementRequest
    from app.models.chat import ChatThread, ChatMessage
    from app.services.chat_service import encrypt_message
    req = AgreementRequest.query.filter_by(agreement_id=agreement_id).first()
    if req and req.chat_thread:
        try:
            text = (f"✅ Landlord {current_user.full_name} has approved the tenant's "
                    f"identity document. The agreement is now fully verified.")
            ct, nonce, h = encrypt_message(req.chat_thread.encrypted_thread_key, text)
            db.session.add(ChatMessage(thread_id=req.chat_thread.id,
                                       sender_id=current_user.id,
                                       ciphertext_b64=ct, nonce_b64=nonce,
                                       message_hash=h, is_system=True))
            db.session.commit()
        except Exception:
            pass

    flash('Tenant document approved.', 'success')
    return redirect(url_for('agreement.view_agreement', agreement_id=agreement_id))


@photo_bp.route('/view/<int:photo_id>')
@login_required
def serve_photo(photo_id):
    photo = IdentityPhoto.query.get_or_404(photo_id)
    agreement = RentalAgreement.query.get(photo.agreement_id)
    if not agreement or current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        abort(403)
    if not photo.photo_encrypted_path or not os.path.exists(photo.photo_encrypted_path):
        abort(404)
    return send_file(photo.photo_encrypted_path, mimetype='image/jpeg')


@photo_bp.route('/view-document/<int:agreement_id>')
@login_required
def serve_document(agreement_id):
    """Serve the tenant's identity document — visible to both parties."""
    agreement = RentalAgreement.query.get_or_404(agreement_id)
    if current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        abort(403)
    photo = IdentityPhoto.query.filter_by(
        user_id=agreement.tenant_id, agreement_id=agreement_id).first()
    if not photo or not photo.document_path or not os.path.exists(photo.document_path):
        abort(404)
    ext = photo.document_path.rsplit('.', 1)[-1].lower()
    mime = 'application/pdf' if ext == 'pdf' else 'image/jpeg'
    return send_file(photo.document_path, mimetype=mime)
