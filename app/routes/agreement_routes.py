import os
import uuid
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models.agreement import RentalAgreement
from app.models.asset import AssetCategory, RentalAsset
from app.models.certificate import Certificate
from app.models.user import User
from app.services.crypto_service import (
    sha256_hash_file, encrypt_file_aes256gcm, rsa_sign, rsa_verify,
    encrypt_rsa_oaep, sha256_hash_bytes
)
from app.services.qr_service import generate_verification_code

agreement_bp = Blueprint('agreement', __name__, url_prefix='/agreements')

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt'}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@agreement_bp.route('/')
@login_required
def list_agreements():
    if current_user.role == 'landlord':
        agreements = RentalAgreement.query.filter_by(landlord_id=current_user.id).order_by(
            RentalAgreement.created_at.desc()).all()
    else:
        agreements = RentalAgreement.query.filter_by(tenant_id=current_user.id).order_by(
            RentalAgreement.created_at.desc()).all()
    return render_template('agreements/list.html', agreements=agreements)


@agreement_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_agreement():
    if current_user.role != 'landlord':
        flash('Only landlords can create agreements.', 'error')
        return redirect(url_for('dashboard.home'))

    categories = AssetCategory.query.order_by(AssetCategory.name).all()
    assets = RentalAsset.query.filter_by(owner_id=current_user.id, status='available').all()
    tenants = User.query.filter_by(role='tenant', is_active=True).all()

    if request.method == 'POST':
        tenant_id = request.form.get('tenant_id')
        asset_id = request.form.get('asset_id')
        rental_category = request.form.get('rental_category')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        rent_amount = request.form.get('rent_amount', 0)
        currency = request.form.get('currency', 'NPR')
        terms = request.form.get('terms', '')
        uploaded_file = request.files.get('agreement_file')

        if not tenant_id or not rental_category or not uploaded_file:
            flash('Tenant, category, and agreement file are required.', 'error')
            return render_template('agreements/create.html',
                                   categories=categories, assets=assets,
                                   tenants=tenants, form_data=request.form)

        if not _allowed_file(uploaded_file.filename):
            flash('Invalid file type. Allowed: PDF, DOC, DOCX, TXT', 'error')
            return render_template('agreements/create.html',
                                   categories=categories, assets=assets,
                                   tenants=tenants, form_data=request.form)

        agreements_dir = current_app.config['AGREEMENTS_DIR']
        Path(agreements_dir).mkdir(parents=True, exist_ok=True)

        uid = str(uuid.uuid4())
        original_filename = secure_filename(uploaded_file.filename)
        temp_path = os.path.join(agreements_dir, f"temp_{uid}_{original_filename}")
        uploaded_file.save(temp_path)

        # Hash original file
        doc_hash = sha256_hash_file(temp_path)

        # Encrypt file
        enc_filename = f"enc_{uid}.bin"
        enc_path = os.path.join(agreements_dir, enc_filename)
        aes_key_b64, nonce_b64 = encrypt_file_aes256gcm(temp_path, enc_path)
        os.remove(temp_path)

        # Wrap AES key with landlord's RSA public key
        import base64
        aes_key_bytes = base64.b64decode(aes_key_b64)
        aes_key_encrypted = encrypt_rsa_oaep(current_user.public_key_pem, aes_key_bytes)

        # Verification code
        vcode = generate_verification_code()

        try:
            rent_amount = float(rent_amount)
        except (ValueError, TypeError):
            rent_amount = 0

        from datetime import date
        try:
            from datetime import datetime
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
        except ValueError:
            start_dt = end_dt = None

        agreement = RentalAgreement(
            agreement_uid=uid,
            landlord_id=current_user.id,
            tenant_id=int(tenant_id),
            asset_id=int(asset_id) if asset_id else None,
            rental_category=rental_category,
            encrypted_file_path=enc_path,
            original_filename=original_filename,
            document_hash_sha256=doc_hash,
            aes_key_encrypted=aes_key_encrypted,
            aes_nonce=nonce_b64,
            start_date=start_dt,
            end_date=end_dt,
            rent_amount=rent_amount,
            currency=currency,
            terms=terms,
            verification_code=vcode,
            status='pending_tenant',
        )
        db.session.add(agreement)
        db.session.commit()

        flash('Agreement created and encrypted successfully! The tenant can now view and sign it.', 'success')
        return redirect(url_for('agreement.view_agreement', agreement_id=agreement.id))

    return render_template('agreements/create.html',
                           categories=categories, assets=assets,
                           tenants=tenants, form_data={})


@agreement_bp.route('/<int:agreement_id>')
@login_required
def view_agreement(agreement_id):
    agreement = RentalAgreement.query.get_or_404(agreement_id)
    if current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        flash('Access denied.', 'error')
        return redirect(url_for('agreement.list_agreements'))

    landlord_cert = Certificate.query.filter_by(
        user_id=agreement.landlord_id, is_revoked=False).first()
    tenant_cert = Certificate.query.filter_by(
        user_id=agreement.tenant_id, is_revoked=False).first() if agreement.tenant_id else None

    return render_template('agreements/view.html',
                           agreement=agreement,
                           landlord_cert=landlord_cert,
                           tenant_cert=tenant_cert)


@agreement_bp.route('/<int:agreement_id>/sign', methods=['POST'])
@login_required
def sign_agreement(agreement_id):
    agreement = RentalAgreement.query.get_or_404(agreement_id)

    if current_user.id not in (agreement.landlord_id, agreement.tenant_id):
        flash('Access denied.', 'error')
        return redirect(url_for('agreement.list_agreements'))

    if not agreement.document_hash_sha256:
        flash('No document hash found. Cannot sign.', 'error')
        return redirect(url_for('agreement.view_agreement', agreement_id=agreement_id))

    cert = Certificate.query.filter_by(user_id=current_user.id, is_revoked=False).first()
    if not cert or not cert.is_valid:
        flash('Your certificate is not valid. Cannot sign.', 'error')
        return redirect(url_for('agreement.view_agreement', agreement_id=agreement_id))

    from datetime import datetime
    signature = rsa_sign(current_user.private_key_pem, agreement.document_hash_sha256)

    if current_user.id == agreement.landlord_id:
        agreement.landlord_signature = signature
        agreement.landlord_signed_at = datetime.utcnow()
        agreement.landlord_cert_serial = cert.serial_number
        agreement.status = 'landlord_signed' if not agreement.tenant_signature else 'fully_signed'
    else:
        # Verify landlord signature first
        landlord = User.query.get(agreement.landlord_id)
        if agreement.landlord_signature and not rsa_verify(
                landlord.public_key_pem, agreement.document_hash_sha256, agreement.landlord_signature):
            flash('Landlord signature verification failed! Document may be tampered.', 'error')
            return redirect(url_for('agreement.view_agreement', agreement_id=agreement_id))

        agreement.tenant_signature = signature
        agreement.tenant_signed_at = datetime.utcnow()
        agreement.tenant_cert_serial = cert.serial_number
        agreement.status = 'fully_signed' if agreement.landlord_signature else 'pending_tenant'

    db.session.commit()
    flash('Agreement signed successfully with your digital certificate!', 'success')
    return redirect(url_for('agreement.view_agreement', agreement_id=agreement_id))
