from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models.agreement import RentalAgreement
from app.models.asset import RentalAsset
from app.models.certificate import Certificate
from app.models.request import AgreementRequest

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    return redirect(url_for('dashboard.home'))


@dashboard_bp.route('/dashboard')
@login_required
def home():
    cert = Certificate.query.filter_by(user_id=current_user.id, is_revoked=False).first()

    if current_user.role == 'landlord':
        agreements = RentalAgreement.query.filter_by(landlord_id=current_user.id).order_by(
            RentalAgreement.created_at.desc()).limit(5).all()
        total_agreements = RentalAgreement.query.filter_by(landlord_id=current_user.id).count()
        assets = RentalAsset.query.filter_by(owner_id=current_user.id).limit(5).all()
        total_assets = RentalAsset.query.filter_by(owner_id=current_user.id).count()
        # Pending requests from tenants
        pending_requests = AgreementRequest.query.filter_by(
            landlord_id=current_user.id, status='pending').order_by(
            AgreementRequest.created_at.desc()).all()
        my_requests = AgreementRequest.query.filter_by(
            landlord_id=current_user.id).order_by(
            AgreementRequest.created_at.desc()).limit(5).all()
    else:
        agreements = RentalAgreement.query.filter_by(tenant_id=current_user.id).order_by(
            RentalAgreement.created_at.desc()).limit(5).all()
        total_agreements = RentalAgreement.query.filter_by(tenant_id=current_user.id).count()
        assets = []
        total_assets = 0
        pending_requests = []
        my_requests = AgreementRequest.query.filter_by(
            tenant_id=current_user.id).order_by(
            AgreementRequest.created_at.desc()).limit(5).all()

    pending = sum(1 for a in agreements if a.status in ('draft', 'pending_tenant', 'landlord_signed', 'pending_signatures'))
    verified = sum(1 for a in agreements if a.status in ('fully_signed', 'verified'))

    return render_template('dashboard/dashboard.html',
                           cert=cert,
                           agreements=agreements,
                           assets=assets,
                           total_agreements=total_agreements,
                           total_assets=total_assets,
                           pending=pending,
                           verified=verified,
                           pending_requests=pending_requests,
                           my_requests=my_requests)
