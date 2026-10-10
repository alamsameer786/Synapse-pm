"""
SYNAPSEPM - RATE LIMITING MIDDLEWARE
Production Ready - v5.2.1
Features: Redis Cluster, Adaptive Limits, DDoS Protection, Monitoring
"""

import os
import sys
import json
import time
import hashlib
import uuid
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from functools import wraps

# ============================================================
# IMPORTS
# ============================================================

try:
    import redis
    from redis.exceptions import RedisError, ConnectionError, TimeoutError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ Redis not installed")

try:
    from flask import request, jsonify, g, current_app
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# ============================================================
# CONFIGURATION
# ============================================================

class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class RateLimiterConfig:
    """Complete rate limiter configuration"""
    
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_cluster: bool = os.getenv('REDIS_CLUSTER', 'false').lower() == 'true'
    redis_socket_timeout: int = int(os.getenv('REDIS_SOCKET_TIMEOUT', '5'))
    redis_max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '50'))
    redis_key_prefix: str = 'rl:'
    
    default_limits: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        'anonymous': (100, 3600),
        'authenticated': (1000, 3600),
        'premium': (10000, 3600),
        'enterprise': (50000, 3600),
        'api_key': (5000, 3600),
        'service_account': (100000, 3600)
    })
    
    endpoint_limits: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        '/api/v1/auth/login': (5, 300),
        '/api/v1/auth/register': (3, 3600),
        '/api/v1/auth/forgot-password': (3, 3600),
        '/api/v1/predict': (100, 60),
        '/api/v1/predict/batch': (10, 60),
        '/api/v1/machines': (200, 60),
        '/api/v1/alerts': (200, 60),
        '/api/v1/reports': (50, 60),
        '/api/v1/admin/': (500, 3600),
        '/api/v1/webhooks/': (1000, 60),
        '/api/v1/payments/checkout': (10, 300),
        '/api/v1/downloads/': (50, 3600),
    })
    
    environment: Environment = Environment(os.getenv('ENVIRONMENT', 'development'))
    enable_monitoring: bool = os.getenv('ENABLE_MONITORING', 'true').lower() == 'true'
    enable_adaptive: bool = os.getenv('ENABLE_ADAPTIVE', 'true').lower() == 'true'
    
    enable_ddos_protection: bool = True
    ddos_threshold: int = int(os.getenv('DDOS_THRESHOLD', '5000'))
    ddos_ban_duration: int = int(os.getenv('DDOS_BAN_DURATION', '3600'))
    
    max_in_memory_keys: int = int(os.getenv('MAX_IN_MEMORY_KEYS', '10000'))
    memory_cleanup_interval: int = int(os.getenv('MEMORY_CLEANUP_INTERVAL', '300'))


# ============================================================
# ADAPTIVE ENGINE
# ============================================================

