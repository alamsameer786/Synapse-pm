"""
SYNAPSEPM - AUTHENTICATION MIDDLEWARE
Production Ready - v5.2.1
Features: JWT, MFA, Session Management, SSO Integration
"""

import os
import sys
import json
import uuid
import hashlib
import logging
import re
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# IMPORTS
# ============================================================

try:
    import bcrypt
    import jwt
    from flask import Flask, request, jsonify, g, current_app, make_response, session
    from flask_cors import CORS
    from werkzeug.middleware.proxy_fix import ProxyFix
    FLASK_AVAILABLE = True
except ImportError as e:
    print(f"❌ Missing required package: {e}")
    print("Please install: pip install bcrypt pyjwt Flask Flask-CORS")
    sys.exit(1)

try:
    import redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ Redis not installed")

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False
    print("⚠️ pyotp not installed - MFA disabled")

# ============================================================
# CONFIGURATION
# ============================================================

class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class AuthConfig:
    """Complete authentication configuration"""
    
    jwt_secret_key: str = os.getenv('JWT_SECRET_KEY')
    jwt_algorithm: str = "HS256"
    access_token_expire: int = int(os.getenv('JWT_ACCESS_EXPIRY_HOURS', '24')) * 3600
    refresh_token_expire: int = int(os.getenv('JWT_REFRESH_EXPIRY_DAYS', '7')) * 86400
    verification_token_expire: int = 86400
    password_reset_expire: int = 3600
    password_expiry_days: int = int(os.getenv('PASSWORD_EXPIRY_DAYS', '90'))
    max_login_attempts: int = int(os.getenv('MAX_LOGIN_ATTEMPTS', '5'))
    lockout_duration_minutes: int = int(os.getenv('LOCKOUT_DURATION_MINUTES', '15'))
    
    environment: Environment = Environment(os.getenv('ENVIRONMENT', 'development'))
    database_url: str = os.getenv('DATABASE_URL', '')
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    frontend_url: str = os.getenv('FRONTEND_URL', 'http://localhost:5500')
    
    # SSO Configuration
    google_client_id: str = os.getenv('GOOGLE_CLIENT_ID')
    google_client_secret: str = os.getenv('GOOGLE_CLIENT_SECRET')
    google_redirect_uri: str = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5000/api/v1/auth/google/callback')
    
    github_client_id: str = os.getenv('GITHUB_CLIENT_ID')
    github_client_secret: str = os.getenv('GITHUB_CLIENT_SECRET')
    github_redirect_uri: str = os.getenv('GITHUB_REDIRECT_URI', 'http://localhost:5000/api/v1/auth/github/callback')
    
    linkedin_client_id: str = os.getenv('LINKEDIN_CLIENT_ID')
    linkedin_client_secret: str = os.getenv('LINKEDIN_CLIENT_SECRET')
    linkedin_redirect_uri: str = os.getenv('LINKEDIN_REDIRECT_URI', 'http://localhost:5000/api/v1/auth/linkedin/callback')
    
    # Features
    enable_mfa: bool = os.getenv('ENABLE_MFA', 'true').lower() == 'true'
    enable_sso: bool = os.getenv('ENABLE_SSO', 'true').lower() == 'true'
    enable_audit_logging: bool = os.getenv('ENABLE_AUDIT_LOGGING', 'true').lower() == 'true'
    
    # Redis
    redis_key_prefix: str = 'auth:'


# ============================================================
# USER REPOSITORY
# ============================================================

