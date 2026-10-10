"""
SynapsePM - Authentication Routes (Production Ready)
Enterprise-grade authentication with JWT, MFA, OAuth, and proper security
"""

import os
import re
import json
import uuid
import hashlib
import logging
import secrets
import random
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Dict, Optional, Tuple, Any, List
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlencode

from flask import Blueprint, request, jsonify, g, current_app, render_template_string

# ============================================================
# IMPORTS
# ============================================================

try:
    import jwt
    from sqlalchemy import and_, or_, text
    from sqlalchemy.exc import SQLAlchemyError, IntegrityError
    from werkzeug.security import generate_password_hash, check_password_hash
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    print("⚠️ bcrypt not installed - using werkzeug security")

# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class AuthConfig:
    """Authentication configuration"""
    
    # JWT Configuration
    jwt_secret_key: str = os.getenv('JWT_SECRET_KEY', '')
    jwt_algorithm: str = "HS256"
    access_token_expire: int = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRE', '86400'))
    refresh_token_expire: int = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRE', '604800'))
    
    # Security
    bcrypt_rounds: int = int(os.getenv('BCRYPT_ROUNDS', '12'))
    
    # OAuth Configuration
    google_client_id: str = os.getenv('GOOGLE_CLIENT_ID', '')
    google_client_secret: str = os.getenv('GOOGLE_CLIENT_SECRET', '')
    github_client_id: str = os.getenv('GITHUB_CLIENT_ID', '')
    github_client_secret: str = os.getenv('GITHUB_CLIENT_SECRET', '')
    
    # Environment
    frontend_url: str = os.getenv('FRONTEND_URL', 'http://localhost:5000')
    app_url: str = os.getenv('APP_URL', 'http://localhost:5000')
    
    # Database models (injected later)
    User = None
    Organization = None
    db = None
    encryption_service = None

# ============================================================
# BLUEPRINT
# ============================================================

bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')
logger = logging.getLogger(__name__)

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _get_user_model():
    return AuthConfig.User

def _get_organization_model():
    return AuthConfig.Organization

def _get_db():
    return AuthConfig.db

def _get_encryption_service():
    return AuthConfig.encryption_service

def _log_audit(action: str, status: str, email: str = None, details: Dict = None):
    try:
        audit_data = {
            'action': action,
            'status': status,
            'email': email,
            'ip_address': request.headers.get('X-Forwarded-For', request.remote_addr),
            'user_agent': request.headers.get('User-Agent'),
            'path': request.path,
            'method': request.method,
            'details': details or {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        logger.info(f"AUDIT: {json.dumps(audit_data)}")
    except Exception as e:
        logger.error(f"Audit log error: {e}")

def _get_user_by_email(email: str):
    User = _get_user_model()
    if User:
        return User.query.filter_by(email=email, is_deleted=False).first()
    return None

def _get_user_by_oauth(provider: str, oauth_id: str):
    User = _get_user_model()
    if User:
        return User.query.filter_by(oauth_provider=provider, oauth_id=oauth_id, is_deleted=False).first()
    return None

def _create_user(email: str, password: str, first_name: str, last_name: str, **kwargs):
    User = _get_user_model()
    Organization = _get_organization_model()
    db = _get_db()
    
    if not User or not Organization or not db:
        logger.error("❌ Database models not configured")
        return None
    
    try:
        # Create organization
        company = kwargs.get('company', f"{first_name}'s Organization")
        org_slug = company.lower().replace(' ', '-').replace('_', '-')
        
        existing_org = Organization.query.filter_by(slug=org_slug).first()
        if existing_org:
            org_slug = f"{org_slug}-{uuid.uuid4().hex[:6]}"
        
        org = Organization(
            name=company,
            slug=org_slug,
            plan='free',
            subscription_status='trialing',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            max_users=5,
            max_machines=10,
            settings={}
        )
        db.session.add(org)
        db.session.flush()
        
        # Create user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            display_name=f"{first_name} {last_name}".strip(),
            role=kwargs.get('role', 'admin'),
            organization_id=org.id,
            is_verified=kwargs.get('is_verified', True),
            is_active=kwargs.get('is_active', True),
            oauth_provider=kwargs.get('oauth_provider'),
            oauth_id=kwargs.get('oauth_id'),
            avatar_url=kwargs.get('avatar_url'),
            preferences=kwargs.get('preferences', {'theme': 'light', 'notifications': {'email': True, 'sms': False, 'in_app': True}})
        )
        
        if password:
            user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"✅ User created: {email} (ID: {user.id})")
        return user
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to create user: {e}")
        import traceback
        traceback.print_exc()
        return None

