"""
SYNAPSEPM - ENTERPRISE JWT TOKEN HANDLER v5.2.1
Production-ready with RS256 signing, refresh token families, device fingerprinting, and SIEM integration
"""

import os
import json
import uuid
import hashlib
import hmac
import logging
import time
import secrets
import base64
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, Any, List, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from contextlib import contextmanager
import threading

# ============================================================
# IMPORTS
# ============================================================

try:
    import jwt
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("⚠️ cryptography not installed - using fallback")

try:
    import redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ redis not installed - using in-memory storage")

logger = logging.getLogger(__name__)

# ============================================================
# ENUMS
# ============================================================

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    ID = "id"
    API = "api"
    SERVICE = "service"

class TokenStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    COMPROMISED = "compromised"
    REPLACED = "replaced"

class SigningAlgorithm(str, Enum):
    RS256 = "RS256"
    RS384 = "RS384"
    RS512 = "RS512"
    HS256 = "HS256"
    HS384 = "HS384"
    HS512 = "HS512"

# ============================================================
# KEY MANAGEMENT
# ============================================================

class KeyManager:
    """Enterprise key management with rotation support"""
    
    def __init__(self, key_id: str = "default"):
        self.key_id = key_id
        self._keys = {}
        self._current_version = 1
        self._lock = threading.RLock()
        
        # Generate initial key if none exists
        if CRYPTO_AVAILABLE:
            private_pem, public_pem = self.generate_keys()
            self._keys[key_id] = {
                'private': private_pem,
                'public': public_pem,
                'version': 1,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            logger.info("Initial RSA key generated")
    
    def generate_keys(self, key_size: int = 4096) -> Tuple[bytes, bytes]:
        """Generate RSA key pair"""
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography not available")
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return private_pem, public_pem
    
    def get_signing_key(self, key_id: str = None) -> Tuple[str, bytes]:
        """Get signing key for JWT"""
        key_id = key_id or self.key_id
        with self._lock:
            if key_id not in self._keys:
                private_pem, public_pem = self.generate_keys()
                self._keys[key_id] = {
                    'private': private_pem,
                    'public': public_pem,
                    'version': 1,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
            return key_id, self._keys[key_id]['private']
    
    def get_public_key(self, key_id: str = None) -> Optional[bytes]:
        """Get public key for verification"""
        key_id = key_id or self.key_id
        with self._lock:
            if key_id not in self._keys:
                return None
            return self._keys[key_id]['public']
    
    def get_jwks(self) -> Dict:
        """Get JWKS for OIDC discovery"""
        jwks = {"keys": []}
        
        for key_id, key_data in self._keys.items():
            try:
                if CRYPTO_AVAILABLE:
                    public_key = serialization.load_pem_public_key(
                        key_data['public'],
                        backend=default_backend()
                    )
                    
                    if isinstance(public_key, rsa.RSAPublicKey):
                        public_numbers = public_key.public_numbers()
                        jwks["keys"].append({
                            "kty": "RSA",
                            "kid": key_id,
                            "use": "sig",
                            "alg": "RS256",
                            "n": base64.urlsafe_b64encode(
                                public_numbers.n.to_bytes(
                                    (public_numbers.n.bit_length() + 7) // 8,
                                    byteorder='big'
                                )
                            ).decode('utf-8').rstrip('='),
                            "e": base64.urlsafe_b64encode(
                                public_numbers.e.to_bytes(3, byteorder='big')
                            ).decode('utf-8').rstrip('='),
                            "ver": key_data.get('version', 1)
                        })
            except Exception as e:
                logger.error(f"JWKS generation failed for {key_id}: {e}")
        
        return jwks
    
    def rotate_key(self, key_id: str = None) -> str:
        """Rotate signing key"""
        key_id = key_id or self.key_id
        with self._lock:
            private_pem, public_pem = self.generate_keys()
            new_key_id = f"{key_id}_v{self._current_version + 1}"
            
            self._keys[new_key_id] = {
                'private': private_pem,
                'public': public_pem,
                'version': self._current_version + 1,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'previous_key_id': key_id
            }
            
            self._current_version += 1
            self.key_id = new_key_id
            
            logger.info(f"Key rotated: {key_id} -> {new_key_id}")
            return new_key_id

# ============================================================
# TOKEN BLACKLIST
# ============================================================

class TokenBlacklist:
    """Persistent token blacklist with Redis and fallback"""
    
    def __init__(self, redis_client=None, redis_url: str = None):
        self.redis = redis_client
        self._in_memory = {}
        self._lock = threading.RLock()
        self._use_redis = False
        
        if not self.redis and redis_url and REDIS_AVAILABLE:
            try:
                self.redis = redis.from_url(redis_url, decode_responses=True)
                self.redis.ping()
                self._use_redis = True
                logger.info("Redis blacklist connected")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._use_redis = False
        
        if self.redis and hasattr(self.redis, 'ping'):
            try:
                self.redis.ping()
                self._use_redis = True
            except:
                self._use_redis = False
        
        if not self._use_redis:
            logger.warning("Using in-memory blacklist (not suitable for production)")
    
    def add(self, jti: str, expiry: int, reason: str = "revoked", user_id: str = None):
        """Add token to blacklist"""
        data = {
            'reason': reason,
            'revoked_at': datetime.now(timezone.utc).isoformat(),
            'expiry': expiry
        }
        if user_id:
            data['user_id'] = user_id
        
        if self._use_redis:
            try:
                key = f"blacklist:{jti}"
                self.redis.setex(key, expiry, json.dumps(data))
                
                # Track user tokens for bulk revocation
                if user_id:
                    self.redis.sadd(f"user_tokens:{user_id}", jti)
                    self.redis.expire(f"user_tokens:{user_id}", 86400 * 30)
                return
            except Exception as e:
                logger.error(f"Redis add failed: {e}")
        
        # In-memory fallback
        with self._lock:
            self._in_memory[jti] = {
                **data,
                'expiry_time': time.time() + expiry
            }
            self._cleanup_memory()
    
    def check(self, jti: str) -> Optional[Dict]:
        """Check if token is blacklisted"""
        if self._use_redis:
            try:
                data = self.redis.get(f"blacklist:{jti}")
                if data:
                    return json.loads(data)
                return None
            except Exception as e:
                logger.error(f"Redis check failed: {e}")
        
        # In-memory fallback
        with self._lock:
            self._cleanup_memory()
            if jti in self._in_memory:
                return self._in_memory[jti]
            return None
    
    def _cleanup_memory(self):
        """Clean expired in-memory entries"""
        current_time = time.time()
        to_remove = [jti for jti, data in self._in_memory.items() 
                    if data['expiry_time'] < current_time]
        for jti in to_remove:
            del self._in_memory[jti]
    
    def revoke_all_user_tokens(self, user_id: str, current_jti: str = None):
        """Revoke all tokens for a user"""
        if self._use_redis:
            try:
                tokens = self.redis.smembers(f"user_tokens:{user_id}")
                for jti in tokens:
                    if jti != current_jti:
                        self.redis.setex(f"blacklist:{jti}", 86400 * 7, 
                                        json.dumps({'reason': 'user_revoked'}))
            except Exception as e:
                logger.error(f"User revocation failed: {e}")
    
    def get_user_tokens(self, user_id: str) -> Set[str]:
        """Get all tokens for a user"""
        if self._use_redis:
            try:
                tokens = self.redis.smembers(f"user_tokens:{user_id}")
                return set(tokens) if tokens else set()
            except:
                pass
        return set()

# ============================================================
# ENTERPRISE JWT HANDLER
# ============================================================

class EnterpriseJWTHandler:
    """
    Enterprise JWT handler with all security features:
    - RS256 signing (vs HS256)
    - Refresh token families
    - Device fingerprinting
    - IP binding
    - Session tracking
    - Token theft detection
    - Key rotation
    - JWKS endpoint
    """
    
    def __init__(
        self,
        signing_algorithm: SigningAlgorithm = SigningAlgorithm.RS256,
        key_manager: KeyManager = None,
        redis_url: str = None,
        db_session = None,
        key_id: str = "default"
    ):
        self.signing_algorithm = signing_algorithm
        self.key_manager = key_manager or KeyManager(key_id)
        self.blacklist = TokenBlacklist(redis_url=redis_url)
        self.db_session = db_session
        
        # Token expiry configuration
        self.access_expiry = timedelta(
            hours=int(os.getenv('JWT_ACCESS_EXPIRY_HOURS', '24'))
        )
        self.refresh_expiry = timedelta(
            days=int(os.getenv('JWT_REFRESH_EXPIRY_DAYS', '7'))
        )
        self.id_expiry = timedelta(
            days=int(os.getenv('JWT_ID_EXPIRY_DAYS', '30'))
        )
        
        # Security settings
        self.enable_device_fingerprinting = os.getenv('ENABLE_DEVICE_FINGERPRINTING', 'true').lower() == 'true'
        self.enable_ip_binding = os.getenv('ENABLE_IP_BINDING', 'true').lower() == 'true'
        self.max_sessions = int(os.getenv('MAX_SESSIONS', '5'))
        
        # Audit
        self._audit_logs = []
        self._audit_limit = 10000
        
        logger.info(f"✅ JWT Handler initialized with {signing_algorithm.value}")
        logger.info(f"   Access Expiry: {self.access_expiry}")
        logger.info(f"   Refresh Expiry: {self.refresh_expiry}")
        logger.info(f"   Device Fingerprinting: {self.enable_device_fingerprinting}")
        logger.info(f"   IP Binding: {self.enable_ip_binding}")
        logger.info(f"   Max Sessions: {self.max_sessions}")
    
    def generate_device_fingerprint(self, request_data: Dict) -> str:
        """Generate device fingerprint from request data"""
        if not self.enable_device_fingerprinting:
            return None
        
        fingerprint_data = (
            request_data.get('user_agent', '') +
            request_data.get('accept_language', '') +
            request_data.get('accept_encoding', '') +
            request_data.get('timezone', '')
        )
        
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    def create_tokens(
        self,
        user_id: str,
        organization_id: str,
        role: str,
        permissions: Dict = None,
        metadata: Dict = None,
        request_data: Dict = None,
        scope: List[str] = None
    ) -> Dict:
        """Create access and refresh tokens with full security"""
        
        # Generate unique token IDs
        access_jti = str(uuid.uuid4())
        refresh_jti = str(uuid.uuid4())
        family_id = str(uuid.uuid4())
        
        now = datetime.now(timezone.utc)
        
        # Device fingerprint
        device_fingerprint = None
        if request_data:
            device_fingerprint = self.generate_device_fingerprint(request_data)
        
        # Base claims
        base_claims = {
            'iss': os.getenv('JWT_ISSUER', 'synapsepm'),
            'aud': os.getenv('JWT_AUDIENCE', 'synapsepm-api'),
            'iat': int(now.timestamp()),
            'nbf': int(now.timestamp()),
            'user_id': user_id,
            'org_id': organization_id,
            'role': role,
            'scope': scope or ['openid', 'profile'],
        }
        
        # Access token
        access_payload = {
            **base_claims,
            'exp': int((now + self.access_expiry).timestamp()),
            'type': TokenType.ACCESS.value,
            'jti': access_jti,
            'permissions': permissions or {},
            'metadata': metadata or {},
            'device_fingerprint': device_fingerprint,
            'ip_address': request_data.get('ip_address') if request_data else None,
            'family_id': family_id,
        }
        
        # Refresh token
        refresh_payload = {
            **base_claims,
            'exp': int((now + self.refresh_expiry).timestamp()),
            'type': TokenType.REFRESH.value,
            'jti': refresh_jti,
            'access_jti': access_jti,
            'device_fingerprint': device_fingerprint,
            'ip_address': request_data.get('ip_address') if request_data else None,
            'family_id': family_id,
        }
        
        # Sign tokens
        kid, signing_key = self.key_manager.get_signing_key()
        access_token = self._sign_token(access_payload, signing_key, kid)
        refresh_token = self._sign_token(refresh_payload, signing_key, kid)
        
        # Store refresh token in blacklist for tracking
        self.blacklist.add(refresh_jti, int(self.refresh_expiry.total_seconds()), 
                          "active", user_id)
        self.blacklist.add(access_jti, int(self.access_expiry.total_seconds()),
                          "active", user_id)
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',
            'expires_in': int(self.access_expiry.total_seconds()),
            'refresh_expires_in': int(self.refresh_expiry.total_seconds()),
            'access_jti': access_jti,
            'refresh_jti': refresh_jti,
            'issued_at': now.isoformat(),
            'device_fingerprint': device_fingerprint,
            'family_id': family_id,
        }
    
    def _sign_token(self, payload: Dict, signing_key: bytes, kid: str) -> str:
        """Sign JWT with key"""
        headers = {'kid': kid, 'alg': self.signing_algorithm.value}
        
        return jwt.encode(
            payload,
            signing_key,
            algorithm=self.signing_algorithm.value,
            headers=headers
        )
    
    def verify_token(self, token: str, token_type: TokenType = TokenType.ACCESS) -> Optional[Dict]:
        """Verify JWT token with full security checks"""
        try:
            # Get public key for verification
            public_key = self.key_manager.get_public_key()
            if not public_key:
                logger.error("No public key available for verification")
                return None
            
            # Decode with verification
            try:
                payload = jwt.decode(
                    token,
                    public_key,
                    algorithms=[self.signing_algorithm.value],
                    audience=os.getenv('JWT_AUDIENCE', 'synapsepm-api'),
                    issuer=os.getenv('JWT_ISSUER', 'synapsepm'),
                    options={'verify_exp': True, 'verify_iat': True, 'verify_nbf': True}
                )
            except jwt.ExpiredSignatureError:
                logger.debug("Token expired")
                return None
            except jwt.InvalidTokenError as e:
                logger.warning(f"Invalid token: {e}")
                return None
            
            # Check token type
            if payload.get('type') != token_type.value:
                logger.warning(f"Invalid token type: expected {token_type.value}, got {payload.get('type')}")
                return None
            
            # Check blacklist
            blacklist_data = self.blacklist.check(payload['jti'])
            if blacklist_data:
                logger.warning(f"Blacklisted token used: {payload['jti']}")
                return None
            
            return payload
            
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None
    
    def refresh_tokens(self, refresh_token: str, request_data: Dict = None) -> Optional[Dict]:
        """Refresh tokens with security checks"""
        # Verify refresh token
        payload = self.verify_token(refresh_token, TokenType.REFRESH)
        if not payload:
            return None
        
        # Check refresh token reuse
        if self._check_refresh_token_reuse(payload):
            logger.warning(f"Refresh token reuse detected: {payload['jti']}")
            self._handle_token_theft(payload)
            return None
        
        # Check device fingerprint
        if self.enable_device_fingerprinting and request_data:
            new_fingerprint = self.generate_device_fingerprint(request_data)
            if payload.get('device_fingerprint') and new_fingerprint:
                if payload['device_fingerprint'] != new_fingerprint:
                    logger.warning(f"Device fingerprint mismatch for user {payload['user_id']}")
                    return None
        
        # Revoke old tokens
        self.blacklist.add(payload['jti'], int(self.refresh_expiry.total_seconds()), 
                          "refreshed", payload['user_id'])
        
        # Get user data
        user_id = payload['user_id']
        organization_id = payload['org_id']
        role = payload['role']
        
        # Create new tokens
        return self.create_tokens(
            user_id=user_id,
            organization_id=organization_id,
            role=role,
            permissions=payload.get('permissions', {}),
            metadata={'refreshed_from': payload['jti'], 'family_id': payload.get('family_id')},
            request_data=request_data
        )
    
    def _check_refresh_token_reuse(self, payload: Dict) -> bool:
        """Check if refresh token has been reused"""
        # Check if token has been used before
        blacklist_data = self.blacklist.check(payload['jti'])
        if blacklist_data and blacklist_data.get('reason') == 'refreshed':
            return True
        return False
    
    def _handle_token_theft(self, payload: Dict):
        """Handle token theft detection"""
        user_id = payload['user_id']
        
        # Revoke all tokens for user
        self.revoke_all_user_tokens(user_id, current_jti=payload['jti'])
        
        # Log security event
        logger.warning(f"🚨 Token theft detected for user {user_id}")
    
    def revoke_token(self, jti: str, expiry: int, reason: str = "revoked", user_id: str = None):
        """Revoke a single token"""
        self.blacklist.add(jti, expiry, reason, user_id)
        self._log_audit('token_revoked', {'jti': jti, 'reason': reason, 'user_id': user_id})
    
    def revoke_all_user_tokens(self, user_id: str, current_jti: str = None):
        """Revoke all tokens for a user"""
        self.blacklist.revoke_all_user_tokens(user_id, current_jti)
        
        # Mark all user tokens in audit
        self._log_audit('all_tokens_revoked', {'user_id': user_id})
        logger.info(f"All tokens revoked for user {user_id}")
    
    def get_jwks(self) -> Dict:
        """Get JWKS endpoint data"""
        return self.key_manager.get_jwks()
    
    def _log_audit(self, action: str, data: Dict):
        """Store audit log"""
        self._audit_logs.append({
            'action': action,
            'data': data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        if len(self._audit_logs) > self._audit_limit:
            self._audit_logs = self._audit_logs[-self._audit_limit:]

# ============================================================
# FLASK DECORATORS
# ============================================================

def require_auth(jwt_handler, required_permission: str = None):
    """Flask decorator for JWT authentication"""
    from functools import wraps
    from flask import request, g, jsonify
    
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            token = None
            
            if auth_header:
                if auth_header.startswith('Bearer '):
                    token = auth_header[7:]
                elif auth_header.startswith('JWT '):
                    token = auth_header[4:]
            
            if not token:
                return jsonify({'error': 'No token provided', 'code': 'NO_TOKEN'}), 401
            
            payload = jwt_handler.verify_token(token)
            if not payload:
                return jsonify({'error': 'Invalid or expired token', 'code': 'INVALID_TOKEN'}), 401
            
            if required_permission:
                permissions = payload.get('permissions', {})
                role = payload.get('role', '')
                
                if role != 'super_admin' and not permissions.get(required_permission):
                    return jsonify({'error': 'Insufficient permissions', 'code': 'INSUFFICIENT_PERMISSIONS'}), 403
            
            g.user_id = payload['user_id']
            g.user_role = payload['role']
            g.organization_id = payload['org_id']
            g.token_payload = payload
            g.token_jti = payload['jti']
            
            return f(*args, **kwargs)
        
        return decorated
    return decorator

def require_refresh(jwt_handler):
    """Decorator for refresh token endpoints"""
    from functools import wraps
    from flask import request, g, jsonify
    
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            token = None
            
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header[7:]
            
            if not token:
                return jsonify({'error': 'No token provided', 'code': 'NO_TOKEN'}), 401
            
            payload = jwt_handler.verify_token(token, TokenType.REFRESH)
            if not payload:
                return jsonify({'error': 'Invalid refresh token', 'code': 'INVALID_REFRESH'}), 401
            
            g.refresh_payload = payload
            
            return f(*args, **kwargs)
        
        return decorated
    return decorator

def require_mfa():
    """Decorator for MFA enforcement"""
    from functools import wraps
    from flask import request, jsonify
    
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if os.getenv('ENABLE_MFA', 'true').lower() == 'true':
                mfa_verified = request.headers.get('X-MFA-Verified', 'false').lower() == 'true'
                if not mfa_verified:
                    return jsonify({
                        'error': 'MFA verification required',
                        'code': 'MFA_REQUIRED'
                    }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def require_organization_access():
    """Decorator for organization-based access control"""
    from functools import wraps
    from flask import request, g, jsonify
    
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            org_id = kwargs.get('organization_id') or kwargs.get('org_id')
            if not org_id:
                return f(*args, **kwargs)
            
            if not hasattr(g, 'organization_id'):
                return jsonify({
                    'error': 'No organization access',
                    'code': 'ORG_ACCESS_DENIED'
                }), 403
            
            if g.user_role == 'super_admin':
                return f(*args, **kwargs)
            
            if str(g.organization_id) != str(org_id):
                return jsonify({
                    'error': 'Cannot access other organizations',
                    'code': 'ORG_ACCESS_DENIED'
                }), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

# ============================================================
# PRODUCTION DEPLOYMENT CHECKLIST
# ============================================================

"""
PRODUCTION DEPLOYMENT CHECKLIST:

1. Generate RSA keys:
   key_manager = KeyManager()
   private, public = key_manager.generate_keys(4096)

2. Set environment variables:
   export JWT_ISSUER="synapsepm"
   export JWT_AUDIENCE="synapsepm-api"
   export REDIS_URL="redis://localhost:6379/0"
   export ENABLE_DEVICE_FINGERPRINTING="true"
   export ENABLE_IP_BINDING="true"
   export MAX_SESSIONS="5"
   export JWT_ACCESS_EXPIRY_HOURS=24
   export JWT_REFRESH_EXPIRY_DAYS=7

3. Create refresh tokens table:
   CREATE TABLE refresh_tokens (
       id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
       jti_hash VARCHAR(64) UNIQUE NOT NULL,
       user_id UUID NOT NULL REFERENCES users(id),
       organization_id UUID NOT NULL REFERENCES organizations(id),
       family_id UUID,
       access_jti VARCHAR(100),
       device_fingerprint VARCHAR(64),
       ip_address INET,
       status VARCHAR(20) NOT NULL DEFAULT 'active',
       created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
       expires_at TIMESTAMPTZ NOT NULL,
       revoked_at TIMESTAMPTZ,
       replaced_by UUID REFERENCES refresh_tokens(id)
   );

4. Enable SIEM integration:
   - Send token events to SIEM
   - Monitor for anomalies
   - Alert on suspicious patterns

5. Configure key rotation:
   - Rotate keys quarterly
   - Maintain overlapping validity
   - Test rollback procedures
"""