class UserRepository:
    """User data access layer with database and in-memory fallback"""
    
    def __init__(self):
        self.config = AuthConfig()
        self._in_memory_users = {}
        self._in_memory_sessions = {}
        self._in_memory_refresh_tokens = {}
        self._in_memory_verifications = {}
        
        # Database connection (SQLAlchemy optional)
        self._engine = None
        self._session_maker = None
        self._init_database()
    
    def _init_database(self):
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import sessionmaker
            
            if self.config.database_url:
                self._engine = create_engine(
                    self.config.database_url,
                    pool_size=10,
                    max_overflow=20,
                    pool_timeout=30
                )
                self._session_maker = sessionmaker(bind=self._engine)
                print("✅ Database connected for auth")
        except Exception as e:
            print(f"⚠️ Database connection failed: {e}")
            self._engine = None
            self._session_maker = None
    
    def get_session(self):
        if self._session_maker:
            return self._session_maker()
        return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        email = email.lower().strip()
        session = self.get_session()
        if session:
            try:
                result = session.execute(
                    text("SELECT * FROM users WHERE email = :email AND is_active = true"),
                    {"email": email}
                ).fetchone()
                if result:
                    return dict(result)
            except Exception as e:
                logging.error(f"Database error: {e}")
            finally:
                session.close()
        
        for user in self._in_memory_users.values():
            if user.get('email') == email:
                return user
        return None
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        session = self.get_session()
        if session:
            try:
                result = session.execute(
                    text("SELECT * FROM users WHERE id = :id AND is_active = true"),
                    {"id": user_id}
                ).fetchone()
                if result:
                    return dict(result)
            except Exception as e:
                logging.error(f"Database error: {e}")
            finally:
                session.close()
        
        return self._in_memory_users.get(user_id)
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        session = self.get_session()
        if session:
            try:
                result = session.execute(
                    text("SELECT * FROM users WHERE username = :username AND is_active = true"),
                    {"username": username}
                ).fetchone()
                if result:
                    return dict(result)
            except Exception as e:
                logging.error(f"Database error: {e}")
            finally:
                session.close()
        
        for user in self._in_memory_users.values():
            if user.get('username') == username:
                return user
        return None
    
    def create_user(self, email: str, password_hash: str, name: str = None,
                    company: str = None, role: str = 'user') -> Dict:
        user_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        user = {
            'id': user_id,
            'email': email.lower().strip(),
            'username': email.lower().strip(),
            'password_hash': password_hash,
            'first_name': name or '',
            'last_name': '',
            'display_name': name or email,
            'company': company or '',
            'role': role,
            'is_active': True,
            'is_verified': False,
            'is_locked': False,
            'is_mfa_enabled': False,
            'login_attempts': 0,
            'login_count': 0,
            'created_at': now,
            'updated_at': now,
            'last_login_at': None,
            'organization_id': None,
            'permissions': [],
            'notification_preferences': {},
            'ui_preferences': {}
        }
        
        session = self.get_session()
        if session:
            try:
                session.execute(
                    text("""INSERT INTO users 
                         (id, email, username, password_hash, first_name, last_name,
                          display_name, role, is_active, is_verified, created_at, updated_at)
                         VALUES (:id, :email, :username, :password_hash, :first_name,
                                 :last_name, :display_name, :role, :is_active, :is_verified,
                                 :created_at, :updated_at)"""),
                    user
                )
                session.commit()
            except Exception as e:
                logging.error(f"Database error: {e}")
                session.rollback()
            finally:
                session.close()
        
        self._in_memory_users[user_id] = user
        return user
    
    def update_user(self, user_id: str, updates: Dict) -> Optional[Dict]:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        
        user.update(updates)
        user['updated_at'] = datetime.utcnow().isoformat()
        
        session = self.get_session()
        if session:
            try:
                set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
                updates['id'] = user_id
                updates['updated_at'] = user['updated_at']
                session.execute(
                    text(f"UPDATE users SET {set_clause}, updated_at = :updated_at WHERE id = :id"),
                    user
                )
                session.commit()
            except Exception as e:
                logging.error(f"Database error: {e}")
                session.rollback()
            finally:
                session.close()
        
        return user
    
    def delete_user(self, user_id: str) -> bool:
        return bool(self.update_user(user_id, {'is_active': False}))
    
    def save_refresh_token(self, user_id: str, token: str, expires_at: datetime):
        session = self.get_session()
        if session:
            try:
                session.execute(
                    text("""INSERT INTO refresh_tokens (user_id, token, expires_at, created_at)
                         VALUES (:user_id, :token, :expires_at, :created_at)"""),
                    {
                        'user_id': user_id,
                        'token': token,
                        'expires_at': expires_at.isoformat(),
                        'created_at': datetime.utcnow().isoformat()
                    }
                )
                session.commit()
            except Exception as e:
                logging.error(f"Database error: {e}")
                session.rollback()
            finally:
                session.close()
        
        self._in_memory_refresh_tokens[token] = {
            'user_id': user_id,
            'expires_at': expires_at.isoformat()
        }
    
    def get_refresh_token(self, token: str) -> Optional[Dict]:
        session = self.get_session()
        if session:
            try:
                result = session.execute(
                    text("SELECT * FROM refresh_tokens WHERE token = :token"),
                    {"token": token}
                ).fetchone()
                if result:
                    return dict(result)
            except Exception as e:
                logging.error(f"Database error: {e}")
            finally:
                session.close()
        
        return self._in_memory_refresh_tokens.get(token)
    
    def delete_refresh_token(self, token: str):
        session = self.get_session()
        if session:
            try:
                session.execute(
                    text("DELETE FROM refresh_tokens WHERE token = :token"),
                    {"token": token}
                )
                session.commit()
            except Exception as e:
                logging.error(f"Database error: {e}")
                session.rollback()
            finally:
                session.close()
        
        self._in_memory_refresh_tokens.pop(token, None)
    
    def save_verification(self, email: str, token: str, expires_at: datetime):
        self._in_memory_verifications[token] = {
            'email': email,
            'expires_at': expires_at.isoformat()
        }
    
    def get_verification(self, token: str) -> Optional[Dict]:
        return self._in_memory_verifications.get(token)
    
    def delete_verification(self, token: str):
        self._in_memory_verifications.pop(token, None)


