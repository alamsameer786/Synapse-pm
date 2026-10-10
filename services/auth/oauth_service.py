"""
SYNAPSEPM - ENTERPRISE OAUTH SERVICE v5.2.1
Production-ready with PKCE, ID Token validation, and zero-trust security
"""

import os
import json
import jwt
import hashlib
import base64
import secrets
import logging
import time
import requests
import hmac
from typing import Dict, Optional, Tuple, Any, List, Union
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, parse_qs
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ redis not installed - using session storage")

logger = logging.getLogger(__name__)

# ============================================================
# ENUMS
# ============================================================

class OAuthProvider(str, Enum):
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    GITHUB = "github"
    LINKEDIN = "linkedin"

class OAuthFlow(str, Enum):
    AUTHORIZATION_CODE = "authorization_code"
    PKCE = "pkce"
    CLIENT_CREDENTIALS = "client_credentials"

# ============================================================
# PKCE SERVICE
# ============================================================

class PKCEService:
    """PKCE (Proof Key for Code Exchange) implementation"""
    
    @staticmethod
    def generate_code_verifier(length: int = 128) -> str:
        """Generate code_verifier for PKCE"""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def generate_code_challenge(verifier: str, method: str = "S256") -> str:
        """Generate code_challenge from verifier"""
        if method == "S256":
            digest = hashlib.sha256(verifier.encode()).digest()
            return base64.urlsafe_b64encode(digest).decode().rstrip('=')
        return verifier
    
    @staticmethod
    def verify_code_verifier(verifier: str, challenge: str, method: str = "S256") -> bool:
        """Verify code verifier matches challenge"""
        expected = PKCEService.generate_code_challenge(verifier, method)
        return hmac.compare_digest(expected, challenge)

# ============================================================
# ID TOKEN VALIDATOR
# ============================================================

class IDTokenValidator:
    """Validate OIDC ID Tokens with JWKS"""
    
    def __init__(self):
        self._jwks_cache = {}
        self._cache_ttl = 3600
        self._cache_timestamp = {}
        self._lock = threading.RLock() if 'threading' in dir() else None
    
    def validate_token(self, token: str, provider: str, client_id: str, nonce: str = None) -> Dict:
        """Validate ID token with full security checks"""
        try:
            # Get JWKS for provider
            jwks = self._get_jwks(provider)
            if not jwks:
                raise ValueError(f"No JWKS available for {provider}")
            
            # Provider-specific issuers
            issuers = {
                'google': ['https://accounts.google.com', 'accounts.google.com'],
                'microsoft': ['https://login.microsoftonline.com/common/v2.0',
                            'https://login.microsoftonline.com/common'],
                'linkedin': ['https://www.linkedin.com']
            }
            
            # Decode and validate
            payload = jwt.decode(
                token,
                jwks,
                algorithms=['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512'],
                options={
                    'verify_signature': True,
                    'verify_exp': True,
                    'verify_iat': True,
                    'verify_aud': True,
                    'verify_iss': True
                },
                audience=client_id,
                issuer=issuers.get(provider, [None])[0] if provider in issuers else None,
                leeway=60
            )
            
            # Validate nonce
            if nonce and payload.get('nonce') != nonce:
                raise ValueError("Invalid nonce")
            
            # Validate azp if present
            if 'azp' in payload and payload['azp'] != client_id:
                raise ValueError("Invalid azp")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise ValueError("ID token expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid ID token: {e}")
    
    def _get_jwks(self, provider: str) -> Dict:
        """Get JWKS for provider with caching"""
        # Check cache
        if provider in self._jwks_cache:
            if time.time() - self._cache_timestamp.get(provider, 0) < self._cache_ttl:
                return self._jwks_cache[provider]
        
        # Provider-specific JWKS endpoints
        endpoints = {
            'google': 'https://www.googleapis.com/oauth2/v3/certs',
            'microsoft': 'https://login.microsoftonline.com/common/discovery/v2.0/keys',
            'linkedin': 'https://www.linkedin.com/oauth/openid/jwks'
        }
        
        endpoint = endpoints.get(provider)
        if not endpoint:
            return None
        
        try:
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            jwks = response.json()
            
            self._jwks_cache[provider] = jwks
            self._cache_timestamp[provider] = time.time()
            return jwks
            
        except Exception as e:
            logger.error(f"Failed to fetch JWKS for {provider}: {e}")
            return None

# ============================================================
# ENTERPRISE OAUTH SERVICE
# ============================================================