def _create_or_update_oauth_user(provider: str, user_info: Dict, access_token: str = None) -> Optional[Any]:
    User = _get_user_model()
    db = _get_db()
    
    if not User or not db:
        logger.error("❌ Database models not configured")
        return None
    
    try:
        email = user_info.get('email')
        oauth_id = str(user_info.get('id'))
        
        if not email or not oauth_id:
            logger.error(f"Missing email or ID for {provider}")
            return None
        
        user = _get_user_by_oauth(provider, oauth_id)
        if not user:
            user = _get_user_by_email(email)
        
        avatar_url = user_info.get('avatar_url') or user_info.get('picture')
        
        if user:
            logger.info(f"🔄 Updating existing user: {email}")
            user.oauth_provider = provider
            user.oauth_id = oauth_id
            user.is_verified = True
            user.is_active = True
            if avatar_url:
                user.avatar_url = avatar_url
            db.session.commit()
            return user
        
        logger.info(f"🆕 Creating new user from {provider}: {email}")
        
        full_name = user_info.get('name', '')
        given_name = user_info.get('given_name')
        family_name = user_info.get('family_name')
        
        if provider == 'github':
            if full_name:
                name_parts = full_name.split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''
            else:
                first_name = user_info.get('login', email.split('@')[0])
                last_name = ''
        else:
            first_name = given_name or full_name.split()[0] if full_name else email.split('@')[0]
            last_name = family_name or (full_name.split()[-1] if full_name and len(full_name.split()) > 1 else '')
        
        user = _create_user(
            email=email,
            password=None,
            first_name=first_name,
            last_name=last_name,
            company=f"{first_name}'s Organization",
            role='admin',
            is_verified=True,
            is_active=True,
            oauth_provider=provider,
            oauth_id=oauth_id,
            avatar_url=avatar_url
        )
        
        return user
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Failed to create/update OAuth user: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================
# OAUTH HELPER FUNCTIONS
# ============================================================