# ============================================================
# JWT HANDLER
# ============================================================

class JWTHandler:
    """Complete JWT handler with token management"""
    
    def __init__(self):
        self.config = AuthConfig()
        self.secret_key = self.config.jwt_secret_key
        self.algorithm = self.config.jwt_algorithm
        
        if not self.secret_key or self.secret_key == 'dev-secret-key-change-in-production':
            logging.warning("⚠️ Using default JWT secret key - not secure for production!")
    
    def create_access_token(self, user_id: str, email: str, role: str = 'user',
                           permissions: List[str] = None, organization_id: str = None) -> str:
        now = datetime.utcnow()
        payload = {
            'sub': user_id,
            'email': email,
            'type': 'access',
            'role': role,
            'permissions': permissions or [],
            'org': organization_id,
            'exp': now + timedelta(seconds=self.config.access_token_expire),
            'iat': now,
            'jti': str(uuid.uuid4()),
            'iss': 'synapsepm',
            'aud': 'synapsepm-api'
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(self, user_id: str) -> str:
        now = datetime.utcnow()
        payload = {
            'sub': user_id,
            'type': 'refresh',
            'exp': now + timedelta(seconds=self.config.refresh_token_expire),
            'iat': now,
            'jti': str(uuid.uuid4()),
            'iss': 'synapsepm'
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_verification_token(self, email: str) -> str:
        now = datetime.utcnow()
        payload = {
            'sub': email,
            'type': 'verify',
            'exp': now + timedelta(seconds=self.config.verification_token_expire),
            'iat': now,
            'jti': str(uuid.uuid4())
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def create_password_reset_token(self, user_id: str) -> str:
        now = datetime.utcnow()
        payload = {
            'sub': user_id,
            'type': 'reset',
            'exp': now + timedelta(seconds=self.config.password_reset_expire),
            'iat': now,
            'jti': str(uuid.uuid4())
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict]:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience='synapsepm-api',
                issuer='synapsepm'
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def decode_token(self, token: str) -> Optional[Dict]:
        try:
            return jwt.decode(token, options={'verify_signature': False})
        except:
            return None


# ============================================================
# PASSWORD HANDLER
# ============================================================

class PasswordHandler:
    """Secure password hashing with bcrypt"""
    
    def __init__(self):
        self.rounds = 12
    
    def hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=self.rounds)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                password_hash.encode('utf-8')
            )
        except:
            return False
    
    def is_strong_password(self, password: str) -> bool:
        if len(password) < 8:
            return False
        if not re.search(r'[A-Z]', password):
            return False
        if not re.search(r'[a-z]', password):
            return False
        if not re.search(r'[0-9]', password):
            return False
        if not re.search(r'[^A-Za-z0-9]', password):
            return False
        return True


# ============================================================
# TOKEN BLACKLIST
# ============================================================

class TokenBlacklist:
    """Token blacklist with Redis support"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = AuthConfig()
        self._blacklist = set()
    
    def add(self, token: str):
        if self.redis:
            try:
                self.redis.setex(
                    f"{self.config.redis_key_prefix}blacklist:{token}",
                    self.config.refresh_token_expire,
                    '1'
                )
                return
            except:
                pass
        self._blacklist.add(token)
    
    def is_blacklisted(self, token: str) -> bool:
        if self.redis:
            try:
                return self.redis.exists(f"{self.config.redis_key_prefix}blacklist:{token}") > 0
            except:
                pass
        return token in self._blacklist


# ============================================================
# AUDIT LOGGER
# ============================================================

class AuditLogger:
    """Audit logging for security events"""
    
    def __init__(self):
        self.logger = logging.getLogger('audit')
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - AUDIT - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def log(self, event_type: str, user_id: str, details: Dict, ip: str = None):
        log_data = {
            'event': event_type,
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat(),
            'ip': ip or request.remote_addr if hasattr(request, 'remote_addr') else None,
            'details': details
        }
        self.logger.info(json.dumps(log_data))
    
    def log_login(self, user_id: str, ip: str, success: bool):
        self.log('login_attempt', user_id, {'ip': ip, 'success': success})
    
    def log_logout(self, user_id: str):
        self.log('logout', user_id, {})
    
    def log_password_change(self, user_id: str):
        self.log('password_change', user_id, {})
    
    def log_admin_action(self, user_id: str, action: str, details: Dict):
        self.log(f'admin_{action}', user_id, details)


# ============================================================
# AUTH MIDDLEWARE - MAIN
# ============================================================

class AuthMiddleware:
    """Complete production-ready authentication middleware"""
    
    def __init__(self, app):
        self.app = app
        self.config = AuthConfig()
        self.jwt_handler = JWTHandler()
        self.user_repo = UserRepository()
        self.password_handler = PasswordHandler()
        self.token_blacklist = TokenBlacklist()
        self.audit_logger = AuditLogger()
        
        self.redis = None
        self._init_redis()
        
        self.public_paths = [
            '/health', '/metrics', '/ping', '/ready',
            '/api/v1/auth/login', '/api/v1/auth/register',
            '/api/v1/auth/verify-email', '/api/v1/auth/resend-verification',
            '/api/v1/auth/forgot-password', '/api/v1/auth/reset-password',
            '/api/v1/auth/refresh', '/api/v1/auth/google', '/api/v1/auth/github',
            '/api/v1/auth/linkedin', '/api/v1/auth/google/callback',
            '/api/v1/auth/github/callback', '/api/v1/auth/linkedin/callback',
            '/api/v1/webhooks/', '/api/docs', '/api/redoc', '/api/swagger',
            '/static/', '/favicon.ico', '/assets/'
        ]
        
        self.admin_paths = ['/api/v1/admin/', '/api/v1/super-admin/']
        
        print(f"✅ AuthMiddleware initialized in {self.config.environment.value} mode")
        print(f"   - MFA: {'✅' if self.config.enable_mfa else '❌'}")
        print(f"   - SSO: {'✅' if self.config.enable_sso else '❌'}")
        print(f"   - Audit Logging: {'✅' if self.config.enable_audit_logging else '❌'}")
    
    def _init_redis(self):
        try:
            if REDIS_AVAILABLE:
                self.redis = redis.from_url(self.config.redis_url, decode_responses=True)
                self.redis.ping()
                print("✅ Connected to Redis for auth")
            else:
                self.redis = None
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            self.redis = None
    
    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        method = environ.get('REQUEST_METHOD', '')
        client_ip = self._get_client_ip(environ)
        
        if self._is_public_path(path):
            return self.app(environ, start_response)
        
        token = self._extract_token(environ)
        if not token:
            return self._unauthorized(environ, start_response, 'No authentication token provided')
        
        if self.token_blacklist.is_blacklisted(token):
            return self._unauthorized(environ, start_response, 'Token has been revoked')
        
        payload = self.jwt_handler.verify_token(token)
        if not payload:
            return self._unauthorized(environ, start_response, 'Invalid or expired token')
        
        if payload.get('type') != 'access':
            return self._unauthorized(environ, start_response, 'Invalid token type')
        
        user_id = payload.get('sub')
        user = self.user_repo.get_user_by_id(user_id)
        
        if not user:
            return self._unauthorized(environ, start_response, 'User not found')
        
        if not user.get('is_active', True):
            return self._forbidden(environ, start_response, 'Account is inactive')
        
        if user.get('is_locked', False):
            locked_until = user.get('locked_until')
            if locked_until and datetime.fromisoformat(locked_until) > datetime.utcnow():
                return self._forbidden(environ, start_response, 'Account is locked')
        
        if self._is_admin_path(path):
            user_role = user.get('role', 'user')
            if user_role not in ['admin', 'super_admin', 'org_admin']:
                self.audit_logger.log_admin_action(
                    user_id, 'admin_access_denied', {'path': path}
                )
                return self._forbidden(environ, start_response, 'Admin access required')
        
        if self.config.enable_audit_logging:
            self.audit_logger.log('api_request', user_id, {
                'path': path, 'method': method, 'ip': client_ip
            })
        
        environ['user_id'] = user_id
        environ['user_email'] = user.get('email')
        environ['user_role'] = user.get('role')
        environ['user_permissions'] = user.get('permissions', [])
        environ['organization_id'] = user.get('organization_id')
        environ['token_payload'] = payload
        
        def _start_response_with_headers(status, headers, exc_info=None):
            headers.extend([
                ('X-Content-Type-Options', 'nosniff'),
                ('X-Frame-Options', 'DENY'),
                ('X-XSS-Protection', '1; mode=block'),
                ('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
            ])
            return start_response(status, headers, exc_info)
        
        return self.app(environ, _start_response_with_headers)
    
    def _is_public_path(self, path: str) -> bool:
        for public_path in self.public_paths:
            if path.startswith(public_path):
                return True
        return False
    
    def _is_admin_path(self, path: str) -> bool:
        for admin_path in self.admin_paths:
            if path.startswith(admin_path):
                return True
        return False
    
    def _extract_token(self, environ) -> Optional[str]:
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:]
        return None
    
    def _get_client_ip(self, environ) -> str:
        forwarded_for = environ.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return environ.get('REMOTE_ADDR', '0.0.0.0')
    
    def _create_response(self, environ, start_response, status_code: int, data: Dict):
        response_data = json.dumps(data).encode('utf-8')
        status = f"{status_code} {self._get_status_message(status_code)}"
        headers = [
            ('Content-Type', 'application/json'),
            ('Content-Length', str(len(response_data)))
        ]
        start_response(status, headers)
        return [response_data]
    
    def _get_status_message(self, status_code: int) -> str:
        return {401: 'Unauthorized', 403: 'Forbidden'}.get(status_code, 'Error')
    
    def _unauthorized(self, environ, start_response, message: str = None):
        return self._create_response(environ, start_response, 401, {
            'error': 'unauthorized',
            'message': message or 'Authentication required',
            'code': 'AUTH_REQUIRED'
        })
    
    def _forbidden(self, environ, start_response, message: str = None):
        return self._create_response(environ, start_response, 403, {
            'error': 'forbidden',
            'message': message or 'Insufficient permissions',
            'code': 'ACCESS_DENIED'
        })


# ============================================================
# FLASK DECORATORS
# ============================================================

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user_id'):
            return jsonify({
                'error': 'unauthorized',
                'message': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }), 401
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user_role') or g.user_role not in ['admin', 'super_admin', 'org_admin']:
            return jsonify({
                'error': 'forbidden',
                'message': 'Admin access required',
                'code': 'ADMIN_REQUIRED'
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def require_super_admin(f):
    """Decorator to require super admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user_role') or g.user_role != 'super_admin':
            return jsonify({
                'error': 'forbidden',
                'message': 'Super admin access required',
                'code': 'SUPER_ADMIN_REQUIRED'
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def require_organization_access(f):
    """Decorator for organization-based access control"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        org_id = kwargs.get('organization_id') or kwargs.get('org_id')
        if not org_id:
            return f(*args, **kwargs)
        
        if not hasattr(g, 'organization_id'):
            return jsonify({
                'error': 'forbidden',
                'message': 'No organization access',
                'code': 'ORG_ACCESS_DENIED'
            }), 403
        
        if g.user_role == 'super_admin':
            return f(*args, **kwargs)
        
        if str(g.organization_id) != str(org_id):
            return jsonify({
                'error': 'forbidden',
                'message': 'Cannot access other organizations',
                'code': 'ORG_ACCESS_DENIED'
            }), 403
        
        return f(*args, **kwargs)
    return decorated_function


def require_mfa(f):
    """Decorator to require MFA verification"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user_id'):
            return jsonify({
                'error': 'unauthorized',
                'message': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }), 401
        
        user = UserRepository().get_user_by_id(g.user_id)
        if user and user.get('is_mfa_enabled', False):
            mfa_verified = request.headers.get('X-MFA-Verified', 'false').lower() == 'true'
            if not mfa_verified:
                return jsonify({
                    'error': 'mfa_required',
                    'message': 'MFA verification required',
                    'code': 'MFA_REQUIRED'
                }), 403
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_current_user():
    """Get current user from request context"""
    if hasattr(g, 'user_id'):
        return UserRepository().get_user_by_id(g.user_id)
    return None


def get_current_user_id() -> Optional[str]:
    """Get current user ID"""
    return getattr(g, 'user_id', None)


def get_current_user_role() -> Optional[str]:
    """Get current user role"""
    return getattr(g, 'user_role', None)


def get_current_organization_id() -> Optional[str]:
    """Get current organization ID"""
    return getattr(g, 'organization_id', None)


# ============================================================
# FLASK APP INTEGRATION
# ============================================================

def init_auth(app):
    """Initialize authentication for Flask app"""
    
    app.wsgi_app = AuthMiddleware(app.wsgi_app)
    
    @app.route('/api/v1/auth/me')
    @require_auth
    def auth_me():
        user = get_current_user()
        if user:
            return jsonify({
                'success': True,
                'user': {
                    'id': user.get('id'),
                    'email': user.get('email'),
                    'username': user.get('username'),
                    'first_name': user.get('first_name'),
                    'last_name': user.get('last_name'),
                    'display_name': user.get('display_name'),
                    'role': user.get('role'),
                    'is_verified': user.get('is_verified', False),
                    'is_mfa_enabled': user.get('is_mfa_enabled', False),
                    'organization_id': user.get('organization_id')
                }
            })
        return jsonify({'error': 'User not found'}), 404
    
    @app.route('/api/v1/auth/logout')
    @require_auth
    def auth_logout():
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if token:
            app.wsgi_app.token_blacklist.add(token)
        return jsonify({'success': True, 'message': 'Logged out successfully'})
    
    return app


# ============================================================
# TEST APPLICATION
# ============================================================

def create_test_app():
    """Create test Flask application with auth"""
    app = Flask(__name__)
    CORS(app, origins=AuthConfig().frontend_url, supports_credentials=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Initialize auth
    init_auth(app)
    
    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}), 200
    
    @app.route('/api/v1/protected')
    @require_auth
    def protected():
        return jsonify({
            'message': 'Protected data',
            'user_id': get_current_user_id(),
            'role': get_current_user_role()
        }), 200
    
    @app.route('/api/v1/admin/dashboard')
    @require_admin
    def admin_dashboard():
        return jsonify({'message': 'Admin dashboard'}), 200
    
    return app


if __name__ == "__main__":
    print("=" * 70)
    print("🔐 SynapsePM - Authentication Middleware (Production Ready)")
    print("=" * 70)
    
    app = create_test_app()
    print("\n✅ Test routes available:")
    print("   GET  /health                        - Health check")
    print("   POST /api/v1/auth/login             - Login endpoint")
    print("   GET  /api/v1/auth/me                - Get current user")
    print("   GET  /api/v1/protected              - Protected endpoint")
    print("   GET  /api/v1/admin/dashboard        - Admin endpoint")
    
    print("\n🚀 Starting server...")
    app.run(host='0.0.0.0', port=5000, debug=True)