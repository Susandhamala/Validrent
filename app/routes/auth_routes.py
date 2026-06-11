from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.certificate import Certificate
from app.services.crypto_service import generate_rsa_keypair
from app.services.certificate_service import issue_certificate

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'tenant')
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email or '@' not in email:
            errors.append('Valid email is required.')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        if role not in ('landlord', 'tenant'):
            errors.append('Invalid role selected.')
        if User.query.filter_by(email=email).first():
            errors.append('Email is already registered.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('auth/register.html',
                                   form_data=request.form)

        # Generate RSA key pair
        private_pem, public_pem = generate_rsa_keypair()

        user = User(
            full_name=full_name,
            email=email,
            phone=phone,
            role=role,
            private_key_pem=private_pem,
            public_key_pem=public_pem,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # get user.id

        # Issue X.509 certificate
        cert_data = issue_certificate(public_pem, full_name, email)
        cert = Certificate(
            user_id=user.id,
            serial_number=cert_data['serial_number'],
            certificate_pem=cert_data['certificate_pem'],
            issued_at=cert_data['issued_at'],
            expires_at=cert_data['expires_at'],
            subject_cn=cert_data['subject_cn'],
        )
        db.session.add(cert)
        db.session.commit()

        flash('Account created successfully! Your digital certificate has been issued. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form_data={})


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Account is deactivated. Contact support.', 'error')
            return render_template('auth/login.html')

        login_user(user, remember=remember)
        next_page = request.args.get('next')
        return redirect(next_page or url_for('dashboard.index'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