class EnterpriseOAuthService:
    """
    Enterprise OAuth authentication service with all security features
    """
    
    def __init__(self, user_repository=None, jwt_handler=None, redis_url: str = None):
        self.user_repository = user_repository
        self.jwt_handler = jwt_handler
        self.id_token_validator = IDTokenValidator()
        self.pkce_service = PKCEService()
        
        # Redis for state storage
        self.redis = None
        if redis_url and REDIS_AVAILABLE:
            try:
                self.redis = redis.from_url(redis_url, decode_responses=True)
                self.redis.ping()
                logger.info("✅ Redis connected for OAuth state")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
        
        # Load configuration
        self.base_url = os.getenv('BASE_URL', 'http://localhost:5000')
        self.enable_pkce = os.getenv('ENABLE_PKCE', 'true').lower() == 'true'
        self.enforce_domain_allowlist = os.getenv('ENFORCE_DOMAIN_ALLOWLIST', 'false').lower() == 'true'
        self.allowed_domains = os.getenv('ALLOWED_DOMAINS', '').split(',')
        
        # OAuth Providers
        self.providers = self._init_providers()
        
        logger.info("✅ OAuth Service initialized")
        logger.info(f"   PKCE: {'✅' if self.enable_pkce else '❌'}")
        logger.info(f"   Providers: {list(self.providers.keys())}")
    
    def _init_providers(self) -> Dict:
        """Initialize provider configurations"""
        providers = {}
        
        # Google OAuth
        if os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET'):
            providers['google'] = {
                'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
                'token_url': 'https://oauth2.googleapis.com/token',
                'userinfo_url': 'https://www.googleapis.com/oauth2/v3/userinfo',
                'revoke_url': 'https://oauth2.googleapis.com/revoke',
                'scope': 'openid email profile',
                'redirect_uri': os.getenv('GOOGLE_REDIRECT_URI', f"{self.base_url}/auth/google/callback"),
                'response_type': 'code',
                'issuer': 'https://accounts.google.com',
                'enable_pkce': True,
                'require_id_token': True,
                'hosted_domain': os.getenv('GOOGLE_HOSTED_DOMAIN')
            }
        
        # GitHub OAuth
        if os.getenv('GITHUB_CLIENT_ID') and os.getenv('GITHUB_CLIENT_SECRET'):
            providers['github'] = {
                'client_id': os.getenv('GITHUB_CLIENT_ID'),
                'client_secret': os.getenv('GITHUB_CLIENT_SECRET'),
                'auth_url': 'https://github.com/login/oauth/authorize',
                'token_url': 'https://github.com/login/oauth/access_token',
                'userinfo_url': 'https://api.github.com/user',
                'emails_url': 'https://api.github.com/user/emails',
                'scope': 'read:user user:email',
                'redirect_uri': os.getenv('GITHUB_REDIRECT_URI', f"{self.base_url}/auth/github/callback"),
                'response_type': 'code',
                'enable_pkce': False,
                'require_id_token': False
            }
        
        # LinkedIn OAuth
        if os.getenv('LINKEDIN_CLIENT_ID') and os.getenv('LINKEDIN_CLIENT_SECRET'):
            providers['linkedin'] = {
                'client_id': os.getenv('LINKEDIN_CLIENT_ID'),
                'client_secret': os.getenv('LINKEDIN_CLIENT_SECRET'),
                'auth_url': 'https://www.linkedin.com/oauth/v2/authorization',
                'token_url': 'https://www.linkedin.com/oauth/v2/accessToken',
                'userinfo_url': 'https://api.linkedin.com/v2/userinfo',
                'scope': 'openid profile email',
                'redirect_uri': os.getenv('LINKEDIN_REDIRECT_URI', f"{self.base_url}/auth/linkedin/callback"),
                'response_type': 'code',
                'enable_pkce': False,
                'require_id_token': True,
                'issuer': 'https://www.linkedin.com'
            }
        
        return providers
    
    def get_authorization_url(
        self,
        provider: str,
        state: str = None,
        nonce: str = None,
        redirect_uri: str = None
    ) -> Dict:
        """Get OAuth authorization URL with PKCE"""
        if provider not in self.providers:
            raise ValueError(f"Unsupported provider: {provider}")
        
        config = self.providers[provider]
        
        state = state or secrets.token_urlsafe(32)
        
        if not nonce and config.get('require_id_token', False):
            nonce = secrets.token_urlsafe(32)
        
        # PKCE support
        code_verifier = None
        code_challenge = None
        if self.enable_pkce and config.get('enable_pkce', False):
            code_verifier = self.pkce_service.generate_code_verifier()
            code_challenge = self.pkce_service.generate_code_challenge(code_verifier)
        
        params = {
            'client_id': config['client_id'],
            'redirect_uri': redirect_uri or config['redirect_uri'],
            'scope': config['scope'],
            'state': state,
            'response_type': config['response_type']
        }
        
        if code_challenge:
            params['code_challenge'] = code_challenge
            params['code_challenge_method'] = 'S256'
        
        if nonce:
            params['nonce'] = nonce
        
        if provider == 'google':
            params['access_type'] = 'offline'
            params['prompt'] = 'consent'
            if config.get('hosted_domain'):
                params['hd'] = config['hosted_domain']
        
        auth_url = f"{config['auth_url']}?{urlencode(params)}"
        
        state_data = {
            'state': state,
            'nonce': nonce,
            'code_verifier': code_verifier,
            'provider': provider,
            'redirect_uri': redirect_uri,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        self._store_state(state, state_data)
        
        return {
            'auth_url': auth_url,
            'state': state,
            'nonce': nonce,
            'code_verifier': code_verifier
        }
    
    def _store_state(self, state: str, data: Dict):
        """Store OAuth state securely"""
        if self.redis:
            try:
                self.redis.setex(f"oauth_state:{state}", 600, json.dumps(data))
                return
            except Exception as e:
                logger.error(f"Redis state store failed: {e}")
        
        # Fallback to Flask session
        try:
            from flask import session
            session[f'oauth_state_{state}'] = data
            session[f'oauth_state_expiry_{state}'] = time.time() + 600
        except:
            pass
    
    def _get_state(self, state: str) -> Optional[Dict]:
        """Retrieve OAuth state"""
        if self.redis:
            try:
                data = self.redis.get(f"oauth_state:{state}")
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Redis state retrieval failed: {e}")
        
        try:
            from flask import session
            expiry = session.get(f'oauth_state_expiry_{state}', 0)
            if time.time() > expiry:
                return None
            return session.get(f'oauth_state_{state}')
        except:
            return None
    
    def _delete_state(self, state: str):
        """Delete OAuth state"""
        if self.redis:
            try:
                self.redis.delete(f"oauth_state:{state}")
                return
            except:
                pass
        
        try:
            from flask import session
            session.pop(f'oauth_state_{state}', None)
            session.pop(f'oauth_state_expiry_{state}', None)
        except:
            pass
    
    def exchange_code(self, provider: str, code: str, state: str) -> Dict:
        """Exchange authorization code for tokens with PKCE"""
        if provider not in self.providers:
            raise ValueError(f"Unsupported provider: {provider}")
        
        state_data = self._get_state(state)
        if not state_data:
            raise ValueError("Invalid or expired state")
        
        self._delete_state(state)
        
        if state_data.get('provider') != provider:
            raise ValueError("Provider mismatch")
        
        config = self.providers[provider]
        
        data = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'redirect_uri': state_data.get('redirect_uri') or config['redirect_uri'],
            'grant_type': 'authorization_code'
        }
        
        # Add PKCE verifier
        if self.enable_pkce and config.get('enable_pkce', False):
            code_verifier = state_data.get('code_verifier')
            if code_verifier:
                data['code_verifier'] = code_verifier
        
        headers = {'Accept': 'application/json'}
        
        try:
            response = requests.post(
                config['token_url'],
                data=data,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            token_data = response.json()
            
            # Validate ID token if present
            if token_data.get('id_token') and config.get('require_id_token', False):
                id_payload = self.id_token_validator.validate_token(
                    token_data['id_token'],
                    provider,
                    config['client_id'],
                    state_data.get('nonce')
                )
                token_data['id_payload'] = id_payload
            
            return {
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token'),
                'expires_in': token_data.get('expires_in', 3600),
                'token_type': token_data.get('token_type', 'Bearer'),
                'id_token': token_data.get('id_token'),
                'id_payload': token_data.get('id_payload')
            }
            
        except requests.RequestException as e:
            logger.error(f"Token exchange failed: {e}")
            raise
    
    def get_user_info(self, provider: str, access_token: str, id_payload: Dict = None) -> Dict:
        """Get user information from provider"""
        if provider not in self.providers:
            raise ValueError(f"Unsupported provider: {provider}")
        
        config = self.providers[provider]
        
        # Use ID token payload if available
        if id_payload and config.get('require_id_token', False):
            return self._normalize_user_from_id_token(provider, id_payload)
        
        headers = {
            'Authorization': f"Bearer {access_token}",
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(
                config['userinfo_url'],
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            user_data = response.json()
            
            # Get emails for GitHub
            if provider == 'github' and not user_data.get('email'):
                user_data['email'] = self._get_github_email(access_token, config)
            
            user_info = self._normalize_user(provider, user_data)
            
            # Validate domain
            if not self._validate_domain(user_info.get('email')):
                raise ValueError("Domain not allowed")
            
            return user_info
            
        except requests.RequestException as e:
            logger.error(f"User info fetch failed: {e}")
            raise
    
    def _normalize_user(self, provider: str, user_data: Dict) -> Dict:
        """Normalize user data"""
        if provider == 'google':
            return {
                'provider': 'google',
                'provider_id': user_data.get('sub'),
                'email': user_data.get('email'),
                'first_name': user_data.get('given_name', ''),
                'last_name': user_data.get('family_name', ''),
                'name': user_data.get('name', ''),
                'avatar_url': user_data.get('picture'),
                'email_verified': user_data.get('email_verified', False),
                'hd': user_data.get('hd')
            }
        elif provider == 'github':
            name = user_data.get('name', '')
            first_name = ''
            last_name = ''
            if name and ' ' in name:
                parts = name.split(' ', 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ''
            elif name:
                first_name = name
            
            return {
                'provider': 'github',
                'provider_id': str(user_data.get('id')),
                'email': user_data.get('email'),
                'first_name': first_name,
                'last_name': last_name,
                'name': name or user_data.get('login', ''),
                'avatar_url': user_data.get('avatar_url'),
                'email_verified': True,
                'username': user_data.get('login')
            }
        elif provider == 'linkedin':
            return {
                'provider': 'linkedin',
                'provider_id': user_data.get('sub'),
                'email': user_data.get('email'),
                'first_name': user_data.get('given_name', ''),
                'last_name': user_data.get('family_name', ''),
                'name': user_data.get('name', ''),
                'avatar_url': user_data.get('picture'),
                'email_verified': user_data.get('email_verified', False)
            }
        return {}
    
    def _normalize_user_from_id_token(self, provider: str, id_payload: Dict) -> Dict:
        """Normalize user from ID token"""
        if provider == 'google':
            return {
                'provider': 'google',
                'provider_id': id_payload.get('sub'),
                'email': id_payload.get('email'),
                'first_name': id_payload.get('given_name', ''),
                'last_name': id_payload.get('family_name', ''),
                'name': id_payload.get('name', ''),
                'avatar_url': id_payload.get('picture'),
                'email_verified': id_payload.get('email_verified', False),
                'hd': id_payload.get('hd')
            }
        elif provider == 'linkedin':
            return {
                'provider': 'linkedin',
                'provider_id': id_payload.get('sub'),
                'email': id_payload.get('email'),
                'first_name': id_payload.get('given_name', ''),
                'last_name': id_payload.get('family_name', ''),
                'name': id_payload.get('name', ''),
                'avatar_url': id_payload.get('picture'),
                'email_verified': True
            }
        return {}
    
    def _get_github_email(self, access_token: str, config: Dict) -> Optional[str]:
        """Get primary email from GitHub"""
        try:
            headers = {
                'Authorization': f"Bearer {access_token}",
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(
                config['emails_url'],
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            emails = response.json()
            for email_data in emails:
                if email_data.get('primary') and email_data.get('verified'):
                    return email_data['email']
            return None
        except Exception as e:
            logger.error(f"GitHub email fetch failed: {e}")
            return None
    
    def _validate_domain(self, email: str) -> bool:
        """Validate email domain against allowlist"""
        if not email:
            return False
        
        domain = email.split('@')[-1].lower()
        
        if self.enforce_domain_allowlist and self.allowed_domains:
            if domain not in [d.lower() for d in self.allowed_domains if d]:
                logger.warning(f"Domain not allowed: {domain}")
                return False
        
        return True
    
    def authenticate_user(self, provider: str, user_info: Dict) -> Optional[Dict]:
        """Authenticate or create user from OAuth data"""
        if not self.user_repository:
            logger.error("User repository not configured")
            return None
        
        try:
            # Check if user exists
            user = self.user_repository.get_user_by_oauth_id(provider, user_info['provider_id'])
            
            if not user:
                # Create new user
                user = self.user_repository.create_oauth_user(provider, user_info)
                logger.info(f"Created user from {provider}: {user_info.get('email')}")
            else:
                logger.info(f"User authenticated from {provider}: {user_info.get('email')}")
            
            return user
            
        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            return None
    
    def refresh_token(self, provider: str, refresh_token: str) -> Dict:
        """Refresh access token"""
        if provider not in self.providers:
            raise ValueError(f"Unsupported provider: {provider}")
        
        config = self.providers[provider]
        
        data = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
        
        try:
            response = requests.post(
                config['token_url'],
                data=data,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise
    
    def revoke_token(self, provider: str, token: str) -> bool:
        """Revoke token if provider supports it"""
        if provider not in self.providers:
            return False
        
        config = self.providers[provider]
        
        if provider == 'google' and config.get('revoke_url'):
            try:
                response = requests.post(
                    config['revoke_url'],
                    params={'token': token},
                    timeout=10
                )
                return response.status_code == 200
            except Exception as e:
                logger.error(f"Token revocation failed: {e}")
                return False
        
        return False
    
    def get_jwks(self, provider: str) -> Dict:
        """Get JWKS for provider"""
        return self.id_token_validator._get_jwks(provider)

# ============================================================
# FLASK BLUEPRINT
# ============================================================

def create_oauth_blueprint(oauth_service, jwt_handler):
    """Create Flask blueprint for OAuth routes"""
    from flask import Blueprint, request, jsonify, redirect, session, url_for, g
    
    bp = Blueprint('oauth', __name__, url_prefix='/auth')
    
    @bp.route('/<provider>/login')
    def oauth_login(provider):
        """Initiate OAuth login"""
        try:
            redirect_uri = request.args.get('redirect_uri')
            result = oauth_service.get_authorization_url(
                provider,
                redirect_uri=redirect_uri
            )
            return redirect(result['auth_url'])
        except Exception as e:
            logger.error(f"OAuth login failed: {e}")
            return jsonify({'error': str(e)}), 400
    
    @bp.route('/<provider>/callback')
    def oauth_callback(provider):
        """Handle OAuth callback"""
        code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        
        if error:
            logger.error(f"OAuth error: {error}")
            return redirect(f"{oauth_service.base_url}/login?error={error}")
        
        if not code:
            return jsonify({'error': 'No code provided'}), 400
        
        try:
            # Exchange code for tokens
            tokens = oauth_service.exchange_code(provider, code, state)
            
            # Get user info
            user_info = oauth_service.get_user_info(
                provider,
                tokens['access_token'],
                tokens.get('id_payload')
            )
            
            # Authenticate/create user
            user = oauth_service.authenticate_user(provider, user_info)
            
            if not user:
                return jsonify({'error': 'Authentication failed'}), 401
            
            # Create JWT tokens
            jwt_tokens = jwt_handler.create_tokens(
                user_id=user.get('id'),
                organization_id=user.get('organization_id'),
                role=user.get('role', 'user'),
                metadata={'oauth_provider': provider}
            )
            
            # Store tokens in secure cookies
            response = redirect(f"{oauth_service.base_url}/auth/success")
            response.set_cookie(
                'access_token',
                jwt_tokens['access_token'],
                httponly=True,
                secure=os.getenv('SESSION_COOKIE_SECURE', 'true').lower() == 'true',
                samesite='lax',
                max_age=jwt_tokens['expires_in']
            )
            response.set_cookie(
                'refresh_token',
                jwt_tokens['refresh_token'],
                httponly=True,
                secure=os.getenv('SESSION_COOKIE_SECURE', 'true').lower() == 'true',
                samesite='lax',
                max_age=jwt_tokens['refresh_expires_in']
            )
            
            return response
            
        except Exception as e:
            logger.error(f"OAuth callback failed: {e}")
            return redirect(f"{oauth_service.base_url}/login?error={str(e)}")
    
    @bp.route('/success')
    def oauth_success():
        """OAuth success page"""
        return redirect(f"{oauth_service.base_url}/dashboard")
    
    @bp.route('/logout')
    def oauth_logout():
        """Logout and revoke tokens"""
        response = redirect(f"{oauth_service.base_url}/")
        response.set_cookie('access_token', '', expires=0)
        response.set_cookie('refresh_token', '', expires=0)
        return response
    
    return bp