from flask import Flask, session, redirect, request as flask_request, url_for
from pathlib import Path
from app.config import Config
from app.extensions import db, login_manager, csrf
from app.i18n import get_translations, SUPPORTED


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # ── Blueprints ──────────────────────────────────────────────────────────
    from app.routes.auth_routes import auth_bp
    from app.routes.dashboard_routes import dashboard_bp
    from app.routes.asset_routes import asset_bp
    from app.routes.agreement_routes import agreement_bp
    from app.routes.photo_routes import photo_bp
    from app.routes.pdf_routes import pdf_bp
    from app.routes.verification_routes import verification_bp
    from app.routes.request_routes import req_bp
    from app.routes.chat_routes import chat_bp
    from app.routes.admin_routes import admin_bp

    for bp in (auth_bp, dashboard_bp, asset_bp, agreement_bp,
               photo_bp, pdf_bp, verification_bp, req_bp, chat_bp, admin_bp):
        app.register_blueprint(bp)

    # ── User loader ─────────────────────────────────────────────────────────
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Template filter: pending request badge count ─────────────────────
    from app.models.request import AgreementRequest

    @app.template_filter('pending_requests_count')
    def pending_requests_count(landlord_id):
        return AgreementRequest.query.filter_by(
            landlord_id=landlord_id, status='pending').count()

    # ── Language switching ───────────────────────────────────────────────────
    @app.route('/set-lang/<lang>')
    def set_lang(lang):
        if lang in SUPPORTED:
            session['lang'] = lang
        referrer = flask_request.referrer or '/'
        return redirect(referrer)

    # ── Translation context processor ────────────────────────────────────────
    @app.context_processor
    def inject_lang():
        lang = session.get('lang', 'en')
        return dict(tr=get_translations(lang), lang=lang, supported_langs=SUPPORTED)

    # ── DB init + seed ──────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        _seed_categories()

    return app


def _seed_categories():
    from app.models.asset import AssetCategory

    categories = [
        {'name': 'House',             'description': 'Residential house rental',          'icon': 'home',      'risk_level': 'medium'},
        {'name': 'Room',              'description': 'Single room rental',                'icon': 'door-open', 'risk_level': 'low'},
        {'name': 'Apartment',         'description': 'Apartment or flat rental',          'icon': 'building',  'risk_level': 'medium'},
        {'name': 'Land',              'description': 'Land lease agreements',             'icon': 'map',       'risk_level': 'high'},
        {'name': 'Automobile',        'description': 'Car, truck, or vehicle rental',     'icon': 'car',       'risk_level': 'high'},
        {'name': 'Bike/Scooter',      'description': 'Motorcycle or scooter rental',      'icon': 'bicycle',   'risk_level': 'medium'},
        {'name': 'Machinery',         'description': 'Heavy machinery or equipment',      'icon': 'gear',      'risk_level': 'high'},
        {'name': 'Office/Commercial', 'description': 'Office or commercial space rental', 'icon': 'briefcase', 'risk_level': 'medium'},
        {'name': 'Storage/Warehouse', 'description': 'Storage unit or warehouse rental', 'icon': 'box',       'risk_level': 'low'},
        {'name': 'Other',             'description': 'Other sensitive rental assets',     'icon': 'tag',       'risk_level': 'medium'},
    ]
    for cat_data in categories:
        if not AssetCategory.query.filter_by(name=cat_data['name']).first():
            db.session.add(AssetCategory(**cat_data))
    db.session.commit()