class AdaptiveEngine:
    """Adaptive rate limiting based on load, time, and behavior"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = RateLimiterConfig()
        self.logger = logging.getLogger(__name__)
        self._history_cache = {}
        self._adaptation_lock = threading.Lock()
    
    def calculate_limit(self, client_id: str, base_limit: int, window: int) -> int:
        if not self.config.enable_adaptive:
            return base_limit
        
        try:
            load_factor = self._get_load_factor()
            time_factor = self._get_time_factor()
            history_factor = self._get_history_factor(client_id)
            behavior_factor = self._get_behavior_factor(client_id)
            
            adaptive_limit = int(base_limit * load_factor * time_factor * history_factor * behavior_factor)
            final_limit = max(int(base_limit * 0.1), min(adaptive_limit, int(base_limit * 2)))
            
            self._log_adaptation(client_id, base_limit, final_limit, {
                'load': load_factor, 'time': time_factor,
                'history': history_factor, 'behavior': behavior_factor
            })
            
            return final_limit
        except Exception as e:
            self.logger.error(f"Adaptive calculation failed: {e}")
            return base_limit
    
    def _get_load_factor(self) -> float:
        try:
            if self.redis:
                load = float(self.redis.get('system:load') or 0.5)
                if load > 0.8:
                    return 0.5
                elif load > 0.6:
                    return 0.75
            return 1.0
        except:
            return 0.8
    
    def _get_time_factor(self) -> float:
        hour = datetime.now().hour
        if 9 <= hour <= 17:
            return 1.2
        elif hour >= 22 or hour <= 6:
            return 0.7
        return 1.0
    
    def _get_history_factor(self, client_id: str) -> float:
        try:
            history = self._history_cache.get(client_id, {})
            avg_usage = history.get('avg_usage', 100)
            peak_usage = history.get('peak_usage', 200)
            if avg_usage > 0 and peak_usage > 0:
                ratio = avg_usage / peak_usage
                if ratio < 0.3:
                    return 0.8
                elif ratio > 0.8:
                    return 1.1
            return 1.0
        except:
            return 1.0
    
    def _get_behavior_factor(self, client_id: str) -> float:
        try:
            if self.redis:
                violations = int(self.redis.get(f'violations:{client_id}') or 0)
                if violations > 10:
                    return 0.5
                elif violations > 5:
                    return 0.7
                elif violations > 2:
                    return 0.9
            return 1.0
        except:
            return 1.0
    
    def record_violation(self, client_id: str):
        try:
            if self.redis:
                self.redis.incr(f'violations:{client_id}')
                self.redis.expire(f'violations:{client_id}', 86400)
        except:
            pass
    
    def update_history(self, client_id: str, usage: int):
        try:
            with self._adaptation_lock:
                history = self._history_cache.get(client_id, {})
                history['avg_usage'] = (history.get('avg_usage', 0) * 0.7 + usage * 0.3)
                history['peak_usage'] = max(history.get('peak_usage', 0), usage)
                history['last_updated'] = time.time()
                self._history_cache[client_id] = history
        except:
            pass
    
    def _log_adaptation(self, client_id: str, base_limit: int, new_limit: int, factors: Dict):
        if self.config.enable_monitoring:
            self.logger.debug(f"Adaptive limit for {client_id}: {base_limit} -> {new_limit}")


# ============================================================
# DDOS PROTECTION
# ============================================================

class DDOSProtection:
    """DDoS protection with automatic IP blocking"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = RateLimiterConfig()
        self.logger = logging.getLogger(__name__)
        self._blocked_cache = {}
        self._blocked_cache_ttl = 60
    
    def is_blocked(self, client_id: str) -> bool:
        if not self.config.enable_ddos_protection:
            return False
        
        if client_id in self._blocked_cache:
            if time.time() - self._blocked_cache[client_id]['timestamp'] < self._blocked_cache_ttl:
                return self._blocked_cache[client_id]['blocked']
        
        blocked = False
        if self.redis:
            try:
                blocked = self.redis.get(f'blocked:{client_id}') is not None
            except:
                pass
        
        self._blocked_cache[client_id] = {'blocked': blocked, 'timestamp': time.time()}
        return blocked
    
    def block_client(self, client_id: str, reason: str = "DDoS detected"):
        try:
            if self.redis:
                self.redis.setex(
                    f'blocked:{client_id}',
                    self.config.ddos_ban_duration,
                    json.dumps({'reason': reason, 'timestamp': time.time(), 'ip': client_id})
                )
            self.logger.warning(f"🚨 Blocked client: {client_id} - {reason}")
        except Exception as e:
            self.logger.error(f"Failed to block client: {e}")
    
    def unblock_client(self, client_id: str):
        try:
            if self.redis:
                self.redis.delete(f'blocked:{client_id}')
            self.logger.info(f"✅ Unblocked client: {client_id}")
        except Exception as e:
            self.logger.error(f"Failed to unblock client: {e}")
    
    def detect_ddos(self, client_id: str, current_rate: int, threshold: int) -> bool:
        if not self.config.enable_ddos_protection:
            return False
        if current_rate > threshold:
            self.block_client(client_id, f"Exceeded DDoS threshold: {current_rate} req/min")
            return True
        return False