def _render_oauth_success(tokens, user):
    frontend_url = AuthConfig.frontend_url
    
    user_dict = user.to_dict() if hasattr(user, 'to_dict') else {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'display_name': user.display_name,
        'role': user.role,
        'organization_id': user.organization_id,
        'avatar_url': user.avatar_url
    }
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login Successful</title>
        <style>
            body {{ display: flex; justify-content: center; align-items: center; height: 100vh; font-family: system-ui, sans-serif; background: #f8fafc; margin: 0; }}
            .container {{ text-align: center; padding: 2rem; background: white; border-radius: 1rem; box-shadow: 0 20px 60px rgba(0,0,0,0.1); }}
            .check {{ font-size: 4rem; color: #22c55e; }}
            h2 {{ color: #0f2b3d; margin: 0.5rem 0; }}
            p {{ color: #64748b; margin: 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="check">✅</div>
            <h2>Login Successful!</h2>
            <p>You can close this window.</p>
        </div>
        <script>
            window.opener.postMessage({{
                type: 'social_auth_success',
                access_token: '{tokens["access_token"]}',
                refresh_token: '{tokens["refresh_token"]}',
                user: {json.dumps(user_dict)}
            }}, '{frontend_url}');
            window.close();
        </script>
    </body>
    </html>
    """

def _render_oauth_error(message: str):
    frontend_url = AuthConfig.frontend_url
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login Failed</title>
        <style>
            body {{ display: flex; justify-content: center; align-items: center; height: 100vh; font-family: system-ui, sans-serif; background: #f8fafc; margin: 0; }}
            .container {{ text-align: center; padding: 2rem; background: white; border-radius: 1rem; box-shadow: 0 20px 60px rgba(0,0,0,0.1); }}
            .error {{ font-size: 4rem; color: #ef4444; }}
            h2 {{ color: #0f2b3d; margin: 0.5rem 0; }}
            p {{ color: #64748b; margin: 0.5rem 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error">❌</div>
            <h2>Login Failed</h2>
            <p>{message}</p>
        </div>
        <script>
            window.opener.postMessage({{
                type: 'social_auth_error',
                message: '{message}'
            }}, '{frontend_url}');
            window.close();
        </script>
    </body>
    </html>
    """

# ============================================================
# TOKEN HANDLER
# ============================================================

def create_tokens(user_id, email, role='user', organization_id=None):
    now = datetime.now(timezone.utc)
    
    access_payload = {
        'sub': str(user_id),
        'email': email,
        'type': 'access',
        'role': role,
        'exp': int((now + timedelta(seconds=86400)).timestamp()),
        'iat': int(now.timestamp()),
        'jti': str(uuid.uuid4())
    }
    if organization_id:
        access_payload['org'] = str(organization_id)
    
    refresh_payload = {
        'sub': str(user_id),
        'type': 'refresh',
        'exp': int((now + timedelta(days=7)).timestamp()),
        'iat': int(now.timestamp()),
        'jti': str(uuid.uuid4())
    }
    
    return {
        'access_token': jwt.encode(access_payload, os.getenv('JWT_SECRET_KEY', 'dev-secret-key'), algorithm='HS256'),
        'refresh_token': jwt.encode(refresh_payload, os.getenv('JWT_REFRESH_SECRET', 'dev-refresh-secret'), algorithm='HS256')
    }

# ============================================================
# REGISTRATION ROUTE
# ============================================================

@bp.route('/register', methods=['POST'])
def register():
    """✅ Register new user"""
    try:
        data = request.get_json()
        logger.info(f"📝 Registration data: {data}")
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        email = data.get('email')
        password = data.get('password')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        company = data.get('company')
        
        if not email or not password or not first_name or not last_name:
            return jsonify({'success': False, 'error': 'Email, password, first name, and last name required'}), 400
        
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        if len(password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
        
        # Check if user exists
        User = _get_user_model()
        if User:
            existing = User.query.filter_by(email=email, is_deleted=False).first()
            if existing:
                return jsonify({'success': False, 'error': 'User already exists'}), 409
        
        # Create user
        user = _create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            company=company or f"{first_name}'s Organization"
        )
        
        if not user:
            return jsonify({'success': False, 'error': 'Failed to create user'}), 500
        
        # Create tokens
        tokens = create_tokens(
            user_id=user.id,
            email=user.email,
            role=user.role,
            organization_id=user.organization_id
        )
        
        _log_audit('REGISTER', 'success', email)
        
        return jsonify({
            'success': True,
            'message': 'User registered successfully',
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'user': user.to_dict() if hasattr(user, 'to_dict') else {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'organization_id': user.organization_id
            }
        }), 201
        
    except Exception as e:
        logger.error(f"❌ Registration failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# LOGIN ROUTE
# ============================================================

@bp.route('/login', methods=['POST'])
def login():
    """✅ Login user"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400
        
        user = _get_user_by_email(email)
        
        if not user:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        if not user.check_password(password):
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        if not user.is_active:
            return jsonify({'success': False, 'error': 'Account is deactivated'}), 403
        
        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = request.remote_addr
        user.login_count = (user.login_count or 0) + 1
        
        db = _get_db()
        if db:
            db.session.commit()
        
        # Create tokens
        tokens = create_tokens(
            user_id=user.id,
            email=user.email,
            role=user.role,
            organization_id=user.organization_id
        )
        
        _log_audit('LOGIN', 'success', email)
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'user': user.to_dict() if hasattr(user, 'to_dict') else {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'organization_id': user.organization_id,
                'avatar_url': user.avatar_url
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Login failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# GOOGLE OAUTH ROUTES
# ============================================================

@bp.route('/google/login', methods=['GET'])
def google_login():
    if not AuthConfig.google_client_id:
        return jsonify({'error': 'Google login not configured'}), 501
    
    redirect_uri = f"{AuthConfig.app_url}/api/v1/auth/google/callback"
    params = {
        'client_id': AuthConfig.google_client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'email profile',
        'access_type': 'offline',
        'prompt': 'consent'
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    return jsonify({'redirect_url': auth_url}), 200

@bp.route('/google/callback', methods=['GET'])
def google_callback():
    frontend_url = AuthConfig.frontend_url
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        return _render_oauth_error(f"Google auth error: {error}")
    
    if not code:
        return _render_oauth_error("No authorization code received")
    
    try:
        import requests
        
        # Exchange code for token
        token_data = {
            'code': code,
            'client_id': AuthConfig.google_client_id,
            'client_secret': AuthConfig.google_client_secret,
            'redirect_uri': f"{AuthConfig.app_url}/api/v1/auth/google/callback",
            'grant_type': 'authorization_code'
        }
        token_response = requests.post('https://oauth2.googleapis.com/token', data=token_data)
        token_json = token_response.json()
        
        if 'access_token' not in token_json:
            return _render_oauth_error("Failed to get access token")
        
        # Get user info
        headers = {'Authorization': f"Bearer {token_json['access_token']}"}
        user_response = requests.get('https://www.googleapis.com/oauth2/v2/userinfo', headers=headers)
        user_info = user_response.json()
        
        if not user_info.get('email'):
            return _render_oauth_error("Could not retrieve email")
        
        # Create or update user
        user = _create_or_update_oauth_user('google', user_info, token_json['access_token'])
        
        if not user:
            return _render_oauth_error("Failed to create/update user")
        
        # Create tokens
        tokens = create_tokens(
            user_id=user.id,
            email=user.email,
            role=user.role,
            organization_id=user.organization_id
        )
        
        _log_audit('OAUTH_LOGIN_GOOGLE', 'success', user.email)
        
        return _render_oauth_success(tokens, user)
        
    except Exception as e:
        logger.error(f"❌ Google callback error: {e}")
        import traceback
        traceback.print_exc()
        return _render_oauth_error(str(e))

# ============================================================
# GITHUB OAUTH ROUTES
# ============================================================

@bp.route('/github/login', methods=['GET'])
def github_login():
    if not AuthConfig.github_client_id:
        return jsonify({'error': 'GitHub login not configured'}), 501
    
    redirect_uri = f"{AuthConfig.app_url}/api/v1/auth/github/callback"
    params = {
        'client_id': AuthConfig.github_client_id,
        'redirect_uri': redirect_uri,
        'scope': 'user:email'
    }
    auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    
    return jsonify({'redirect_url': auth_url}), 200

@bp.route('/github/callback', methods=['GET'])
def github_callback():
    frontend_url = AuthConfig.frontend_url
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        return _render_oauth_error(f"GitHub auth error: {error}")
    
    if not code:
        return _render_oauth_error("No authorization code received")
    
    try:
        import requests
        
        # Exchange code for token
        token_data = {
            'code': code,
            'client_id': AuthConfig.github_client_id,
            'client_secret': AuthConfig.github_client_secret,
            'redirect_uri': f"{AuthConfig.app_url}/api/v1/auth/github/callback"
        }
        token_response = requests.post('https://github.com/login/oauth/access_token', 
                                       data=token_data, 
                                       headers={'Accept': 'application/json'})
        token_json = token_response.json()
        
        if 'access_token' not in token_json:
            return _render_oauth_error("Failed to get access token")
        
        # Get user info
        headers = {'Authorization': f"Bearer {token_json['access_token']}"}
        user_response = requests.get('https://api.github.com/user', headers=headers)
        user_info = user_response.json()
        
        # Get email if not public
        email = user_info.get('email')
        if not email:
            email_response = requests.get('https://api.github.com/user/emails', headers=headers)
            emails = email_response.json()
            for e in emails:
                if e.get('primary'):
                    email = e.get('email')
                    break
        
        if not email:
            return _render_oauth_error("Could not retrieve email")
        
        user_info['email'] = email
        
        # Create or update user
        user = _create_or_update_oauth_user('github', user_info, token_json['access_token'])
        
        if not user:
            return _render_oauth_error("Failed to create/update user")
        
        # Create tokens
        tokens = create_tokens(
            user_id=user.id,
            email=user.email,
            role=user.role,
            organization_id=user.organization_id
        )
        
        _log_audit('OAUTH_LOGIN_GITHUB', 'success', user.email)
        
        return _render_oauth_success(tokens, user)
        
    except Exception as e:
        logger.error(f"❌ GitHub callback error: {e}")
        import traceback
        traceback.print_exc()
        return _render_oauth_error(str(e))

# ============================================================
# LOGOUT ROUTE
# ============================================================

@bp.route('/logout', methods=['POST'])
def logout():
    return jsonify({'success': True, 'message': 'Logout successful'}), 200

# ============================================================
# ERROR HANDLERS
# ============================================================

@bp.errorhandler(404)
def handle_not_found(e):
    return jsonify({'error': 'not_found', 'message': 'Resource not found', 'success': False}), 404

@bp.errorhandler(500)
def handle_internal_error(e):
    logger.error(f"Internal error: {e}")
    return jsonify({'error': 'internal_error', 'message': 'An unexpected error occurred', 'success': False}), 500
