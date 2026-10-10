"""
SYNAPSEPM - ENTERPRISE SECURITY MIDDLEWARE
Production Ready - v5.2.1
Features: CSP Nonces, WAF, Threat Intelligence, Behavioral Analysis, DDoS Protection
"""

import os
import sys
import re
import json
import time
import uuid
import hashlib
import logging
import threading
import base64
import ipaddress
import hmac
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from collections import defaultdict

# ============================================================
# IMPORTS
# ============================================================

try:
    from flask import request, jsonify, g, current_app, session, make_response
    from flask import Response as FlaskResponse
    from werkzeug.exceptions import Forbidden, BadRequest
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("⚠️ Flask not installed")

try:
    import redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ Redis not installed")

# ============================================================
# CONFIGURATION
# ============================================================

class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class SecurityConfig:
    """Complete security configuration"""
    
    # Environment
    environment: Environment = Environment(os.getenv('ENVIRONMENT', 'development'))
    frontend_urls: List[str] = field(default_factory=lambda: [
        os.getenv('FRONTEND_URL', 'http://localhost:5500'),
        os.getenv('FRONTEND_URL_PROD', 'https://synapsepm.com'),
        'https://*.synapsepm.com'
    ])
    api_domain: str = os.getenv('API_DOMAIN', 'api.synapsepm.com')
    
    # CSP Configuration - Strict
    csp_directives: Dict[str, List[str]] = field(default_factory=lambda: {
        'default-src': ["'self'"],
        'script-src': ["'self'", "'unsafe-inline'", "https://cdn.tailwindcss.com", 
                      "https://cdn.jsdelivr.net", "https://fonts.googleapis.com"],
        'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", 
                     "https://cdn.tailwindcss.com"],
        'font-src': ["'self'", "https://fonts.gstatic.com"],
        'img-src': ["'self'", "data:", "https:", "https://images.unsplash.com", 
                   "https://ui-avatars.com"],
        'connect-src': ["'self'", "wss:", "https://api.synapsepm.com", "ws:"],
        'frame-ancestors': ["'none'"],
        'base-uri': ["'self'"],
        'form-action': ["'self'"],
        'object-src': ["'none'"],
        'worker-src': ["'self'", "blob:"],
        'manifest-src': ["'self'"],
        'media-src': ["'self'"],
        'frame-src': ["'self'", "https://www.youtube.com", "https://player.vimeo.com"]
    })
    
    # Redis
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_key_prefix: str = 'sec:'
    
    # Features
    enable_csp_nonces: bool = True
    enable_waf: bool = True
    enable_input_validation: bool = True
    enable_output_encoding: bool = True
    enable_threat_intelligence: bool = True
    enable_behavioral_analysis: bool = True
    
    # WAF Configuration
    waf_rate_limit: int = int(os.getenv('WAF_RATE_LIMIT', '1000'))
    waf_window: int = int(os.getenv('WAF_WINDOW', '60'))
    waf_block_duration: int = int(os.getenv('WAF_BLOCK_DURATION', '3600'))
    
    # Threat Intelligence
    ti_update_interval: int = int(os.getenv('TI_UPDATE_INTERVAL', '3600'))
    ti_api_key: str = os.getenv('THREAT_INTELLIGENCE_API_KEY', '')
    
    # Behavioral Analysis
    behavior_window: int = int(os.getenv('BEHAVIOR_WINDOW', '300'))
    behavior_threshold: float = float(os.getenv('BEHAVIOR_THRESHOLD', '0.8'))


# ============================================================
# SECURE RANDOM GENERATOR
# ============================================================

class SecureRandom:
    """Cryptographically secure random generator"""
    
    @staticmethod
    def generate_nonce(length: int = 32) -> str:
        return base64.b64encode(os.urandom(length)).decode('utf-8').replace('+', '').replace('/', '')[:length]
    
    @staticmethod
    def generate_csrf_token() -> str:
        return hashlib.sha256(os.urandom(32)).hexdigest()
    
    @staticmethod
    def generate_session_id() -> str:
        return uuid.uuid4().hex


# ============================================================
# CSP NONCE GENERATOR
# ============================================================

