"""
In-app encrypted chat — REST endpoints used via fetch() for real-time feel.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.chat import ChatThread, ChatMessage
from app.models.request import AgreementRequest
from app.services.chat_service import encrypt_message, decrypt_thread_messages

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')


def _assert_access(thread: ChatThread):
    req_obj = thread.request
    if current_user.id not in (req_obj.tenant_id, req_obj.landlord_id):
        abort(403)


@chat_bp.route('/thread/<int:thread_id>/messages')
@login_required
def get_messages(thread_id):
    """Return all decrypted messages as JSON (polled every 3 s)."""
    thread = ChatThread.query.get_or_404(thread_id)
    _assert_access(thread)
    since_id = request.args.get('since', 0, type=int)
    messages = [m for m in decrypt_thread_messages(thread) if m['id'] > since_id]
    return jsonify({'messages': [
        {
            'id': m['id'],
            'sender_name': m['sender_name'],
            'sender_role': m['sender_role'],
            'text': m['text'],
            'sent_at': m['sent_at'].strftime('%d %b %H:%M'),
            'is_system': m['is_system'],
            'is_mine': m['sender_id'] == current_user.id,
        }
        for m in messages
    ]})


@chat_bp.route('/thread/<int:thread_id>/send', methods=['POST'])
@login_required
def send_message(thread_id):
    """Encrypt and store a new chat message."""
    thread = ChatThread.query.get_or_404(thread_id)
    _assert_access(thread)

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'success': False, 'error': 'Empty message.'}), 400
    if len(text) > 4000:
        return jsonify({'success': False, 'error': 'Message too long (max 4000 chars).'}), 400

    ct, nonce, msg_hash = encrypt_message(thread.encrypted_thread_key, text)
    msg = ChatMessage(
        thread_id=thread.id,
        sender_id=current_user.id,
        ciphertext_b64=ct,
        nonce_b64=nonce,
        message_hash=msg_hash,
        is_system=False,
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': {
            'id': msg.id,
            'sender_name': current_user.full_name,
            'sender_role': current_user.role,
            'text': text,
            'sent_at': msg.sent_at.strftime('%d %b %H:%M'),
            'is_system': False,
            'is_mine': True,
        }
    })
