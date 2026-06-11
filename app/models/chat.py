import uuid
from datetime import datetime
from app.extensions import db


class ChatThread(db.Model):
    """A chat thread linked to an agreement request."""
    __tablename__ = 'encrypted_chat_threads'

    id = db.Column(db.Integer, primary_key=True)
    thread_uid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    request_id = db.Column(db.Integer, db.ForeignKey('agreement_requests.id'), nullable=False)
    # AES-256 thread key encrypted with a server-side master key (base64)
    encrypted_thread_key = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    request = db.relationship('AgreementRequest', back_populates='chat_thread')
    messages = db.relationship('ChatMessage', back_populates='thread',
                               order_by='ChatMessage.sent_at', lazy='dynamic')


class ChatMessage(db.Model):
    """AES-256-GCM encrypted chat message."""
    __tablename__ = 'encrypted_chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('encrypted_chat_threads.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Encrypted payload (base64-encoded ciphertext)
    ciphertext_b64 = db.Column(db.Text, nullable=False)
    # Nonce for AES-GCM (base64)
    nonce_b64 = db.Column(db.String(32), nullable=False)
    # SHA-256 of original plaintext for integrity
    message_hash = db.Column(db.String(64))

    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_system = db.Column(db.Boolean, default=False)   # system/status messages

    thread = db.relationship('ChatThread', back_populates='messages')
    sender = db.relationship('User')
