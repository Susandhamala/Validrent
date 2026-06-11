from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.asset import AssetCategory, RentalAsset

asset_bp = Blueprint('asset', __name__, url_prefix='/assets')


@asset_bp.route('/')
@login_required
def list_assets():
    if current_user.role != 'landlord':
        return redirect(url_for('asset.browse'))
    assets = RentalAsset.query.filter_by(owner_id=current_user.id).order_by(
        RentalAsset.created_at.desc()).all()
    return render_template('assets/asset_list.html', assets=assets)


@asset_bp.route('/browse')
@login_required
def browse():
    """All available assets — visible to all users, especially tenants."""
    category_id = request.args.get('category_id', type=int)
    search = request.args.get('q', '').strip()

    q = RentalAsset.query.filter_by(status='available')
    if category_id:
        q = q.filter_by(category_id=category_id)
    if search:
        q = q.filter(
            RentalAsset.asset_title.ilike(f'%{search}%') |
            RentalAsset.location.ilike(f'%{search}%') |
            RentalAsset.description.ilike(f'%{search}%')
        )

    assets = q.order_by(RentalAsset.created_at.desc()).all()
    categories = AssetCategory.query.order_by(AssetCategory.name).all()
    return render_template('assets/browse.html', assets=assets,
                           categories=categories,
                           selected_cat=category_id, search=search)


@asset_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_asset():
    if current_user.role != 'landlord':
        flash('Only landlords can create assets.', 'error')
        return redirect(url_for('dashboard.home'))

    categories = AssetCategory.query.order_by(AssetCategory.name).all()

    if request.method == 'POST':
        category_id = request.form.get('category_id')
        asset_title = request.form.get('asset_title', '').strip()
        asset_type = request.form.get('asset_type', '').strip()
        asset_identifier = request.form.get('asset_identifier', '').strip()
        description = request.form.get('description', '').strip()
        location = request.form.get('location', '').strip()
        estimated_value = request.form.get('estimated_value', 0)

        if not asset_title or not category_id:
            flash('Asset title and category are required.', 'error')
            return render_template('assets/asset_create.html', categories=categories, form_data=request.form)

        try:
            estimated_value = float(estimated_value) if estimated_value else 0
        except ValueError:
            estimated_value = 0

        asset = RentalAsset(
            owner_id=current_user.id,
            category_id=int(category_id),
            asset_title=asset_title,
            asset_type=asset_type,
            asset_identifier=asset_identifier,
            description=description,
            location=location,
            estimated_value=estimated_value,
        )
        db.session.add(asset)
        db.session.commit()
        flash(f'Asset "{asset_title}" created successfully!', 'success')
        return redirect(url_for('asset.list_assets'))

    return render_template('assets/asset_create.html', categories=categories, form_data={})


@asset_bp.route('/<int:asset_id>')
@login_required
def view_asset(asset_id):
    asset = RentalAsset.query.get_or_404(asset_id)
    # Landlords see only their own; tenants can view any available asset
    if current_user.role == 'landlord' and asset.owner_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('asset.list_assets'))
    return render_template('assets/asset_detail.html', asset=asset)