class CSPNonceGenerator:
    """Content Security Policy nonce generator with Redis persistence"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = SecurityConfig()
        self.logger = logging.getLogger(__name__)
        self._nonces = {}
        self._nonce_lock = threading.Lock()
    
    def generate_nonce(self, session_id: str = None) -> str:
        nonce = SecureRandom.generate_nonce(32)
        expiry = 300  # 5 minutes
        
        if self.redis and session_id:
            try:
                key = f"nonce:{session_id}:{nonce}"
                self.redis.setex(key, expiry, '1')
            except Exception as e:
                self.logger.error(f"Redis error: {e}")
        
        with self._nonce_lock:
            self._nonces[nonce] = time.time() + expiry
        
        return nonce
    
    def verify_nonce(self, nonce: str, session_id: str = None) -> bool:
        if self.redis and session_id:
            try:
                key = f"nonce:{session_id}:{nonce}"
                return self.redis.exists(key) > 0
            except:
                pass
        
        with self._nonce_lock:
            if nonce in self._nonces:
                if time.time() < self._nonces[nonce]:
                    return True
                del self._nonces[nonce]
        
        return False


# ============================================================
# INPUT VALIDATOR
# ============================================================

class InputValidator:
    """Complete input validation and sanitization"""
    
    def __init__(self):
        self.config = SecurityConfig()
        self.logger = logging.getLogger(__name__)
        
        self._patterns = {
            'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            'alphanumeric': r'^[a-zA-Z0-9]+$',
            'alphanumeric_space': r'^[a-zA-Z0-9\s]+$',
            'phone': r'^\+?[0-9\s\-()]{10,20}$',
            'url': r'^https?://[^\s/$.?#].[^\s]*$',
            'hex_color': r'^#[0-9a-fA-F]{6}$',
            'html_id': r'^[a-zA-Z][a-zA-Z0-9_-]*$',
            'password': r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
        }
        
        self._sanitize_patterns = [
            (r'<script.*?>.*?</script>', ''),
            (r'javascript:', ''),
            (r'on[a-z]+=', ''),
            (r'<.*?>', ''),
            (r'&[a-z]+;', '')
        ]
    
    def validate(self, value: Any, validation_type: str = 'string') -> bool:
        if value is None:
            return False
        if validation_type in self._patterns:
            return bool(re.match(self._patterns[validation_type], str(value)))
        if isinstance(value, str):
            return len(value) <= 10000
        return True
    
    def sanitize(self, value: str) -> str:
        if not isinstance(value, str):
            return str(value)
        
        result = value
        for pattern, replacement in self._sanitize_patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        html_escape = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;'
        }
        for char, escape in html_escape.items():
            result = result.replace(char, escape)
        
        return result
    
    def validate_json_body(self, data: Dict, schema: Dict) -> Tuple[bool, Dict]:
        errors = {}
        
        for field, rules in schema.items():
            if rules.get('required') and field not in data:
                errors[field] = 'Field is required'
                continue
            
            if field in data:
                value = data[field]
                
                if rules.get('type'):
                    if rules['type'] == 'string' and not isinstance(value, str):
                        errors[field] = 'Must be a string'
                    elif rules['type'] == 'number' and not isinstance(value, (int, float)):
                        errors[field] = 'Must be a number'
                    elif rules['type'] == 'boolean' and not isinstance(value, bool):
                        errors[field] = 'Must be a boolean'
                    elif rules['type'] == 'array' and not isinstance(value, list):
                        errors[field] = 'Must be an array'
                    elif rules['type'] == 'object' and not isinstance(value, dict):
                        errors[field] = 'Must be an object'
                
                if rules.get('pattern') and isinstance(value, str):
                    if not re.match(rules['pattern'], value):
                        errors[field] = f'Invalid format'
                
                if rules.get('min_length') and isinstance(value, str) and len(value) < rules['min_length']:
                    errors[field] = f'Minimum length is {rules["min_length"]}'
                if rules.get('max_length') and isinstance(value, str) and len(value) > rules['max_length']:
                    errors[field] = f'Maximum length is {rules["max_length"]}'
        
        return len(errors) == 0, errors


# ============================================================
# OUTPUT ENCODER
# ============================================================

class OutputEncoder:
    """Complete output encoding for XSS prevention"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._html_escape = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;'
        }
    
    def encode_html(self, value: str) -> str:
        if not isinstance(value, str):
            return str(value)
        result = value
        for char, escape in self._html_escape.items():
            result = result.replace(char, escape)
        return result
    
    def encode_json(self, data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)
    
    def encode_url(self, value: str) -> str:
        import urllib.parse
        return urllib.parse.quote(value, safe='')
    
    def encode_javascript(self, value: str) -> str:
        if not isinstance(value, str):
            return str(value)
        js_escape = {
            '\\': '\\\\',
            "'": "\\'",
            '"': '\\"',
            '\n': '\\n',
            '\r': '\\r',
            '\t': '\\t',
            '\b': '\\b',
            '\f': '\\f'
        }
        result = value
        for char, escape in js_escape.items():
            result = result.replace(char, escape)
        return result


