from flask import Blueprint, render_template
from app.models.agreement import RentalAgreement
from app.models.certificate import Certificate
from app.models.user import User
from app.services.crypto_service import rsa_verify

verification_bp = Blueprint('verification', __name__, url_prefix='/verify')


@verification_bp.route('/crypto')
def crypto_info():
    return render_template('crypto/crypto_page.html')


@verification_bp.route('/code/<string:code>')
def verify_by_code(code):
    agreement = RentalAgreement.query.filter_by(verification_code=code).first()
    if not agreement:
        return render_template('pdf/verification_result.html',
                               result='INVALID',
                               reason='Verification code not found.',
                               agreement=None)

    landlord = User.query.get(agreement.landlord_id)
    tenant = User.query.get(agreement.tenant_id) if agreement.tenant_id else None

    checks = {}

    # Document hash check (we can't re-hash encrypted file without decryption key, so just report stored hash)
    checks['document_hash'] = agreement.document_hash_sha256 or 'N/A'

    # Signature checks
    landlord_sig_valid = False
    tenant_sig_valid = False

    if agreement.landlord_signature and landlord:
        landlord_sig_valid = rsa_verify(
            landlord.public_key_pem,
            agreement.document_hash_sha256,
            agreement.landlord_signature
        )

    if agreement.tenant_signature and tenant:
        tenant_sig_valid = rsa_verify(
            tenant.public_key_pem,
            agreement.document_hash_sha256,
            agreement.tenant_signature
        )

    checks['landlord_signed'] = landlord_sig_valid
    checks['tenant_signed'] = tenant_sig_valid

    # Certificate checks
    landlord_cert = Certificate.query.filter_by(
        serial_number=agreement.landlord_cert_serial).first() if agreement.landlord_cert_serial else None
    tenant_cert = Certificate.query.filter_by(
        serial_number=agreement.tenant_cert_serial).first() if agreement.tenant_cert_serial else None

    checks['landlord_cert_valid'] = landlord_cert.is_valid if landlord_cert else False
    checks['landlord_cert_revoked'] = landlord_cert.is_revoked if landlord_cert else False
    checks['tenant_cert_valid'] = tenant_cert.is_valid if tenant_cert else False
    checks['tenant_cert_revoked'] = tenant_cert.is_revoked if tenant_cert else False

    # Final result
    all_valid = (
        landlord_sig_valid and
        tenant_sig_valid and
        checks['landlord_cert_valid'] and
        checks['tenant_cert_valid'] and
        not checks['landlord_cert_revoked'] and
        not checks['tenant_cert_revoked']
    )

    result = 'VALID' if all_valid else 'INVALID'

    # Public-safe info only
    public_info = {
        'agreement_id': str(agreement.agreement_uid)[:18] + '...',
        'rental_category': agreement.rental_category,
        'status': agreement.status,
        'start_date': str(agreement.start_date),
        'end_date': str(agreement.end_date),
        'document_hash_short': (agreement.document_hash_sha256 or '')[:16] + '...',
    }

    return render_template('pdf/verification_result.html',
                           result=result,
                           checks=checks,
                           public_info=public_info,
                           agreement=agreement,
                           code=code)
