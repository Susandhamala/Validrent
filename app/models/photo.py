from datetime import datetime
from app.extensions import db


class IdentityPhoto(db.Model):
    __tablename__ = 'identity_photos'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agreement_id = db.Column(db.Integer, db.ForeignKey('rental_agreements.id'), nullable=False)
    photo_encrypted_path = db.Column(db.String(500))
    photo_hash_sha256 = db.Column(db.String(64))
    consent_given = db.Column(db.Boolean, default=False)
    captured_at = db.Column(db.DateTime, default=datetime.utcnow)
    purpose = db.Column(db.String(100), default='agreement_evidence')

    user = db.relationship('User', back_populates='photos')
    agreement = db.relationship('RentalAgreement', back_populates='photos')