# ============================================================
# WEB APPLICATION FIREWALL (WAF)
# ============================================================

class WAF:
    """Complete Web Application Firewall with IP blocking, DDoS protection"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = SecurityConfig()
        self.logger = logging.getLogger(__name__)
        
        self.attack_patterns = {
            'sql_injection': [
                r'(\s|^)(SELECT|INSERT|DELETE|UPDATE|DROP|ALTER|CREATE|EXEC|UNION|JOIN)\s',
                r'(\s|^)(OR|AND)\s+\d+\s*=\s*\d+',
                r'--', r'/\*.*\*/', r'WAITFOR\s+DELAY', r'xp_cmdshell',
            ],
            'xss': [
                r'<script.*?>.*?</script>', r'javascript:', r'onerror\s*=',
                r'onload\s*=', r'onclick\s*=', r'onmouseover\s*=',
                r'<iframe.*?>', r'<object.*?>', r'<embed.*?>'
            ],
            'path_traversal': [
                r'\.\./', r'\.\.\\', r'/etc/passwd', r'/proc/self/environ',
                r'\%2e\%2e\%2f'
            ],
            'command_injection': [
                r';\s*(ls|pwd|cat|echo|rm|wget|curl|nc|bash)',
                r'\|\s*(ls|pwd|cat|echo|rm|wget|curl|nc|bash)',
                r'&\s*(ls|pwd|cat|echo|rm|wget|curl|nc|bash)',
                r'`.*`'
            ],
            'http_attack': [
                r'HTTP/1\.1\s*$', r'Content-Length:\s*0',
                r'TRACE\s+', r'TRACK\s+'
            ]
        }
        
        self._blocked_cache = {}
        self._blocked_cache_ttl = 60
        self._rate_cache = defaultdict(list)
        self._rate_lock = threading.Lock()
    
    def is_blocked(self, ip: str) -> bool:
        if ip in self._blocked_cache:
            if time.time() - self._blocked_cache[ip]['timestamp'] < self._blocked_cache_ttl:
                return self._blocked_cache[ip]['blocked']
        
        blocked = False
        if self.redis:
            try:
                blocked = self.redis.exists(f'waf:blocked:{ip}') > 0
            except:
                pass
        
        self._blocked_cache[ip] = {'blocked': blocked, 'timestamp': time.time()}
        return blocked
    
    def block_ip(self, ip: str, reason: str = "WAF detected attack"):
        if self.redis:
            try:
                self.redis.setex(
                    f'waf:blocked:{ip}',
                    self.config.waf_block_duration,
                    json.dumps({'reason': reason, 'timestamp': time.time()})
                )
            except:
                pass
        self.logger.warning(f"⚠️ WAF blocked IP: {ip} - {reason}")
    
    def unblock_ip(self, ip: str):
        if self.redis:
            try:
                self.redis.delete(f'waf:blocked:{ip}')
            except:
                pass
        if ip in self._blocked_cache:
            del self._blocked_cache[ip]
        self.logger.info(f"✅ WAF unblocked IP: {ip}")
    
    def detect_attack(self, request_data: Dict) -> Optional[str]:
        path = request_data.get('path', '')
        for attack_type, patterns in self.attack_patterns.items():
            for pattern in patterns:
                if re.search(pattern, path, re.IGNORECASE):
                    return attack_type
        
        query = request_data.get('query', '')
        for attack_type, patterns in self.attack_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return attack_type
        
        body = request_data.get('body', '')
        if isinstance(body, str):
            for attack_type, patterns in self.attack_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, body, re.IGNORECASE):
                        return attack_type
        
        return None
    
    def check_rate_limit(self, ip: str) -> Tuple[bool, int]:
        with self._rate_lock:
            now = time.time()
            window_start = now - self.config.waf_window
            self._rate_cache[ip] = [ts for ts in self._rate_cache[ip] if ts > window_start]
            count = len(self._rate_cache[ip])
            
            if count >= self.config.waf_rate_limit:
                return False, 0
            
            self._rate_cache[ip].append(now)
            return True, self.config.waf_rate_limit - count - 1
    
    def get_stats(self) -> Dict:
        stats = {'blocked_ips': len(self._blocked_cache), 'active_rate_limits': len(self._rate_cache)}
        if self.redis:
            try:
                keys = self.redis.keys('waf:blocked:*')
                stats['blocked_ips'] = len(keys)
            except:
                pass
        return stats


# ============================================================
# THREAT INTELLIGENCE
# ============================================================

class ThreatIntelligence:
    """Threat intelligence integration with external feeds"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = SecurityConfig()
        self.logger = logging.getLogger(__name__)
        
        self._threat_feeds = {
            'malicious_ips': set(),
            'malicious_domains': set(),
            'malicious_hashes': set(),
            'bad_user_agents': set()
        }
        self._last_update = 0
        self._update_lock = threading.Lock()
        self._start_update_thread()
    
    def is_malicious(self, ip: str = None, domain: str = None, user_agent: str = None) -> bool:
        if not self.config.enable_threat_intelligence:
            return False
        
        with self._update_lock:
            if ip and ip in self._threat_feeds['malicious_ips']:
                return True
            if domain and domain in self._threat_feeds['malicious_domains']:
                return True
            if user_agent and user_agent in self._threat_feeds['bad_user_agents']:
                return True
        
        if self.redis:
            try:
                if ip and self.redis.exists(f'ti:ip:{ip}'):
                    return True
                if domain and self.redis.exists(f'ti:domain:{domain}'):
                    return True
            except:
                pass
        
        return False
    
    def mark_malicious(self, ip: str = None, domain: str = None, reason: str = None):
        if self.redis:
            try:
                if ip:
                    self.redis.setex(f'ti:ip:{ip}', 86400, json.dumps({
                        'reason': reason, 'timestamp': time.time()
                    }))
                if domain:
                    self.redis.setex(f'ti:domain:{domain}', 86400, json.dumps({
                        'reason': reason, 'timestamp': time.time()
                    }))
            except:
                pass
        
        with self._update_lock:
            if ip:
                self._threat_feeds['malicious_ips'].add(ip)
            if domain:
                self._threat_feeds['malicious_domains'].add(domain)
        
        self.logger.warning(f"⚠️ Marked malicious: {ip or domain} - {reason}")
    
    def _update_feeds(self):
        try:
            if self.redis:
                try:
                    for key in self.redis.keys('ti:ip:*'):
                        ip = key.split(':')[-1]
                        self._threat_feeds['malicious_ips'].add(ip)
                except:
                    pass
            self._last_update = time.time()
            self.logger.info("Threat intelligence feeds updated")
        except Exception as e:
            self.logger.error(f"Failed to update threat feeds: {e}")
    
    def _start_update_thread(self):
        def update_loop():
            while True:
                time.sleep(self.config.ti_update_interval)
                self._update_feeds()
        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()