# ============================================================
# MONITORING ENGINE
# ============================================================

class MonitoringEngine:
    """Real-time monitoring and alerting"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.config = RateLimiterConfig()
        self.logger = logging.getLogger(__name__)
        
        self.alert_thresholds = {
            'rate_limit_violations': 50,
            'ddos_detected': 1,
            'redis_errors': 10,
            'high_usage_percent': 80
        }
        self._alerts_sent = {}
    
    def record_metric(self, metric_name: str, value: Any, tags: Dict = None):
        try:
            if self.redis:
                key = f'metric:{metric_name}:{time.time()}'
                self.redis.setex(key, 3600, json.dumps({
                    'value': value, 'tags': tags or {}, 'timestamp': time.time()
                }))
        except:
            pass
    
    def check_alerts(self, client_id: str, usage: int, limit: int, window: int):
        if not self.config.enable_monitoring:
            return
        
        usage_percent = (usage / limit) * 100
        if usage_percent > self.alert_thresholds['high_usage_percent']:
            self._send_alert('high_usage', f"Client {client_id} using {usage_percent:.1f}% of limit",
                           {'client': client_id, 'usage': usage, 'limit': limit})
        
        if usage > self.config.ddos_threshold:
            self._send_alert('ddos_detected', f"Potential DDoS from {client_id}: {usage} req/min",
                           {'client': client_id, 'rate': usage})
    
    def _send_alert(self, alert_type: str, message: str, details: Dict):
        alert_key = f"alert:{alert_type}:{details.get('client', 'unknown')}"
        if alert_key in self._alerts_sent:
            if time.time() - self._alerts_sent[alert_key] < 300:
                return
        
        self._alerts_sent[alert_key] = time.time()
        self.logger.warning(f"🔔 ALERT [{alert_type}]: {message}")
        
        if self.redis:
            try:
                self.redis.lpush('alerts:queue', json.dumps({
                    'type': alert_type, 'message': message,
                    'details': details, 'timestamp': time.time()
                }))
            except:
                pass


# ============================================================
# DISTRIBUTED RATE LIMITER - MAIN
# ============================================================

class DistributedRateLimiter:
    """Complete distributed rate limiter with Redis Cluster support"""
    
    def __init__(self, app=None):
        self.config = RateLimiterConfig()
        self.logger = logging.getLogger(__name__)
        
        self.redis = None
        self._init_redis()
        
        self.adaptive_engine = AdaptiveEngine(self.redis)
        self.ddos_protection = DDOSProtection(self.redis)
        self.monitoring = MonitoringEngine(self.redis)
        
        self._memory_store = defaultdict(list)
        self._memory_lock = threading.Lock()
        
        self._stats = {
            'total_requests': 0, 'allowed_requests': 0, 'blocked_requests': 0,
            'rate_limited_requests': 0, 'ddos_blocks': 0, 'redis_errors': 0
        }
        self._stats_lock = threading.Lock()
        
        self._start_cleanup_thread()
    
    def _init_redis(self):
        try:
            if REDIS_AVAILABLE:
                if self.config.redis_cluster:
                    from redis.cluster import RedisCluster
                    self.redis = RedisCluster(
                        host=self.config.redis_url,
                        socket_timeout=self.config.redis_socket_timeout,
                        max_connections=self.config.redis_max_connections
                    )
                else:
                    self.redis = redis.from_url(
                        self.config.redis_url,
                        socket_timeout=self.config.redis_socket_timeout,
                        max_connections=self.config.redis_max_connections
                    )
                self.redis.ping()
                self.logger.info("✅ Connected to Redis for rate limiting")
            else:
                self.redis = None
        except Exception as e:
            self.logger.warning(f"⚠️ Redis connection failed: {e}")
            self.redis = None
    
    def check_rate_limit(self, client_id: str, path: str, tier: str = 'authenticated') -> Tuple[bool, Dict]:
        self._update_stats('total_requests')
        
        if self.ddos_protection.is_blocked(client_id):
            self._update_stats('ddos_blocks')
            return False, {
                'X-RateLimit-Limit': '0', 'X-RateLimit-Remaining': '0',
                'X-RateLimit-Reset': str(int(time.time() + 3600)),
                'X-RateLimit-Reason': 'Blocked by DDoS protection'
            }
        
        base_limit, window = self._get_limit_for_path(path, tier)
        limit = self.adaptive_engine.calculate_limit(client_id, base_limit, window)
        
        if self.redis:
            allowed, headers = self._check_redis(client_id, limit, window)
        else:
            allowed, headers = self._check_memory(client_id, limit, window)
        
        if allowed:
            self._update_stats('allowed_requests')
        else:
            self._update_stats('rate_limited_requests')
            self.adaptive_engine.record_violation(client_id)
        
        if not allowed:
            self.monitoring.check_alerts(client_id, limit, limit, window)
        
        usage = int(headers.get('X-RateLimit-Remaining', 0))
        self.adaptive_engine.update_history(client_id, limit - usage)
        
        return allowed, headers
    
    def _get_limit_for_path(self, path: str, tier: str) -> Tuple[int, int]:
        for endpoint, (limit, window) in self.config.endpoint_limits.items():
            if path.startswith(endpoint):
                return limit, window
        return self.config.default_limits.get(tier, self.config.default_limits['authenticated'])
    
    def _check_redis(self, client_id: str, limit: int, window: int) -> Tuple[bool, Dict]:
        try:
            key = f"{self.config.redis_key_prefix}{client_id}"
            now = time.time()
            window_start = now - window
            
            lua_script = """
                local key = KEYS[1]
                local now = tonumber(ARGV[1])
                local window_start = tonumber(ARGV[2])
                local limit = tonumber(ARGV[3])
                local window = tonumber(ARGV[4])
                
                redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
                local count = redis.call('ZCARD', key)
                
                if count >= limit then
                    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
                    local reset_time = window_start + window
                    if next(oldest) then
                        reset_time = tonumber(oldest[2]) + window
                    end
                    return {0, reset_time, count}
                end
                
                redis.call('ZADD', key, now, now)
                redis.call('EXPIRE', key, window)
                return {1, now + window, count + 1}
            """
            
            result = self.redis.eval(lua_script, 1, key, now, window_start, limit, window)
            
            allowed = result[0] == 1
            reset_time = int(result[1])
            current_count = int(result[2])
            
            headers = {
                'X-RateLimit-Limit': str(limit),
                'X-RateLimit-Remaining': str(limit - current_count if allowed else 0),
                'X-RateLimit-Reset': str(reset_time)
            }
            return allowed, headers
            
        except RedisError as e:
            self.logger.error(f"Redis error: {e}")
            self._update_stats('redis_errors')
            return self._check_memory(client_id, limit, window)
    
    def _check_memory(self, client_id: str, limit: int, window: int) -> Tuple[bool, Dict]:
        with self._memory_lock:
            now = time.time()
            window_start = now - window
            self._memory_store[client_id] = [ts for ts in self._memory_store[client_id] if ts > window_start]
            current_count = len(self._memory_store[client_id])
            
            if current_count >= limit:
                oldest = min(self._memory_store[client_id]) if self._memory_store[client_id] else now
                reset_time = int(oldest + window)
                return False, {
                    'X-RateLimit-Limit': str(limit), 'X-RateLimit-Remaining': '0',
                    'X-RateLimit-Reset': str(reset_time)
                }
            
            self._memory_store[client_id].append(now)
            return True, {
                'X-RateLimit-Limit': str(limit),
                'X-RateLimit-Remaining': str(limit - current_count - 1),
                'X-RateLimit-Reset': int(now + window)
            }
    
    def _update_stats(self, stat_key: str):
        with self._stats_lock:
            if stat_key in self._stats:
                self._stats[stat_key] += 1
    
    def get_stats(self) -> Dict:
        with self._stats_lock:
            return self._stats.copy()
    
    def _start_cleanup_thread(self):
        def cleanup():
            while True:
                time.sleep(self.config.memory_cleanup_interval)
                try:
                    with self._memory_lock:
                        now = time.time()
                        for client_id in list(self._memory_store.keys()):
                            self._memory_store[client_id] = [
                                ts for ts in self._memory_store[client_id]
                                if ts > now - 3600
                            ]
                            if len(self._memory_store[client_id]) == 0:
                                del self._memory_store[client_id]
                except Exception as e:
                    self.logger.error(f"Cleanup error: {e}")
        
        thread = threading.Thread(target=cleanup, daemon=True)
        thread.start()


# ============================================================
# FLASK MIDDLEWARE
# ============================================================

class RateLimiterMiddleware:
    """Flask middleware for rate limiting"""
    
    def __init__(self, app):
        self.app = app
        self.config = RateLimiterConfig()
        self.limiter = DistributedRateLimiter()
        
        app.config['rate_limiter'] = self.limiter
        app.before_request(self._before_request)
    
    def _before_request(self):
        if request.path in ['/health', '/metrics', '/ping', '/ready']:
            return
        if request.path.startswith('/static/') or request.path.startswith('/favicon'):
            return
        
        client_id = self._get_client_id()
        tier = self._get_user_tier()
        path = request.path
        
        allowed, headers = self.limiter.check_rate_limit(client_id, path, tier)
        
        if not allowed:
            response = jsonify({
                'error': 'rate_limit_exceeded',
                'message': 'Too many requests. Please try again later.',
                'retry_after': headers.get('X-RateLimit-Reset', 60)
            })
            response.status_code = 429
            for key, value in headers.items():
                response.headers[key] = value
            return response
    
    def _get_client_id(self) -> str:
        api_key = request.headers.get('X-API-Key')
        if api_key:
            return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
        if hasattr(g, 'user_id'):
            return f"user:{g.user_id}"
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
        return f"ip:{ip}"
    
    def _get_user_tier(self) -> str:
        if hasattr(g, 'user_tier'):
            return g.user_tier
        if hasattr(g, 'user_id'):
            return 'authenticated'
        if request.headers.get('X-API-Key'):
            return 'api_key'
        return 'anonymous'


# ============================================================
# DECORATOR
# ============================================================

def rate_limit(limit: int = None, window: int = None):
    """Decorator for Flask route rate limiting"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            limiter = getattr(g, 'rate_limiter', None)
            if not limiter:
                limiter = current_app.config.get('rate_limiter')
                if not limiter:
                    return f(*args, **kwargs)
            
            client_id = _get_client_id()
            tier = _get_user_tier()
            path = request.path
            
            if limit and window:
                allowed, headers = limiter._check_redis(client_id, limit, window)
            else:
                allowed, headers = limiter.check_rate_limit(client_id, path, tier)
            
            if not allowed:
                response = jsonify({
                    'error': 'rate_limit_exceeded',
                    'message': 'Too many requests. Please try again later.',
                    'retry_after': headers.get('X-RateLimit-Reset', 60)
                })
                response.status_code = 429
                for key, value in headers.items():
                    response.headers[key] = value
                return response
            
            response = f(*args, **kwargs)
            for key, value in headers.items():
                if hasattr(response, 'headers'):
                    response.headers[key] = value
            return response
        return decorated_function
    return decorator


def _get_client_id() -> str:
    api_key = request.headers.get('X-API-Key')
    if api_key:
        return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
    if hasattr(g, 'user_id'):
        return f"user:{g.user_id}"
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
    return f"ip:{ip}"


def _get_user_tier() -> str:
    if hasattr(g, 'user_tier'):
        return g.user_tier
    if hasattr(g, 'user_id'):
        return 'authenticated'
    if request.headers.get('X-API-Key'):
        return 'api_key'
    return 'anonymous'