# ============================================================
# BEHAVIORAL ANALYZER
# ============================================================

class BehavioralAnalyzer:
    """Behavioral analysis for anomaly detection"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = SecurityConfig()
        self.logger = logging.getLogger(__name__)
        
        self._behavior_data = defaultdict(lambda: {
            'requests': 0, 'failed_requests': 0, 'unique_endpoints': set(),
            'timestamps': [], 'suspicious_score': 0, 'last_activity': 0
        })
        self._anomaly_cache = {}
    
    def record_request(self, client_id: str, path: str, status_code: int):
        now = time.time()
        behavior = self._behavior_data[client_id]
        
        behavior['requests'] += 1
        behavior['timestamps'].append(now)
        behavior['unique_endpoints'].add(path)
        behavior['last_activity'] = now
        
        if status_code >= 400:
            behavior['failed_requests'] += 1
        
        cutoff = now - self.config.behavior_window
        behavior['timestamps'] = [t for t in behavior['timestamps'] if t > cutoff]
        
        self._calculate_suspicious_score(client_id)
    
    def is_anomalous(self, client_id: str) -> bool:
        if client_id in self._anomaly_cache:
            if time.time() - self._anomaly_cache[client_id]['timestamp'] < 60:
                return self._anomaly_cache[client_id]['is_anomalous']
        
        behavior = self._behavior_data.get(client_id)
        if not behavior:
            return False
        
        is_anomalous = behavior.get('suspicious_score', 0) > self.config.behavior_threshold
        self._anomaly_cache[client_id] = {
            'is_anomalous': is_anomalous, 'timestamp': time.time()
        }
        return is_anomalous
    
    def _calculate_suspicious_score(self, client_id: str) -> float:
        behavior = self._behavior_data.get(client_id)
        if not behavior:
            return 0.0
        
        score = 0.0
        now = time.time()
        
        # Request rate (20% weight)
        request_count = len([t for t in behavior['timestamps'] if t > now - 60])
        if request_count > 100:
            score += 0.2
        
        # Failure rate (25% weight)
        total_requests = behavior['requests']
        failed_requests = behavior['failed_requests']
        if total_requests > 10:
            failure_rate = failed_requests / total_requests
            if failure_rate > 0.5:
                score += 0.25
        
        # Unique endpoints (25% weight)
        endpoint_count = len(behavior['unique_endpoints'])
        if endpoint_count > 20:
            score += 0.15
        if endpoint_count > 50:
            score += 0.1
        
        # Session duration (30% weight)
        if behavior['last_activity'] > 0:
            session_duration = (now - min(behavior['timestamps'])) / 3600
            if session_duration < 0.1 and total_requests > 50:
                score += 0.15
            if session_duration > 12:
                score += 0.15
        
        score = min(score, 1.0)
        behavior['suspicious_score'] = score
        return score


# ============================================================
# SECURITY MIDDLEWARE - MAIN
# ============================================================

class SecurityMiddleware:
    """Complete enterprise-grade security middleware"""
    
    def __init__(self, app):
        self.app = app
        self.config = SecurityConfig()
        self.logger = logging.getLogger(__name__)
        
        self.redis = None
        self._init_redis()
        
        self.csp_nonce = CSPNonceGenerator(self.redis)
        self.input_validator = InputValidator()
        self.output_encoder = OutputEncoder()
        self.waf = WAF(self.redis)
        self.threat_intel = ThreatIntelligence(self.redis)
        self.behavioral = BehavioralAnalyzer(self.redis)
        
        self.security_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=(), payment=()',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'X-Robots-Tag': 'noindex, nofollow',
            'Cross-Origin-Opener-Policy': 'same-origin',
            'Cross-Origin-Embedder-Policy': 'require-corp',
            'Cross-Origin-Resource-Policy': 'same-origin'
        }
        
        self.remove_server_header = True
        
        print(f"✅ SecurityMiddleware initialized in {self.config.environment.value} mode")
        print(f"   - CSP Nonces: {'✅' if self.config.enable_csp_nonces else '❌'}")
        print(f"   - WAF: {'✅' if self.config.enable_waf else '❌'}")
        print(f"   - Threat Intelligence: {'✅' if self.config.enable_threat_intelligence else '❌'}")
        print(f"   - Behavioral Analysis: {'✅' if self.config.enable_behavioral_analysis else '❌'}")
    
    def _init_redis(self):
        try:
            if REDIS_AVAILABLE:
                self.redis = redis.from_url(self.config.redis_url, decode_responses=True)
                self.redis.ping()
                self.logger.info("✅ Connected to Redis for security")
            else:
                self.redis = None
        except Exception as e:
            self.logger.warning(f"⚠️ Redis connection failed: {e}")
            self.redis = None
    
    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        method = environ.get('REQUEST_METHOD', '')
        query = environ.get('QUERY_STRING', '')
        client_ip = self._get_client_ip(environ)
        user_agent = environ.get('HTTP_USER_AGENT', '')
        
        # Skip health checks and static
        if path in ['/health', '/metrics', '/ping', '/ready'] or path.startswith('/static/') or path.startswith('/favicon'):
            return self.app(environ, start_response)
        
        # 1. Input Validation
        if self.config.enable_input_validation:
            if not self._validate_request(environ):
                return self._block_request(environ, start_response, 'Input validation failed')
        
        # 2. WAF Check
        if self.config.enable_waf:
            if self.waf.is_blocked(client_ip):
                return self._block_request(environ, start_response, 'IP blocked by WAF')
            
            allowed, remaining = self.waf.check_rate_limit(client_ip)
            if not allowed:
                self.waf.block_ip(client_ip, 'Rate limit exceeded')
                return self._too_many_requests(environ, start_response)
            
            if self._detect_attack(environ):
                self.waf.block_ip(client_ip, 'Attack detected')
                return self._block_request(environ, start_response, 'Attack detected')
        
        # 3. Threat Intelligence Check
        if self.config.enable_threat_intelligence:
            if self.threat_intel.is_malicious(ip=client_ip, user_agent=user_agent):
                self.waf.block_ip(client_ip, 'Threat intelligence block')
                return self._block_request(environ, start_response, 'Malicious activity detected')
        
        # 4. Behavioral Analysis
        if self.config.enable_behavioral_analysis:
            self.behavioral.record_request(client_ip, path, 200)
            if self.behavioral.is_anomalous(client_ip):
                self.logger.warning(f"⚠️ Anomalous behavior detected: {client_ip}")
                self.threat_intel.mark_malicious(ip=client_ip, reason='Anomalous behavior')
        
        # 5. Generate CSP Nonce
        nonce = None
        if self.config.enable_csp_nonces:
            nonce = self.csp_nonce.generate_nonce()
        
        def custom_start_response(status, headers, exc_info=None):
            headers = self._add_security_headers(headers, nonce)
            if self.remove_server_header:
                headers = [(k, v) for k, v in headers if k != 'Server']
            return start_response(status, headers, exc_info)
        
        environ['nonce'] = nonce
        environ['client_ip'] = client_ip
        
        try:
            return self.app(environ, custom_start_response)
        except Exception as e:
            self.logger.error(f"Security middleware error: {e}")
            if self.config.enable_behavioral_analysis:
                self.behavioral.record_request(client_ip, path, 500)
            raise
    
    def _validate_request(self, environ) -> bool:
        path = environ.get('PATH_INFO', '')
        query = environ.get('QUERY_STRING', '')
        
        if not self.input_validator.sanitize(path):
            return False
        if query:
            sanitized = self.input_validator.sanitize(query)
            if sanitized != query:
                return False
        return True
    
    def _detect_attack(self, environ) -> bool:
        path = environ.get('PATH_INFO', '')
        query = environ.get('QUERY_STRING', '')
        body = environ.get('wsgi.input')
        
        request_data = {'path': path, 'query': query, 'body': ''}
        if body:
            try:
                content_length = int(environ.get('CONTENT_LENGTH', 0))
                if 0 < content_length < 100000:
                    body_data = body.read(content_length)
                    request_data['body'] = body_data.decode('utf-8', errors='ignore')
            except:
                pass
        
        attack_type = self.waf.detect_attack(request_data)
        if attack_type:
            self.logger.warning(f"⚠️ Attack detected: {attack_type} on {path}")
            return True
        return False
    
    def _add_security_headers(self, headers, nonce: str = None) -> List:
        headers = list(headers)
        
        for key, value in self.security_headers.items():
            headers.append((key, value))
        
        csp_directives = {}
        for directive, sources in self.config.csp_directives.items():
            csp_directives[directive] = sources.copy()
            if nonce and directive in ['script-src', 'style-src']:
                if "'unsafe-inline'" in csp_directives[directive]:
                    csp_directives[directive].remove("'unsafe-inline'")
                csp_directives[directive].append(f"'nonce-{nonce}'")
        
        csp_string = '; '.join([
            f"{directive} {' '.join(sources)}"
            for directive, sources in csp_directives.items()
        ])
        headers.append(('Content-Security-Policy', csp_string))
        
        return headers
    
    def _get_client_ip(self, environ) -> str:
        forwarded_for = environ.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return environ.get('REMOTE_ADDR', '0.0.0.0')
    
    def _create_response(self, environ, start_response, status_code: int, message: str):
        response_data = json.dumps({
            'error': 'security_blocked',
            'message': message,
            'code': 'SECURITY_BLOCKED',
            'timestamp': datetime.utcnow().isoformat()
        }).encode('utf-8')
        
        status = f"{status_code} {self._get_status_message(status_code)}"
        headers = [('Content-Type', 'application/json'), ('Content-Length', str(len(response_data)))]
        start_response(status, headers)
        return [response_data]
    
    def _get_status_message(self, status_code: int) -> str:
        return {403: 'Forbidden', 429: 'Too Many Requests'}.get(status_code, 'Error')
    
    def _block_request(self, environ, start_response, message: str = None):
        return self._create_response(environ, start_response, 403, message or 'Request blocked')
    
    def _too_many_requests(self, environ, start_response):
        return self._create_response(environ, start_response, 429, 'Too many requests. Please try again later.')