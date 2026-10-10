// ============================================================
// AUTH.JS — SYNAPSEPM v10.0.0
// ============================================================
// Frontend auth + API client. Aligned with backend v18.0.0.
//
// WHAT'S NEW IN v10.0.0 (over v9.2.0):
//   ✅ Dataset prediction now supports machine_type without a
//      pre-connected machine (calls /predictions/predict-dataset
//      with machine_type).
//   ✅ Alert CRUD aliases: acknowledgeAlert, escalateAlert added.
//   ✅ Alerts marked-read bulk endpoint wired.
//   ✅ Prediction status normalisation (healthy/warning/critical).
//   ✅ Single-flight refresh proven across concurrent 401s.
//   ✅ 401 → refresh → retry once → logout only on refresh fail.
//   ✅ FormData uploads inherit 401-refresh (no CT for multipart).
//   ✅ Blob downloads (reports, releases) with 401-refresh.
//   ✅ WS reconnect stops on 1008 (auth failure).
//   ✅ synapse:token-refreshed event for page-level WS rebuild.
//   ✅ Safe same-origin redirect whitelist (no open redirects).
//   ✅ Idempotent session dedupe by id.
//   ✅ Client rate guard: 200/min (was 120/min — dashboards
//      were tripping it).
//   ✅ authFetch / authDownload exposed for pages that want raw
//      fetch instead of the JSON wrapper.
//   ✅ All legacy storage keys still read + cleared.
// ============================================================

(function (global) {
    'use strict';

    // ============================================================
    // SAFE ENV ACCESSOR
    // ============================================================

    const ENV = (typeof window !== 'undefined' && window.ENV) ? window.ENV : {};

    function _normalizeBase(base) {
        if (!base || typeof base !== 'string') return '';
        let b = base.trim();
        b = b.replace(/\/+$/, '');
        return b;
    }

    function detectApiBase() {
        if (ENV.API_URL && typeof ENV.API_URL === 'string') {
            let b = _normalizeBase(ENV.API_URL);
            b = b.replace(/\/api\/v1$/, '').replace(/\/api$/, '');
            return b;
        }
        if (typeof window !== 'undefined' && window.location && window.location.origin) {
            return _normalizeBase(window.location.origin);
        }
        return 'http://localhost:5000';
    }

    function detectWsUrl() {
        if (ENV.WS_URL && typeof ENV.WS_URL === 'string') return ENV.WS_URL;
        if (typeof window !== 'undefined' && window.location) {
            const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${proto}//${window.location.host}/ws`;
        }
        return 'ws://localhost:5000/ws';
    }

    /**
     * Join the API base with an endpoint path, avoiding the classic
     * `/api/v1/api/v1/...` bug.
     */
    function _joinUrl(base, endpoint) {
        if (!endpoint) return base;
        if (/^https?:\/\//i.test(endpoint)) return endpoint;

        let b = _normalizeBase(base);
        let ep = String(endpoint);

        if (ep.charAt(0) !== '/') ep = '/' + ep;

        const baseHasApiV1 = /\/api\/v1$/i.test(b);
        const baseHasApi    = !baseHasApiV1 && /\/api$/i.test(b);

        if (baseHasApiV1 && ep.startsWith('/api/v1/')) {
            ep = ep.slice('/api/v1'.length);
        } else if (baseHasApi && ep.startsWith('/api/')) {
            ep = ep.slice('/api'.length);
        }

        if (!ep) return b;
        if (ep.charAt(0) !== '/') ep = '/' + ep;
        return b + ep;
    }

    // ============================================================
    // CONFIG — PUBLIC VALUES ONLY
    // ============================================================

    const AUTH_CONFIG = {
        API_BASE_URL: detectApiBase(),
        WS_URL: detectWsUrl(),

        MODEL_BASE_PATH: ENV.MODEL_PATH || './models',

        MAX_LOGIN_ATTEMPTS: 5,
        LOCKOUT_DURATION: 15 * 60 * 1000,
        PASSWORD_EXPIRY_DAYS: 90,
        SESSION_TIMEOUT: 24 * 60 * 60 * 1000,
        IDLE_TIMEOUT: 30 * 60 * 1000,
        BACKUP_CODES_COUNT: 10,

        // Client-side guard — generous for dashboards
        RATE_LIMIT_WINDOW: 60 * 1000,
        RATE_LIMIT_MAX: 300,

        // Storage keys
        TOKEN_KEY:    'synapse_token',
        REFRESH_KEY:  'synapse_refresh',
        USER_KEY:     'synapse_user',
        TENANT_KEY:   'synapse_tenant',
        MFA_KEY:      'synapse_mfa',
        SESSION_KEY:  'synapse_session',
        REDIRECT_KEY: 'synapse_redirect',
        OAUTH_PROVIDER: 'oauth_provider',
        DEVICE_ID_KEY:  'synapse_device_id',
        SESSIONS_KEY:   'synapse_sessions',

        LEGACY_ACCESS_KEYS:  ['token', 'auth_token', 'access_token'],
        LEGACY_REFRESH_KEYS: ['refresh_token', 'synapse_refresh_token'],
        LEGACY_USER_KEYS:    ['user'],
        LEGACY_TENANT_KEYS:  ['organization'],

        ADMIN_TOKEN_KEY: 'synapse_admin_token',
        ADMIN_USER_KEY:  'synapse_admin_user',

        TOKEN_EXPIRY_LEEWAY_SECONDS: 30,

        ROLES: {
            SUPER_ADMIN: 'super_admin',
            ADMIN:       'admin',
            ORG_ADMIN:   'org_admin',
            MANAGER:     'manager',
            ENGINEER:    'engineer',
            OPERATOR:    'operator',
            VIEWER:      'viewer',
        },

        FEATURES: {
            AI_PREDICTIONS:   'ai_predictions',
            REAL_TIME:        'real_time',
            MFA:              'mfa',
            SSO:              'sso',
            API_ACCESS:       'api_access',
            AUDIT_LOGS:       'audit_logs',
            DATA_EXPORT:      'data_export',
            CUSTOM_REPORTS:   'custom_reports',
            TEAM_WORKSPACE:   'team_workspace',
            PRIORITY_SUPPORT: 'priority_support',
        },
    };

    console.log('🔧 SynapsePM auth.js v10.0.0');
    console.log('   API:', AUTH_CONFIG.API_BASE_URL);
    console.log('   WS :', AUTH_CONFIG.WS_URL);

    // ============================================================
    // JWT HELPERS
    // ============================================================

    function decodeJwt(token) {
        if (!token || typeof token !== 'string') return null;
        try {
            const parts = token.split('.');
            if (parts.length !== 3) return null;
            const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
            const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
            return JSON.parse(atob(padded));
        } catch (e) {
            return null;
        }
    }

    function isTokenValid(token) {
        const payload = decodeJwt(token);
        if (!payload || typeof payload.exp !== 'number') return false;
        const now = Math.floor(Date.now() / 1000);
        return payload.exp > now + AUTH_CONFIG.TOKEN_EXPIRY_LEEWAY_SECONDS;
    }

    function isTokenExpired(token) {
        const payload = decodeJwt(token);
        if (!payload || typeof payload.exp !== 'number') return true;
        return payload.exp <= Math.floor(Date.now() / 1000);
    }

    // ============================================================
    // SAFE REDIRECT HELPER — same-origin whitelist
    // ============================================================

    function _safeRedirect(target, fallback) {
        fallback = fallback || 'dashboard.html';
        if (!target || typeof target !== 'string') return fallback;
        try {
            if (/^[a-z][a-z0-9+.-]*:/i.test(target)) {
                const u = new URL(target, window.location.origin);
                if (u.origin !== window.location.origin) return fallback;
                return u.pathname + u.search + u.hash;
            }
            if (target.startsWith('//')) return fallback;
            return target;
        } catch (e) {
            return fallback;
        }
    }

    // ============================================================
    // STORAGE HELPERS
    // ============================================================

    function _readFirst(keys) {
        for (const k of keys) {
            try {
                const v = localStorage.getItem(k);
                if (v) return v;
            } catch (e) {}
        }
        return null;
    }

    function getStoredToken() {
        return _readFirst([AUTH_CONFIG.TOKEN_KEY, ...AUTH_CONFIG.LEGACY_ACCESS_KEYS]);
    }
    function getStoredRefresh() {
        return _readFirst([AUTH_CONFIG.REFRESH_KEY, ...AUTH_CONFIG.LEGACY_REFRESH_KEYS]);
    }
    function getStoredUser() {
        const raw = _readFirst([AUTH_CONFIG.USER_KEY, ...AUTH_CONFIG.LEGACY_USER_KEYS]);
        if (!raw) return null;
        try { return JSON.parse(raw); } catch { return null; }
    }
    function getStoredTenant() {
        const raw = _readFirst([AUTH_CONFIG.TENANT_KEY, ...AUTH_CONFIG.LEGACY_TENANT_KEYS]);
        if (!raw) return null;
        try { return JSON.parse(raw); } catch { return null; }
    }

    function writeToken(token) {
        if (!token) return;
        try {
            localStorage.setItem(AUTH_CONFIG.TOKEN_KEY, token);
            AUTH_CONFIG.LEGACY_ACCESS_KEYS.forEach(k => localStorage.setItem(k, token));
        } catch (e) {}
    }
    function writeRefresh(token) {
        if (!token) return;
        try {
            localStorage.setItem(AUTH_CONFIG.REFRESH_KEY, token);
            AUTH_CONFIG.LEGACY_REFRESH_KEYS.forEach(k => localStorage.setItem(k, token));
        } catch (e) {}
    }
    function writeUser(user) {
        if (!user) return;
        const s = JSON.stringify(user);
        try {
            localStorage.setItem(AUTH_CONFIG.USER_KEY, s);
            AUTH_CONFIG.LEGACY_USER_KEYS.forEach(k => localStorage.setItem(k, s));
            if (user.role && ['super_admin', 'org_admin', 'admin'].includes(user.role)) {
                localStorage.setItem(AUTH_CONFIG.ADMIN_USER_KEY, s);
            } else {
                localStorage.removeItem(AUTH_CONFIG.ADMIN_USER_KEY);
            }
        } catch (e) {}
    }
    function writeTenant(tenant) {
        if (!tenant) return;
        const s = JSON.stringify(tenant);
        try {
            localStorage.setItem(AUTH_CONFIG.TENANT_KEY, s);
            AUTH_CONFIG.LEGACY_TENANT_KEYS.forEach(k => localStorage.setItem(k, s));
        } catch (e) {}
    }
    function writeAdminToken(token) {
        try {
            if (token) localStorage.setItem(AUTH_CONFIG.ADMIN_TOKEN_KEY, token);
            else localStorage.removeItem(AUTH_CONFIG.ADMIN_TOKEN_KEY);
        } catch (e) {}
    }

    function clearAllAuthStorage() {
        const keys = new Set([
            AUTH_CONFIG.TOKEN_KEY, AUTH_CONFIG.REFRESH_KEY,
            AUTH_CONFIG.USER_KEY, AUTH_CONFIG.TENANT_KEY,
            AUTH_CONFIG.MFA_KEY, AUTH_CONFIG.SESSION_KEY,
            AUTH_CONFIG.ADMIN_TOKEN_KEY, AUTH_CONFIG.ADMIN_USER_KEY,
            ...AUTH_CONFIG.LEGACY_ACCESS_KEYS,
            ...AUTH_CONFIG.LEGACY_REFRESH_KEYS,
            ...AUTH_CONFIG.LEGACY_USER_KEYS,
            ...AUTH_CONFIG.LEGACY_TENANT_KEYS,
            'synapse_mfa', 'synapse_sessions', 'synapse_guest',
        ]);
        keys.forEach(k => { try { localStorage.removeItem(k); } catch (e) {} });
    }

    function getOrCreateDeviceId() {
        let id = null;
        try { id = localStorage.getItem(AUTH_CONFIG.DEVICE_ID_KEY); } catch (e) {}
        if (!id) {
            id = 'device_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
            try { localStorage.setItem(AUTH_CONFIG.DEVICE_ID_KEY, id); } catch (e) {}
        }
        return id;
    }

    // ============================================================
    // SINGLE-FLIGHT REFRESH PROMISE
    // Shared across every API call so concurrent 401s trigger one
    // refresh, not N.
    // ============================================================

    let _refreshPromise = null;

    async function performRefresh() {
        if (_refreshPromise) return _refreshPromise;

        const rt = getStoredRefresh();
        if (!rt) return false;

        _refreshPromise = (async () => {
            try {
                const resp = await fetch(
                    _joinUrl(AUTH_CONFIG.API_BASE_URL, '/api/v1/auth/refresh'),
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json',
                        },
                        body: JSON.stringify({
                            refresh_token: rt,
                            device_id: getOrCreateDeviceId(),
                        }),
                        credentials: 'same-origin',
                        cache: 'no-store',
                    }
                );
                if (!resp.ok) return false;
                const data = await resp.json().catch(() => null);
                if (!data || !data.success || !data.access_token) return false;

                writeToken(data.access_token);
                if (data.refresh_token) writeRefresh(data.refresh_token);

                try {
                    window.dispatchEvent(new CustomEvent('synapse:token-refreshed', {
                        detail: { access_token: data.access_token },
                    }));
                } catch (e) {}

                return true;
            } catch (e) {
                return false;
            } finally {
                _refreshPromise = null;
            }
        })();

        return _refreshPromise;
    }

    // ============================================================
    // STATE MANAGER
    // ============================================================

    class AuthStateManager {
        constructor() {
            this._listeners = [];
            this._user = null;
            this._token = null;
            this._refresh = null;
            this._mfaToken = null;
            this._tenant = null;
            this._session = null;
            this._permissions = [];
            this._sessionTimer = null;
            this._loginAttempts = 0;
            this._lockedUntil = null;
            this._lastActivity = Date.now();
            this._wsConnection = null;
            this._wsReconnectTimer = null;
            this._deviceId = null;
            this._sessions = [];
            this._rateLimitCount = 0;
            this._rateLimitReset = Date.now() + AUTH_CONFIG.RATE_LIMIT_WINDOW;
            this._mfaBackupCodes = [];
            this._idleCheckTimer = null;

            this._initialize();
        }

        _initialize() {
            if (typeof document !== 'undefined' && !this._visibilityListenerBound) {
                this._visibilityListenerBound = true;
                document.addEventListener('visibilitychange', () => {
                    if (document.visibilityState === 'visible' && this.isAuthenticated) {
                        if (!this._wsConnection || this._wsConnection.readyState !== WebSocket.OPEN) {
                            this._connectWebSocket();
                        }
                    }
                });
            }
            this._loadFromStorage();
            this._setupIdleDetection();
            this._setupActivityTracking();
            this._generateDeviceId();
            this._loadSessions();
            if (this.isAuthenticated) this._connectWebSocket();
            this._notifyListeners();
        }

        _generateDeviceId() {
            this._deviceId = getOrCreateDeviceId();
            return this._deviceId;
        }

        getDeviceId() {
            if (!this._deviceId) this._deviceId = getOrCreateDeviceId();
            return this._deviceId;
        }

        _loadSessions() {
            try {
                const raw = localStorage.getItem(AUTH_CONFIG.SESSIONS_KEY);
                this._sessions = raw ? JSON.parse(raw) : [];
                if (!Array.isArray(this._sessions)) this._sessions = [];
            } catch {
                this._sessions = [];
            }
        }

        _saveSessions() {
            try {
                localStorage.setItem(AUTH_CONFIG.SESSIONS_KEY, JSON.stringify(this._sessions));
            } catch (e) {}
        }

        addSession(session) {
            if (!session) return;
            if (session.id) {
                const existingIdx = this._sessions.findIndex(s => s.id === session.id);
                if (existingIdx >= 0) {
                    this._sessions[existingIdx] = session;
                    this._saveSessions();
                    return;
                }
            }
            this._sessions.push(session);
            this._saveSessions();
        }

        removeSession(sessionId) {
            this._sessions = this._sessions.filter(s => s.id !== sessionId);
            this._saveSessions();
        }

        clearSessions() {
            this._sessions = [];
            this._saveSessions();
        }

        getActiveSessions() {
            return this._sessions;
        }

        // ---- Lockout ----
        incrementLoginAttempts() {
            this._loginAttempts++;
            if (this._loginAttempts >= AUTH_CONFIG.MAX_LOGIN_ATTEMPTS) {
                this._lockedUntil = Date.now() + AUTH_CONFIG.LOCKOUT_DURATION;
                this._loginAttempts = 0;
                this._showToast('Account locked for 15 minutes due to too many failed attempts', 'error');
                return true;
            }
            return false;
        }

        resetLoginAttempts() {
            this._loginAttempts = 0;
            this._lockedUntil = null;
        }

        isLocked() {
            if (this._lockedUntil && Date.now() < this._lockedUntil) return true;
            if (this._lockedUntil && Date.now() >= this._lockedUntil) {
                this._lockedUntil = null;
                this._loginAttempts = 0;
            }
            return false;
        }

        getLockoutRemaining() {
            if (!this._lockedUntil) return 0;
            return Math.max(0, Math.ceil((this._lockedUntil - Date.now()) / 60000));
        }

        // ---- Client rate guard ----
        checkRateLimit() {
            const user = this._user || getStoredUser();
            const plan = String((user && user.plan) || 'free').toLowerCase();
            const limits = { free: 300, starter: 600, professional: 1500, business: 5000, enterprise: 20000 };
            const max = limits[plan] || AUTH_CONFIG.RATE_LIMIT_MAX;
            if (Date.now() > this._rateLimitReset) {
                this._rateLimitCount = 0;
                this._rateLimitReset = Date.now() + AUTH_CONFIG.RATE_LIMIT_WINDOW;
            }
            this._rateLimitCount++;
            return this._rateLimitCount > max;
        }

        getRateLimitReset() {
            return this._rateLimitReset;
        }

        // ---- MFA backup codes ----
        setBackupCodes(codes) {
            this._mfaBackupCodes = codes || [];
            try {
                localStorage.setItem('synapse_backup_codes', JSON.stringify(this._mfaBackupCodes));
            } catch (e) {}
        }

        getBackupCodes() {
            if (this._mfaBackupCodes.length === 0) {
                try {
                    const raw = localStorage.getItem('synapse_backup_codes');
                    if (raw) this._mfaBackupCodes = JSON.parse(raw);
                } catch {
                    this._mfaBackupCodes = [];
                }
            }
            return this._mfaBackupCodes;
        }

        // ---- Getters ----
        get user()            { return this._user; }
        get token()           { return this._token; }
        get refresh()         { return this._refresh; }
        get mfaToken()        { return this._mfaToken; }
        get tenant()          { return this._tenant; }
        get session()         { return this._session; }
        get permissions()     { return this._permissions; }
        get lastActivity()    { return this._lastActivity; }
        get plan()            { return this._user ? (this._user.plan || 'free') : 'free'; }

        get isAuthenticated() {
            return !!(this._token && this._user && isTokenValid(this._token));
        }
        get isAdmin() {
            if (!this._user) return false;
            return ['super_admin', 'admin', 'org_admin'].includes(this._user.role);
        }
        get isSuperAdmin() {
            return !!(this._user && this._user.role === 'super_admin');
        }
        get isMFARequired() {
            return !!(this._mfaToken && !this.isAuthenticated);
        }

        // ---- Setters ----
        setUser(user) {
            this._user = user;
            if (user) {
                writeUser(user);
                this._permissions = this._calculatePermissions(user);
            } else {
                try {
                    localStorage.removeItem(AUTH_CONFIG.USER_KEY);
                    AUTH_CONFIG.LEGACY_USER_KEYS.forEach(k => localStorage.removeItem(k));
                } catch (e) {}
                this._permissions = [];
            }
            this._notifyListeners();
        }

        setToken(token) {
            const hadToken = !!this._token;
            this._token = token || null;
            if (token) {
                writeToken(token);
                this._startSessionTimer();
                if (!hadToken) this._connectWebSocket();
            } else {
                try {
                    localStorage.removeItem(AUTH_CONFIG.TOKEN_KEY);
                    AUTH_CONFIG.LEGACY_ACCESS_KEYS.forEach(k => localStorage.removeItem(k));
                } catch (e) {}
                this._stopSessionTimer();
                this._disconnectWebSocket();
            }
            this._notifyListeners();
        }

        setRefresh(refresh) {
            this._refresh = refresh || null;
            if (refresh) writeRefresh(refresh);
            else {
                try {
                    localStorage.removeItem(AUTH_CONFIG.REFRESH_KEY);
                    AUTH_CONFIG.LEGACY_REFRESH_KEYS.forEach(k => localStorage.removeItem(k));
                } catch (e) {}
            }
        }

        setMFAToken(token) {
            this._mfaToken = token || null;
            try {
                if (token) localStorage.setItem(AUTH_CONFIG.MFA_KEY, token);
                else localStorage.removeItem(AUTH_CONFIG.MFA_KEY);
            } catch (e) {}
            this._notifyListeners();
        }

        setTenant(tenant) {
            this._tenant = tenant || null;
            if (tenant) writeTenant(tenant);
            else {
                try {
                    localStorage.removeItem(AUTH_CONFIG.TENANT_KEY);
                    AUTH_CONFIG.LEGACY_TENANT_KEYS.forEach(k => localStorage.removeItem(k));
                } catch (e) {}
            }
            this._notifyListeners();
        }

        setSession(session) {
            this._session = session || null;
            try {
                if (session) {
                    localStorage.setItem(AUTH_CONFIG.SESSION_KEY, JSON.stringify(session));
                } else {
                    localStorage.removeItem(AUTH_CONFIG.SESSION_KEY);
                }
            } catch (e) {}
        }

        setAdminToken(token) {
            writeAdminToken(token);
        }

        // ---- Permissions ----
        _calculatePermissions(user) {
            if (!user) return [];
            const rolePerms = {
                super_admin: ['*'],
                admin:       ['read','write','delete','manage_users','view_analytics','manage_ml','view_audit'],
                org_admin:   ['read','write','delete','manage_users','view_analytics','manage_ml','view_audit'],
                manager:     ['read','write','view_analytics'],
                engineer:    ['read','write','manage_ml','view_analytics'],
                operator:    ['read','write'],
                viewer:      ['read'],
            };
            return rolePerms[user.role] || ['read'];
        }

        hasPermission(permission) {
            if (this.isSuperAdmin) return true;
            return this._permissions.includes(permission) || this._permissions.includes('*');
        }

        hasFeature(feature) {
            if (this.isSuperAdmin) return true;
            if (this.isAuthenticated) {
                return this._permissions.includes(feature) || this.hasPermission('admin');
            }
            return false;
        }

        getFeatureStatus(feature) {
            if (this.isAuthenticated) {
                return {
                    allowed: this.hasFeature(feature),
                    plan: this.plan,
                    role: this._user ? this._user.role : null,
                    reason: this.hasFeature(feature) ? null : 'Upgrade required',
                };
            }
            return { allowed: false, plan: 'visitor', reason: 'Please login' };
        }

        // ---- Session timer ----
        _startSessionTimer() {
            this._stopSessionTimer();
            this._sessionTimer = setTimeout(
                () => this._handleSessionTimeout(),
                AUTH_CONFIG.SESSION_TIMEOUT
            );
        }

        _stopSessionTimer() {
            if (this._sessionTimer) {
                clearTimeout(this._sessionTimer);
                this._sessionTimer = null;
            }
        }

        _handleSessionTimeout() {
            this.logout('Session expired. Please login again.');
        }

        _setupIdleDetection() {
            this._idleCheckTimer = setInterval(() => {
                if (this.isAuthenticated && Date.now() - this._lastActivity > AUTH_CONFIG.IDLE_TIMEOUT) {
                    this.logout('Session idle timeout.');
                }
            }, 60000);
        }

        _setupActivityTracking() {
            const events = ['mousedown','keydown','touchstart','scroll','click'];
            events.forEach(evt => {
                document.addEventListener(evt, () => { this._lastActivity = Date.now(); }, { passive: true });
            });
        }

        // ---- WebSocket ----
        _disconnectWebSocket() {
            if (this._wsReconnectTimer) {
                clearTimeout(this._wsReconnectTimer);
                this._wsReconnectTimer = null;
            }
            if (this._wsConnection) {
                try {
                    this._wsConnection.onclose = null;
                    this._wsConnection.onerror = null;
                    this._wsConnection.onmessage = null;
                    this._wsConnection.close();
                } catch (e) {}
                this._wsConnection = null;
            }
        }

        _connectWebSocket() {
            if (!this.isAuthenticated) return;
            if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
            if (this._wsConnection && this._wsConnection.readyState === WebSocket.OPEN) return;

            if (this._wsConnection) this._disconnectWebSocket();

            try {
                const url = AUTH_CONFIG.WS_URL
                    + (AUTH_CONFIG.WS_URL.includes('?') ? '&' : '?')
                    + 'token=' + encodeURIComponent(this._token || '');

                this._wsConnection = new WebSocket(url);

                this._wsConnection.onopen = () => {
                    console.log('🔌 WebSocket connected');
                    this._wsReconnectAttempt = 0;
                    if (this._wsReconnectTimer) {
                        clearTimeout(this._wsReconnectTimer);
                        this._wsReconnectTimer = null;
                    }
                };

                this._wsConnection.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this._handleWebSocketMessage(data);
                    } catch (e) {
                        console.error('Invalid WebSocket message:', e);
                    }
                };

                this._wsConnection.onclose = (evt) => {
                    console.log('🔌 WebSocket disconnected', evt && evt.code);
                    if (evt && evt.code === 1008) return;
                    if (this.isAuthenticated && isTokenValid(this._token)) {
                        const attempt = Math.min(8, Number(this._wsReconnectAttempt || 0));
                        this._wsReconnectAttempt = attempt + 1;
                        const delay = Math.min(60000, 1000 * (2 ** attempt)) + Math.floor(Math.random() * 500);
                        this._wsReconnectTimer = setTimeout(() => this._connectWebSocket(), delay);
                    }
                };

                this._wsConnection.onerror = (err) => {
                    console.error('WebSocket error:', err);
                };
            } catch (e) {
                console.error('Failed to connect WebSocket:', e);
            }
        }

        _handleWebSocketMessage(data) {
            switch (data.type) {
                case 'ping':
                    if (this._wsConnection && this._wsConnection.readyState === WebSocket.OPEN) {
                        this._wsConnection.send(JSON.stringify({ type: 'pong' }));
                    }
                    break;
                case 'auth_error':
                    this._disconnectWebSocket();
                    break;
                case 'notification':
                    this._showToast(data.message, data.severity || 'info');
                    break;
                case 'prediction_created':
                    if (data.prediction && data.prediction.machine_name === '__dataset__') {
                        data.prediction.machine_name = 'Dataset prediction';
                    }
                    this._listeners.forEach(fn => { try { fn('prediction', data); } catch (e) {} });
                    try { window.dispatchEvent(new CustomEvent('synapse:admin-data-changed', { detail: { event: 'prediction_created', payload: data } })); } catch (e) {}
                    break;
                case 'alert_triggered':
                case 'alert_created':
                    this._listeners.forEach(fn => { try { fn('alert', data); } catch (e) {} });
                    try { window.dispatchEvent(new CustomEvent('synapse:admin-data-changed', { detail: { event: data.type || 'alert_created', payload: data } })); } catch (e) {}
                    break;
                case 'session_revoked':
                    if (data.session_id && this._session && data.session_id === this._session.id) {
                        this.logout('Your session was revoked remotely.');
                    }
                    break;
                case 'system_status_changed':
                    try {
                        window.dispatchEvent(new CustomEvent('synapse:system-status-changed', { detail: data }));
                    } catch (e) {}
                    if (data.online === false && !this.isAdmin) {
                        this._disconnectWebSocket();
                        this._showToast('SynapsePM is temporarily unavailable.', 'warning');
                        try { if (window.location.pathname !== '/404.html') window.location.replace('/404.html'); } catch (e) {}
                    } else if (data.online === true && window.location.pathname === '/404.html') {
                        window.location.replace('/dashboard.html');
                    }
                    this._listeners.forEach(fn => { try { fn('system_status', data); } catch (e) {} });
                    break;
                case 'user_created':
                case 'user_updated':
                case 'user_deleted':
                case 'machine_created':
                case 'machine_updated':
                case 'machine_deleted':
                case 'report_created':
                case 'billing_updated':
                case 'enterprise_request_updated':
                case 'download_created':
                case 'alerts_marked_read':
                case 'settings_updated':
                    try {
                        window.dispatchEvent(new CustomEvent('synapse:admin-data-changed', {
                            detail: { type: data.type || null, event: data.event || data.type || 'updated', payload: data }
                        }));
                    } catch (e) {}
                    this._listeners.forEach(fn => { try { fn('admin_data', data); } catch (e) {} });
                    break;
                default:
                    break;
            }
        }

        // ---- Load from storage ----
        _loadFromStorage() {
            const token = getStoredToken();
            const refresh = getStoredRefresh();
            const user = getStoredUser();
            let mfaToken = null, tenant = null, session = null;
            try { mfaToken = localStorage.getItem(AUTH_CONFIG.MFA_KEY); } catch (e) {}
            tenant = getStoredTenant();
            try {
                const s = localStorage.getItem(AUTH_CONFIG.SESSION_KEY);
                session = s ? JSON.parse(s) : null;
            } catch {}

            if (token && user) {
                try {
                    this._token = token;
                    this._refresh = refresh;
                    this._user = user;
                    this._mfaToken = mfaToken;
                    this._tenant = tenant;
                    this._session = session;
                    this._permissions = this._calculatePermissions(user);

                    if (!isTokenValid(token)) {
                        // Keep access + refresh + user together. A protected request can
                        // receive 401 and perform the automatic refresh flow instead of
                        // destroying a still-valid login session and showing Guest.
                        console.warn('Stored access token expired — retaining refresh session for automatic renewal');
                    } else {
                        this._startSessionTimer();
                    }
                } catch (e) {
                    this.clear();
                }
            }
        }

        // ---- Clear / logout ----
        clear() {
            this._token = null;
            this._refresh = null;
            this._user = null;
            this._mfaToken = null;
            this._tenant = null;
            this._session = null;
            this._permissions = [];
            this._stopSessionTimer();
            this._disconnectWebSocket();
            clearAllAuthStorage();
            this._notifyListeners();
        }

        logout(message) {
            this.clear();
            if (message) this._showToast(message, 'info');
            return true;
        }

        // ---- Listeners ----
        addListener(fn) { this._listeners.push(fn); }
        removeListener(fn) { this._listeners = this._listeners.filter(f => f !== fn); }

        _notifyListeners() {
            this._listeners.forEach(fn => {
                try { fn(this.isAuthenticated, this._user); } catch (e) {}
            });
        }

        // ---- Toast ----
        _showToast(message, type) {
            type = type || 'success';
            const key = String(type) + '::' + String(message);
            const now = Date.now();
            if (!this._toastHistory) this._toastHistory = Object.create(null);
            if (this._toastHistory[key] && now - this._toastHistory[key] < 3000) return;
            this._toastHistory[key] = now;
            for (const oldKey of Object.keys(this._toastHistory)) {
                if (now - this._toastHistory[oldKey] > 10000) delete this._toastHistory[oldKey];
            }
            const colors = { success:'#10b981', error:'#ef4444', warning:'#f59e0b', info:'#3b82f6' };
            try {
                const toast = document.createElement('div');
                toast.style.cssText =
                    'position:fixed;bottom:20px;right:20px;padding:12px 24px;' +
                    'border-radius:12px;background:' + (colors[type] || colors.info) + ';' +
                    'color:white;z-index:9999;font-family:Inter,sans-serif;font-size:14px;' +
                    'box-shadow:0 4px 12px rgba(0,0,0,0.15);max-width:90%;';
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(() => { try { toast.remove(); } catch (e) {} }, 4000);
            } catch (e) {}
        }
    }

    // ============================================================
    // API CLIENT
    // ============================================================

    class AuthAPIClient {
        constructor(state) {
            this._state = state;
            this._pendingRequests = new Map();
            this._rateLimitedUntil = null;
        }

        // ---- Header builder (FormData-aware) ----
        _buildHeaders(extra, body) {
            const headers = { 'Accept': 'application/json' };
            const isForm = (typeof FormData !== 'undefined') && (body instanceof FormData);
            if (!isForm) headers['Content-Type'] = 'application/json';

            const token = this._state.token || getStoredToken();
            if (token) headers['Authorization'] = 'Bearer ' + token;

            if (this._state.mfaToken) headers['X-MFA-Token'] = this._state.mfaToken;

            const tenant = this._state.tenant;
            if (tenant && tenant.id) headers['X-Tenant-ID'] = tenant.id;

            const deviceId = this._state.getDeviceId();
            if (deviceId) headers['X-Device-ID'] = deviceId;

            if (extra) {
                for (const k of Object.keys(extra)) headers[k] = extra[k];
            }
            return headers;
        }

        _url(endpoint) {
            return _joinUrl(AUTH_CONFIG.API_BASE_URL, endpoint);
        }

        // ---- Core request ----
        async _request(endpoint, options) {
            options = options || {};

            if (this._rateLimitedUntil && Date.now() < this._rateLimitedUntil) {
                const remaining = Math.ceil((this._rateLimitedUntil - Date.now()) / 1000);
                throw new Error('Rate limited. Please wait ' + remaining + ' seconds.');
            }

            if (this._state.checkRateLimit()) {
                this._rateLimitedUntil = this._state.getRateLimitReset();
                throw new Error('Too many requests. Please wait.');
            }

            const isAuthEndpoint = endpoint.startsWith('/api/v1/auth/');
            const url = this._url(endpoint);

            const bodyForKey = (options.body instanceof FormData)
                ? '[formdata]'
                : JSON.stringify(options.body || {});
            const method = String(options.method || 'GET').toUpperCase();
            const isPaymentWrite = method === 'POST' && /\/(payments|billing)\/(create-checkout|checkout|khalti\/initiate)(?:$|\?)/i.test(endpoint);
            if (isPaymentWrite) {
                options = Object.assign({}, options, { headers: Object.assign({}, options.headers || {}) });
                if (!options.headers['Idempotency-Key']) {
                    const key = (typeof crypto !== 'undefined' && crypto.randomUUID)
                        ? crypto.randomUUID() : ('spm-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 18));
                    options.headers['Idempotency-Key'] = key;
                }
            }
            const dedupKey = method + ' ' + endpoint + ' ' + bodyForKey;

            if (this._pendingRequests.has(dedupKey)) {
                return this._pendingRequests.get(dedupKey);
            }

            const promise = this._executeWithRefresh(url, endpoint, options, isAuthEndpoint);
            this._pendingRequests.set(dedupKey, promise);
            try {
                return await promise;
            } finally {
                this._pendingRequests.delete(dedupKey);
            }
        }

        async _executeWithRefresh(url, endpoint, options, isAuthEndpoint) {
            if (!isAuthEndpoint) {
                const stored = this._state.token || getStoredToken();
                if (stored && isTokenExpired(stored)) {
                    const ok = await performRefresh();
                    if (!ok) {
                        this._state.logout('Session expired');
                        throw new Error('Session expired');
                    }
                }
            }

            const attempt = async () => {
                const headers = this._buildHeaders(options.headers, options.body);
                let body = null;
                if (options.body !== undefined && options.body !== null) {
                    if (options.body instanceof FormData) {
                        body = options.body;
                    } else if (typeof options.body === 'string') {
                        body = options.body;
                    } else {
                        body = JSON.stringify(options.body);
                    }
                }
                return fetch(url, {
                    method: options.method || 'GET',
                    headers,
                    body,
                    credentials: 'same-origin',
                });
            };

            let response;
            let networkError = null;
            for (let attemptNum = 0; attemptNum < 2; attemptNum++) {
                try {
                    response = await attempt();
                    networkError = null;
                    break;
                } catch (err) {
                    networkError = err;
                    if (attemptNum === 0 && !isAuthEndpoint) {
                        await new Promise(resolve => setTimeout(resolve, 800));
                        continue;
                    }
                    throw err;
                }
            }
            if (networkError || !response) throw networkError || new Error('Network request failed');

            if (response.status === 429) {
                const retryAfter = parseInt(response.headers.get('Retry-After')) || 60;
                this._rateLimitedUntil = Date.now() + retryAfter * 1000;
                let rateData = null;
                try { rateData = await response.clone().json(); } catch (_) {}
                const err = new Error((rateData && (rateData.error || rateData.message)) || ('Rate limited. Try again in ' + retryAfter + 's'));
                err.status = 429;
                err.retryAfter = retryAfter;
                err.data = rateData || { retry_after: retryAfter };
                throw err;
            }

            if (response.status === 401 && !options._retried && !isAuthEndpoint) {
                const ok = await performRefresh();
                if (ok) {
                    options = Object.assign({}, options, { _retried: true });
                    response = await attempt();
                } else {
                    this._state.logout('Session expired');
                    throw new Error('Authentication required');
                }
            }

            const ctype = response.headers.get('content-type') || '';
            let data = null;
            if (ctype.includes('application/json')) {
                try { data = await response.json(); } catch { data = null; }
            } else {
                try {
                    const text = await response.text();
                    try { data = JSON.parse(text); } catch { data = { raw: text }; }
                } catch { data = null; }
            }

            if (!response.ok) {
                const msg = (data && (data.message || data.error || data.detail)) || ('HTTP ' + response.status);
                const err = new Error(msg);
                err.status = response.status;
                err.data = data;
                throw err;
            }
            return data;
        }

        // ========================================================
        // AUTH
        // ========================================================

        async login(email, password, rememberMe) {
            rememberMe = !!rememberMe;
            const pathname = (window.location && window.location.pathname || '').toLowerCase();
            const portal = pathname.startsWith('/admin/') ? 'admin' : 'user';

            if (this._state.isLocked()) {
                throw new Error('Account locked. Try again in ' + this._state.getLockoutRemaining() + ' minutes.');
            }

            const data = await this._request('/api/v1/auth/login', {
                method: 'POST',
                body: {
                    email, password,
                    remember_me: rememberMe,
                    portal,
                    device_id: this._state.getDeviceId(),
                    user_agent: navigator.userAgent,
                },
            });

            if (!data.success) {
                if (this._state.incrementLoginAttempts()) {
                    throw new Error('Account locked for 15 minutes due to too many failed attempts');
                }
                throw new Error(data.message || 'Login failed');
            }

            this._state.resetLoginAttempts();

            if (data.mfa_required) {
                this._state.setMFAToken(data.challenge_token || data.mfa_token || null);
                return { success: true, mfa_required: true };
            }

            this._state.setToken(data.access_token);
            this._state.setRefresh(data.refresh_token);
            this._state.setUser(data.user);
            this._state.setTenant(data.tenant || data.organization || null);
            this._state.setSession(data.session || null);
            if (data.session) this._state.addSession(data.session);

            if (data.user && ['super_admin','org_admin','admin'].includes(data.user.role)) {
                this._state.setAdminToken(data.access_token);
            }

            this._logActivity('login', 'User logged in');
            try { sessionStorage.setItem('justLoggedIn', 'true'); } catch (e) {}

            const redirect = _safeRedirect(
                data.redirect
                || (function () { try { return localStorage.getItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) { return null; } })()
                || (portal === 'admin' ? '/admin/dashboard.html' : '/dashboard.html')
            );
            try { localStorage.removeItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) {}

            return { success: true, redirect, user: data.user };
        }

        async verifyMFA(code, rememberDevice) {
            rememberDevice = !!rememberDevice;
            const challenge = this._state.mfaToken;
            if (!challenge) throw new Error('No MFA challenge in progress');

            const data = await this._request('/api/v1/auth/verify-mfa', {
                method: 'POST',
                body: {
                    code,
                    challenge_token: challenge,
                    mfa_token: challenge,
                    remember_device: rememberDevice,
                    device_id: this._state.getDeviceId(),
                },
            });

            if (!data.success) throw new Error(data.message || 'Invalid MFA code');

            this._state.setToken(data.access_token);
            this._state.setRefresh(data.refresh_token);
            this._state.setUser(data.user);
            this._state.setTenant(data.tenant || data.organization || null);
            this._state.setMFAToken(null);
            this._state.setSession(data.session || null);
            if (data.session) this._state.addSession(data.session);

            if (data.user && ['super_admin','org_admin','admin'].includes(data.user.role)) {
                this._state.setAdminToken(data.access_token);
            }

            this._logActivity('mfa_verified', 'MFA verification successful');

            const redirect = _safeRedirect(
                data.redirect
                || (function () { try { return localStorage.getItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) { return null; } })()
                || ((window.location && (window.location.pathname || '').toLowerCase().startsWith('/admin/')) ? '/admin/dashboard.html' : '/dashboard.html')
            );
            try { localStorage.removeItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) {}

            return { success: true, redirect, user: data.user };
        }

        async register(userData) {
            const data = await this._request('/api/v1/auth/register', {
                method: 'POST',
                body: {
                    email:      userData.email,
                    password:   userData.password,
                    first_name: userData.firstName,
                    last_name:  userData.lastName,
                    company:    userData.company  || '',
                    job_title:  userData.jobTitle || '',
                    phone:      userData.phone    || '',
                    device_id:  this._state.getDeviceId(),
                },
            });

            if (!data.success) throw new Error(data.message || 'Registration failed');

            this._state.setToken(data.access_token);
            this._state.setRefresh(data.refresh_token);
            this._state.setUser(data.user);
            this._state.setTenant(data.organization || data.tenant || null);
            this._state.setSession(data.session || null);
            if (data.session) this._state.addSession(data.session);

            if (data.user && ['super_admin','org_admin','admin'].includes(data.user.role)) {
                this._state.setAdminToken(data.access_token);
            }

            this._logActivity('register', 'User registered successfully');
            try { sessionStorage.setItem('signupSuccess', 'true'); } catch (e) {}

            this._sendEmail({
                to: userData.email,
                subject: 'Welcome to SynapsePM!',
                template: 'welcome',
                data: {
                    name: userData.firstName,
                    email: userData.email,
                    company: userData.company || 'Your Company',
                    link: window.location.origin + '/verify-email?token=' + (data.verification_token || ''),
                },
            });

            return data;
        }

        async logout(revokeAll) {
            revokeAll = !!revokeAll;
            const token = this._state.token || getStoredToken();
            if (token && isTokenValid(token)) {
                try {
                    await this._request('/api/v1/auth/logout', {
                        method: 'POST', body: { revoke_all: revokeAll },
                    });
                    this._logActivity('logout', 'User logged out');
                } catch (e) {}
            }
            if (revokeAll) this._state.clearSessions();
            this._state.logout('Logged out successfully');
            return true;
        }

        // ========================================================
        // PASSWORD RESET (OTP flow)
        // ========================================================

        async sendOTP(email) {
            const data = await this._request('/api/v1/auth/forgot-password', {
                method: 'POST',
                body: { email, device_id: this._state.getDeviceId() },
            });
            if (!data.success) throw new Error(data.message || 'Failed to send OTP');
            return data;
        }

        async verifyOTP(email, otp) {
            const data = await this._request('/api/v1/auth/verify-otp', {
                method: 'POST',
                body: { email, otp },
            });
            if (!data.success) throw new Error(data.message || 'Invalid OTP');
            return data;
        }

        async resetPassword(email, otpOrToken, newPassword) {
            const body = {
                new_password: newPassword,
                password: newPassword,
                device_id: this._state.getDeviceId(),
            };
            if (otpOrToken && String(otpOrToken).length > 10) {
                body.token = otpOrToken;
            } else {
                body.email = email;
                body.otp = otpOrToken;
            }
            const data = await this._request('/api/v1/auth/reset-password', {
                method: 'POST',
                body,
            });
            if (!data.success) throw new Error(data.message || 'Failed to reset password');
            return data;
        }

        async forgotPassword(email) {
            return this.sendOTP(email);
        }

        // ========================================================
        // MFA BACKUP CODES
        // ========================================================

        async generateBackupCodes() {
            const data = await this._request('/api/v1/auth/mfa/backup-codes', {
                method: 'POST',
                body: { count: AUTH_CONFIG.BACKUP_CODES_COUNT },
            });
            if (data.success && data.codes) {
                this._state.setBackupCodes(data.codes);
                this._logActivity('generate_backup_codes', 'MFA backup codes generated');
            }
            return data;
        }

        async verifyBackupCode(code) {
            return this._request('/api/v1/auth/mfa/verify-backup', {
                method: 'POST',
                body: { code },
            });
        }

        // ========================================================
        // SESSION MANAGEMENT
        // ========================================================

        async getActiveSessions() {
            const data = await this._request('/api/v1/auth/sessions', { method: 'GET' });
            if (data.sessions) {
                this._state._sessions = data.sessions;
                this._state._saveSessions();
                this._state._notifyListeners();
            }
            return data;
        }

        getActiveSessionsCount() {
            return this._state ? this._state.getActiveSessions().length : 0;
        }

        async revokeSession(sessionId) {
            const data = await this._request('/api/v1/auth/sessions/' + encodeURIComponent(sessionId), {
                method: 'DELETE',
            });
            this._state.removeSession(sessionId);
            this._logActivity('revoke_session', 'Session revoked: ' + sessionId);
            return data;
        }

        async revokeAllSessions() {
            const data = await this._request('/api/v1/auth/sessions/revoke-all', {
                method: 'POST',
            });
            this._state.clearSessions();
            this._logActivity('revoke_all_sessions', 'All sessions revoked');
            return data;
        }

        // ========================================================
        // PASSWORD EXPIRY
        // ========================================================

        async checkPasswordExpiry() {
            const user = this._state.user;
            if (!user) return null;

            if (user.password_last_changed) {
                const lastChanged = new Date(user.password_last_changed);
                if (isNaN(lastChanged.getTime())) return null;
                const daysSince = Math.floor((Date.now() - lastChanged) / (1000 * 60 * 60 * 24));

                if (daysSince >= AUTH_CONFIG.PASSWORD_EXPIRY_DAYS) {
                    return {
                        expired: true,
                        days_overdue: daysSince - AUTH_CONFIG.PASSWORD_EXPIRY_DAYS,
                        message: 'Your password has expired. Please change it.',
                    };
                }
                const daysRemaining = AUTH_CONFIG.PASSWORD_EXPIRY_DAYS - daysSince;
                if (daysRemaining <= 7) {
                    return {
                        expired: false,
                        days_remaining: daysRemaining,
                        message: 'Your password will expire in ' + daysRemaining + ' days.',
                    };
                }
            }
            return null;
        }

        // ========================================================
        // SOCIAL LOGIN
        // ========================================================

        async socialLogin(provider) {
            const url = this._url('/api/v1/auth/' + encodeURIComponent(provider));
            const response = await fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin', cache: 'no-store' });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || err.message || 'OAuth not available for ' + provider);
            }
            const data = await response.json();
            if (!data || !data.redirect_url) {
                throw new Error('Server did not return an OAuth redirect URL');
            }
            window.location.href = data.redirect_url;
        }

        async _exchangeOAuthCode(oauthCode) {
            const data = await this._request('/api/v1/auth/oauth/exchange', {
                method: 'POST',
                body: { code: oauthCode },
            });
            if (!data.success) throw new Error(data.message || 'OAuth exchange failed');
            this._state.setToken(data.access_token);
            this._state.setRefresh(data.refresh_token);
            this._state.setUser(data.user);
            this._state.setTenant(data.tenant || data.organization || null);
            this._state.setSession(data.session || null);
            if (data.session) this._state.addSession(data.session);
            if (data.user && ['super_admin','org_admin','admin'].includes(data.user.role)) {
                this._state.setAdminToken(data.access_token);
            }
            return data;
        }

        handleSocialCallback() {
            const params = new URLSearchParams(window.location.search);
            const oauthCode = params.get('code') || params.get('oauth_code');
            const error = params.get('error');

            const path = window.location.pathname || '';
            const isSameWindowSuccess = /auth-success(\.html)?$/i.test(path);

            if (isSameWindowSuccess && oauthCode) {
                this._exchangeOAuthCode(oauthCode)
                    .then(() => {
                        const redirect = _safeRedirect(
                            (function () { try { return localStorage.getItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) { return null; } })()
                            || 'dashboard.html'
                        );
                        try { localStorage.removeItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) {}
                        window.location.href = redirect;
                    })
                    .catch(err => {
                        const msg = encodeURIComponent(err.message || 'OAuth failed');
                        window.location.href = 'login.html?error=' + msg;
                    });
                return;
            }

            if (error) {
                if (window.opener) {
                    window.opener.postMessage(
                        { type: 'social_auth_error', message: error },
                        window.location.origin
                    );
                } else {
                    window.location.href = 'login.html?error=' + encodeURIComponent(error);
                }
                return;
            }
            if (oauthCode && window.opener) {
                const url = this._url('/api/v1/auth/oauth/exchange');
                fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                    body: JSON.stringify({ code: oauthCode }),
                    credentials: 'same-origin',
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        window.opener.postMessage({
                            type: 'social_auth_success',
                            access_token: data.access_token,
                            refresh_token: data.refresh_token,
                            user: data.user,
                            tenant: data.tenant || data.organization || null,
                            session: data.session || null,
                        }, window.location.origin);
                    } else {
                        window.opener.postMessage({
                            type: 'social_auth_error',
                            message: data.message || 'Authentication failed',
                        }, window.location.origin);
                    }
                })
                .catch(err => {
                    if (window.opener) {
                        window.opener.postMessage({
                            type: 'social_auth_error',
                            message: err.message || 'Network error',
                        }, window.location.origin);
                    }
                })
                .finally(() => { try { window.close(); } catch (e) {} });
            }
        }

        // ========================================================
        // DASHBOARD HELPERS
        // ========================================================

        redirectToLogin()     { window.location.href = 'login.html'; }
        redirectToSignup()    { window.location.href = 'signup.html'; }
        redirectToDashboard() { window.location.href = 'dashboard.html'; }

        getUser()  { return this._state.user || getStoredUser(); }
        getToken() { return this._state.token || getStoredToken(); }
        isAuthenticated() { return this._state.isAuthenticated; }
        getRedirectUrl() {
            try { return localStorage.getItem(AUTH_CONFIG.REDIRECT_KEY) || 'dashboard.html'; }
            catch (e) { return 'dashboard.html'; }
        }

        // ========================================================
        // HEALTH CHECK
        // ========================================================

        async health() {
            try {
                const url = this._url('/health');
                const r = await fetch(url, {
                    headers: { 'Accept': 'application/json' },
                    credentials: 'same-origin',
                });
                return await r.json();
            } catch (e) {
                return { status: 'unreachable', error: e.message };
            }
        }

        // ========================================================
        // MACHINES
        // ========================================================

        async getMachines() {
            return this._request('/api/v1/machines?per_page=200', { method: 'GET' });
        }
        async addMachine(machineData) {
            const data = await this._request('/api/v1/machines', {
                method: 'POST', body: machineData,
            });
            this._logActivity('add_machine', 'Added machine: ' + machineData.name);
            return data;
        }
        async updateMachine(machineId, data) {
            return this._request('/api/v1/machines/' + encodeURIComponent(machineId), {
                method: 'PUT', body: data,
            });
        }
        async deleteMachine(machineId) {
            return this._request('/api/v1/machines/' + encodeURIComponent(machineId), {
                method: 'DELETE',
            });
        }
        async connectMachine(machineId, connectionData) {
            const data = await this._request(
                '/api/v1/machines/' + encodeURIComponent(machineId) + '/connect',
                { method: 'POST', body: connectionData || {} }
            );
            this._logActivity('connect_machine', 'Connected machine: ' + machineId);
            return data;
        }
        async simulateMachine(machineId) {
            const data = await this._request(
                '/api/v1/machines/' + encodeURIComponent(machineId) + '/simulate',
                { method: 'POST' }
            );
            this._logActivity('simulate_machine', 'Simulated machine: ' + machineId);
            return data;
        }
        async machinePredict(machineId, options) {
            options = options || {};
            const data = await this._request(
                '/api/v1/machines/' + encodeURIComponent(machineId) + '/predict',
                {
                    method: 'POST',
                    body: {
                        model_type: options.model || 'auto',
                        horizon: options.horizon || 30,
                        features: options.features || {},
                    },
                }
            );
            this._logActivity('machine_predict', 'Machine prediction: ' + machineId);
            return data;
        }

        // ---- Device keys ----
        async createMachineDeviceKey(machineId, name) {
            return this._request(
                '/api/v1/machines/' + encodeURIComponent(machineId) + '/api-keys',
                { method: 'POST', body: { name: name || 'Device key' } }
            );
        }
        async listMachineDeviceKeys(machineId) {
            return this._request(
                '/api/v1/machines/' + encodeURIComponent(machineId) + '/api-keys',
                { method: 'GET' }
            );
        }
        async revokeMachineDeviceKey(machineId, keyId) {
            return this._request(
                '/api/v1/machines/' + encodeURIComponent(machineId) + '/api-keys/' + encodeURIComponent(keyId),
                { method: 'DELETE' }
            );
        }
        async getMachineSensorData(machineId, limit) {
            const qs = limit ? ('?limit=' + encodeURIComponent(limit)) : '';
            return this._request(
                '/api/v1/machines/' + encodeURIComponent(machineId) + '/sensor-data' + qs,
                { method: 'GET' }
            );
        }

        // ========================================================
        // PREDICTIONS
        // ========================================================

        async runPrediction(machineId, model, horizon) {
            const body = {
                machine_id: machineId,
                horizon: horizon || 30,
                device_id: this._state.getDeviceId(),
            };
            if (model && model !== 'auto') {
                body.model = model;
                body.model_type = model;
            }
            const data = await this._request('/api/v1/predictions/run', {
                method: 'POST', body,
            });
            this._logActivity('prediction', 'Ran prediction for machine: ' + machineId);
            return data;
        }

        /**
         * Run a prediction on an uploaded dataset.
         * Accepts either:
         *   - machineId  (a connected machine)
         *   - machineType (e.g. 'pump', 'turbine') if no connected machine
         *     matches the dataset. The backend will create/reuse a hidden
         *     dataset machine for you.
         */
        async runPredictionFromDataset(filename, machineId, options) {
            options = options || {};
            const body = {
                filename,
                horizon: options.horizon || 30,
                model_type: options.model || 'auto',
                machine_key: options.machineKey || null,
                dataset_hint: options.datasetHint || null,
                device_id: this._state.getDeviceId(),
            };
            if (machineId) {
                body.machine_id = machineId;
            } else if (options.machineType) {
                body.machine_type = options.machineType;
            } else {
                throw new Error('Either machine_id or machine_type is required for dataset prediction.');
            }
            const data = await this._request('/api/v1/predictions/predict-dataset', {
                method: 'POST', body,
            });
            this._logActivity('prediction_dataset', 'Prediction from dataset: ' + filename);
            return data;
        }

        async getPredictionHistory(machineId, page, perPage) {
            const qs = [];
            if (machineId) qs.push('machine_id=' + encodeURIComponent(machineId));
            if (page) qs.push('page=' + page);
            if (perPage) qs.push('per_page=' + perPage);
            const url = '/api/v1/predictions/history' + (qs.length ? '?' + qs.join('&') : '');
            return this._request(url, { method: 'GET' });
        }

        async getPredictionStats() {
            return this._request('/api/v1/predictions/stats', { method: 'GET' });
        }

        async savePrediction(payload) {
            return this._request('/api/v1/predictions', { method: 'POST', body: payload });
        }

        // ========================================================
        // ALERTS
        // ========================================================

        async getAlerts(params) {
            const qs = params ? ('?' + new URLSearchParams(params).toString()) : '';
            return this._request('/api/v1/alerts' + qs, { method: 'GET' });
        }
        async getAlert(alertId) {
            return this._request('/api/v1/alerts/' + encodeURIComponent(alertId), { method: 'GET' });
        }
        async createAlert(alertData) {
            const data = await this._request('/api/v1/alerts', {
                method: 'POST', body: alertData,
            });
            if (alertData.severity === 'critical' || alertData.severity === 'high') {
                this._sendAlertEmail(alertData);
            }
            return data;
        }
        async resolveAlert(alertId, notes) {
            return this._request('/api/v1/alerts/' + encodeURIComponent(alertId) + '/resolve', {
                method: 'POST', body: { notes: notes || '' },
            });
        }
        async acknowledgeAlert(alertId) {
            return this._request('/api/v1/alerts/' + encodeURIComponent(alertId) + '/acknowledge', {
                method: 'POST',
            });
        }
        async escalateAlert(alertId) {
            return this._request('/api/v1/alerts/' + encodeURIComponent(alertId) + '/escalate', {
                method: 'POST',
            });
        }
        async markAllAlertsRead() {
            return this._request('/api/v1/alerts/mark-all-read', { method: 'POST' });
        }

        // ========================================================
        // REPORTS
        // ========================================================

        async getReports() {
            return this._request('/api/v1/reports', { method: 'GET' });
        }
        async generateReport(reportData) {
            const data = await this._request('/api/v1/reports/generate', {
                method: 'POST', body: reportData,
            });
            this._logActivity('generate_report', 'Generated report: ' + (reportData && reportData.name));
            return data;
        }
        async saveReport(reportData) {
            return this._request('/api/v1/reports', { method: 'POST', body: reportData });
        }
        async getReport(reportId) {
            return this._request('/api/v1/reports/' + encodeURIComponent(reportId), { method: 'GET' });
        }
        async downloadReport(reportId) {
            return this._requestBlob(
                '/api/v1/reports/' + encodeURIComponent(reportId) + '/download',
                'report'
            );
        }

        // ========================================================
        // PAYMENTS
        // ========================================================

        async getPaymentPlans() {
            return this._request('/api/v1/payments/plans', { method: 'GET' });
        }
        async getPaddleConfig() {
            return this._request('/api/v1/payments/paddle-config', { method: 'GET' });
        }
        async createCheckout(planId, gateway) {
            return this._request('/api/v1/billing/create-checkout', {
                method: 'POST',
                body: {
                    plan_id: planId,
                    plan_name: planId,
                    gateway: gateway || 'paddle',
                    currency: 'USD',
                    success_url: window.location.origin + '/payment-success.html',
                    cancel_url:  window.location.origin + '/payment-cancel.html',
                    user_id: this._state.user ? this._state.user.id : null,
                    device_id: this._state.getDeviceId(),
                },
            });
        }
        async getSubscription() {
            return this._request('/api/v1/billing/subscription', { method: 'GET' });
        }
        async cancelSubscription() {
            const data = await this._request('/api/v1/payments/cancel', { method: 'POST' });
            this._logActivity('cancel_subscription', 'Subscription cancelled');
            return data;
        }
        async getInvoices() {
            return this._request('/api/v1/billing/invoices', { method: 'GET' });
        }
        async getBillingUsage() {
            return this._request('/api/v1/billing/usage', { method: 'GET' });
        }
        async getBillingStats() {
            return this._request('/api/v1/billing/stats', { method: 'GET' });
        }
        async getPaymentMethods() {
            return this._request('/api/v1/billing/payment-methods', { method: 'GET' });
        }
        async submitEnterpriseRequest(payload) {
            return this._request('/api/v1/billing/enterprise-request', {
                method: 'POST', body: payload,
            });
        }
        async verifyPayment(paymentUuid) {
            return this._request('/api/v1/payments/verify/' + encodeURIComponent(paymentUuid), {
                method: 'GET',
            });
        }

        // ========================================================
        // EMAIL (backend-mediated)
        // ========================================================

        async _sendEmail(emailData) {
            try {
                return await this._request('/api/v1/email/send', {
                    method: 'POST',
                    body: {
                        to: emailData.to,
                        subject: emailData.subject,
                        template: emailData.template,
                        data: emailData.data,
                    },
                });
            } catch (error) {
                console.error('Email send error:', error);
                return { success: false };
            }
        }

        async _sendAlertEmail(alertData) {
            if (!this._state.user || !this._state.user.email) return;
            this._sendEmail({
                to: this._state.user.email,
                subject: 'CRITICAL ALERT: ' + alertData.title,
                template: 'alert',
                data: {
                    title: alertData.title,
                    description: alertData.description,
                    severity: alertData.severity,
                    machine: alertData.machine_name || 'Unknown Machine',
                    timestamp: new Date().toISOString(),
                    action: alertData.action || 'Schedule maintenance immediately',
                    user_name: this._state.user.name || this._state.user.email,
                },
            });
        }

        // ========================================================
        // AUDIT
        // ========================================================

        _logActivity(action, description) {
            // Fire-and-forget: audit telemetry must not delay or block the user action.
            try {
                this._request('/api/v1/audit/log', {
                    method: 'POST',
                    body: {
                        action, description,
                        user_id: this._state.user ? this._state.user.id : 'unknown',
                        user_email: this._state.user ? this._state.user.email : 'unknown',
                        user_agent: (typeof navigator !== 'undefined' ? navigator.userAgent : ''),
                        device_id: this._state.getDeviceId(),
                        timestamp: new Date().toISOString(),
                    },
                }).catch(() => {});
            } catch (error) {}
        }

        // ========================================================
        // USER PROFILE
        // ========================================================

        async getProfile() {
            return this._request('/api/v1/user/profile', { method: 'GET' });
        }

        async updateProfile(data) {
            const result = await this._request('/api/v1/user/profile', {
                method: 'PUT', body: data,
            });
            if (result.success && result.user) {
                this._state.setUser(result.user);
                this._logActivity('update_profile', 'Profile updated');
            }
            return result;
        }

        async changePassword(oldPassword, newPassword) {
            const result = await this._request('/api/v1/user/change-password', {
                method: 'POST',
                body: {
                    old_password: oldPassword,
                    current_password: oldPassword,
                    new_password: newPassword,
                    device_id: this._state.getDeviceId(),
                },
            });
            this._logActivity('change_password', 'Password changed');
            return result;
        }

        // ========================================================
        // AVATAR
        // ========================================================

        async uploadAvatar(file) {
            const formData = new FormData();
            formData.append('avatar', file);
            formData.append('device_id', this._state.getDeviceId());

            const data = await this._request('/api/v1/user/avatar', {
                method: 'POST',
                body: formData,
            });

            if (data && data.avatar_url && this._state.user) {
                this._state.user.avatar_url = data.avatar_url;
                writeUser(this._state.user);
                this._state._notifyListeners();
            }
            this._logActivity('upload_avatar', 'Avatar uploaded');
            return data;
        }

        async removeAvatar() {
            const data = await this._request('/api/v1/user/avatar', { method: 'DELETE' });
            if (this._state.user) {
                this._state.user.avatar_url = null;
                writeUser(this._state.user);
                this._state._notifyListeners();
            }
            this._logActivity('remove_avatar', 'Avatar removed');
            return data || { success: true };
        }

        // ========================================================
        // TENANT
        // ========================================================

        async getTenants() {
            return this._request('/api/v1/tenants', { method: 'GET' });
        }

        async switchTenant(tenantId) {
            const data = await this._request('/api/v1/tenant/switch', {
                method: 'POST',
                body: { tenant_id: tenantId, device_id: this._state.getDeviceId() },
            });
            if (data.success) {
                if (data.tenant) this._state.setTenant(data.tenant);
                if (data.session) {
                    this._state.setSession(data.session);
                    this._state.addSession(data.session);
                }
                this._logActivity('switch_tenant', 'Switched to tenant: ' + tenantId);
            }
            return data;
        }

        // ========================================================
        // DOWNLOADS
        // ========================================================

        async getDownloadLinks() {
            return this._request('/api/v1/downloads', { method: 'GET' });
        }
        async downloadDesktopApp(os) {
            os = os || 'windows';
            return this._requestBlob(
                '/api/v1/downloads/desktop/' + encodeURIComponent(os),
                'SynapsePM-' + os
            );
        }
        async downloadMobileApp(os) {
            os = os || 'android';
            return this._requestBlob(
                '/api/v1/downloads/mobile/' + encodeURIComponent(os),
                'SynapsePM-' + os
            );
        }

        // ========================================================
        // CONTACT & APPLICATIONS
        // ========================================================

        async submitContact(formData) {
            const data = await this._request('/api/v1/contact', {
                method: 'POST',
                body: {
                    first_name: formData.first_name,
                    last_name:  formData.last_name,
                    full_name:  ((formData.first_name || '') + ' ' + (formData.last_name || '')).trim(),
                    email:      formData.email,
                    company:    formData.company || '',
                    subject:    formData.subject,
                    message:    formData.message,
                    device_id:  this._state.getDeviceId(),
                },
            });
            this._logActivity('contact_submit', 'Contact form submitted');
            return data;
        }

        async submitApplication(formData) {
            const data = await this._request('/api/v1/applications', {
                method: 'POST', body: formData,
            });
            this._logActivity('application_submit', 'Job application submitted: ' + (formData && formData.position));
            return data;
        }

        async getApplications() {
            return this._request('/api/v1/applications', { method: 'GET' });
        }

        // ========================================================
        // DATASETS
        // ========================================================

        async getDatasets() {
            return this._request('/api/v1/datasets', { method: 'GET' });
        }

        async uploadDataset(file) {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('device_id', this._state.getDeviceId());
            return this._request('/api/v1/datasets/upload', {
                method: 'POST', body: formData,
            });
        }

        async analyzeDataset(filename) {
            return this._request('/api/v1/datasets/analyze', {
                method: 'POST', body: { filename },
            });
        }

        // ========================================================
        // PERMISSION HELPERS
        // ========================================================

        can(permission)       { return this._state.hasPermission(permission); }
        canAccess(feature)    { return this._state.hasFeature(feature); }
        getFeatureStatus(f)   { return this._state.getFeatureStatus(f); }

        // ========================================================
        // RAW FETCH HELPERS (for pages that need raw fetch)
        // ========================================================

        /**
         * authFetch — returns a raw Response. Handles 401-refresh-retry
         * exactly once. Useful when you need to inspect headers or stream
         * the response body yourself.
         */
        async authFetch(endpoint, options = {}, _retried = false) {
            const token = this._state.token || getStoredToken();
            const headers = { ...(options.headers || {}) };
            if (token) headers['Authorization'] = 'Bearer ' + token;
            const timeoutMs = Number(options.timeout || 30000);
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeoutMs);
            try {
                const url = /^https?:\/\//i.test(endpoint) ? endpoint : this._url(endpoint);
                const fetchOptions = { ...options, headers,
                    credentials: options.credentials || 'same-origin',
                    cache: options.cache || 'no-store', signal: controller.signal };
                delete fetchOptions.timeout;
                const response = await fetch(url, fetchOptions);
                if (response.status === 401 && !_retried) {
                    const ok = await performRefresh();
                    if (ok) return this.authFetch(endpoint, options, true);
                    this._state.logout('Session expired');
                    throw new Error('Authentication required');
                }
                return response;
            } catch (err) {
                if (err && err.name === 'AbortError') {
                    const timeoutError = new Error('Request timed out after ' + (timeoutMs / 1000) + 's.');
                    timeoutError.status = 0;
                    throw timeoutError;
                }
                throw err;
            } finally {
                clearTimeout(timer);
            }
        }

        /**
         * authDownload — fetch a file with 401-refresh-retry, then
         * save it as a download.
         */
        async authDownload(endpoint, fallbackName) {
            const response = await this.authFetch(endpoint, { method: 'GET' });
            if (!response.ok) {
                let err = {};
                try { err = await response.json(); } catch (e) {}
                const ex = new Error(err.error || err.message || ('Download failed (' + response.status + ')'));
                ex.status = response.status;
                ex.data = err;
                throw ex;
            }
            const contentType = response.headers.get('content-type') || '';
            if (contentType.toLowerCase().includes('application/json')) {
                let err = {};
                try { err = await response.json(); } catch (e) {}
                const ex = new Error(err.error || err.message || 'Server returned JSON instead of a downloadable file.');
                ex.status = response.status;
                ex.data = err;
                throw ex;
            }
            const cd = response.headers.get('Content-Disposition') || '';
            let filename = fallbackName || 'download.bin';
            const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^\";]+)"?/i);
            if (m && m[1]) {
                try {
                    filename = decodeURIComponent(m[1].replace(/["']/g, ''))
                        .replace(/[\\/:*?"<>|]/g, '_');
                } catch {}
            }
            const blob = await response.blob();
            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
            return { success: true, filename };
        }

        // ========================================================
        // BLOB DOWNLOAD (internal, same as authDownload)
        // ========================================================

        async _requestBlob(endpoint, fallbackName) {
            return this.authDownload(endpoint, fallbackName);
        }
    }

    // ============================================================
    // ROUTE GUARD
    // ============================================================

    class AuthGuard {
        constructor(state, api) {
            this._state = state;
            this._api = api;
            this._pendingCheck = null;
        }

        requireAuth() {
            if (!this._state.isAuthenticated) {
                try { localStorage.setItem(AUTH_CONFIG.REDIRECT_KEY, window.location.pathname); } catch (e) {}
                window.location.href = 'login.html';
                return false;
            }

            if (!this._pendingCheck) {
                this._pendingCheck = this._api.checkPasswordExpiry().then(result => {
                    this._pendingCheck = null;
                    if (result && result.expired && !window.location.pathname.includes('change-password.html')) {
                        try { localStorage.setItem('password_expired', 'true'); } catch (e) {}
                        window.location.href = 'change-password.html?expired=true';
                        return false;
                    }
                    return true;
                });
            }
            return true;
        }

        requireRegistered() { return this.requireAuth(); }

        requireMFA() {
            if (this._state.isMFARequired) {
                window.location.href = 'mfa-verify.html';
                return false;
            }
            return true;
        }

        requireAdmin() {
            if (!this.requireRegistered()) return false;
            if (!this._state.isAdmin) {
                window.location.href = 'dashboard.html';
                return false;
            }
            return true;
        }

        requireSuperAdmin() {
            if (!this.requireRegistered()) return false;
            if (!this._state.isSuperAdmin) {
                window.location.href = 'dashboard.html';
                return false;
            }
            return true;
        }

        requirePermission(permission) {
            if (!this.requireRegistered()) return false;
            if (!this._state.hasPermission(permission)) {
                window.location.href = 'unauthorized.html';
                return false;
            }
            return true;
        }

        requireFeature(feature) {
            if (!this.requireRegistered()) return false;
            if (!this._state.hasFeature(feature)) {
                this._state._showToast('This feature requires an upgrade', 'warning');
                window.location.href = 'pricing.html';
                return false;
            }
            return true;
        }

        redirectIfAuthenticated() {
            // Login pages must remain visible when switching between user/admin
            // accounts in the same browser. Previously a stale token bounced the
            // user straight to the user dashboard before the form could be used.
            const path = (window.location && window.location.pathname || '').toLowerCase();
            if (/(^|\/)login(?:\.html)?$/.test(path)) return false;

            if (this._state.isAuthenticated) {
                const user = this._state.user || {};
                const role = String(user.role || '').toLowerCase();
                const isGlobalAdmin = ['super_admin', 'admin'].includes(role);
                const redirect = _safeRedirect(
                    (function () { try { return localStorage.getItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) { return null; } })()
                    || (isGlobalAdmin ? '/admin/dashboard.html' : '/dashboard.html')
                );
                try { localStorage.removeItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) {}
                window.location.href = redirect;
                return true;
            }
            return false;
        }

        requireVerified() {
            if (!this.requireAuth()) return false;
            if (this._state.user && this._state.user.email_verified === false) {
                window.location.href = 'verify-email.html';
                return false;
            }
            return true;
        }
    }

    // ============================================================
    // BOOTSTRAP
    // ============================================================

    const AuthState = new AuthStateManager();
    const AuthAPI = new AuthAPIClient(AuthState);
    const AuthGuardInstance = new AuthGuard(AuthState, AuthAPI);

    // ============================================================
    // GLOBAL HELPERS
    // ============================================================

    function updateUserInfo() {
        const user = AuthState.user;
        if (!user) return;

        const name = user.display_name || user.full_name || user.name
            || (user.email ? user.email.split('@')[0] : 'User');
        const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();

        document.querySelectorAll('.user-name').forEach(el => { el.textContent = name; });
        document.querySelectorAll('.user-email').forEach(el => { el.textContent = user.email || ''; });
        document.querySelectorAll('.welcome-name').forEach(el => { el.textContent = name.split(' ')[0]; });
        document.querySelectorAll('.user-plan').forEach(el => { el.textContent = user.plan || 'Free'; });

        document.querySelectorAll('.user-avatar').forEach(el => {
            if (user.avatar_url) {
                el.style.backgroundImage = 'url(' + user.avatar_url + ')';
                el.style.backgroundSize = 'cover';
                el.textContent = '';
            } else {
                el.textContent = initials;
            }
        });
    }

    function handleSocialCallback() {
        AuthAPI.handleSocialCallback();
    }

    async function checkBackendHealth(silent) {
        try {
            const h = await AuthAPI.health();
            if (!h || h.status === 'unreachable') {
                if (!silent) AuthState._showToast('⚠️ Cannot reach backend', 'error');
                return false;
            }
            if (h.status !== 'healthy') {
                const msg = [];
                if (h.database === false) msg.push('DB down');
                if (h.redis === false) msg.push('Redis down');
                AuthState._showToast('⚠️ Backend degraded: ' + (msg.join(' · ') || h.status), 'warning', 8000);
                return false;
            }
            return true;
        } catch (e) {
            return false;
        }
    }

    // ============================================================
    // EXPOSE window.Auth
    // ============================================================

    global.Auth = {
        // State getters
        get user()            { return AuthState.user; },
        get token()           { return AuthState.token; },
        get isAuthenticated() { return AuthState.isAuthenticated; },
        get isAdmin()         { return AuthState.isAdmin; },
        get isSuperAdmin()    { return AuthState.isSuperAdmin; },
        get plan()            { return AuthState.plan; },
        get permissions()     { return AuthState.permissions; },
        get isMFARequired()   { return AuthState.isMFARequired; },
        get deviceId()        { return AuthState.getDeviceId(); },
        get activeSessions()  { return AuthState.getActiveSessions(); },
        get isLocked()        { return AuthState.isLocked(); },
        get lockoutRemaining(){ return AuthState.getLockoutRemaining(); },
        get config()          { return AUTH_CONFIG; },

        // Token helpers
        getToken: () => AuthState.token || getStoredToken(),
        getRefresh: () => AuthState.refresh || getStoredRefresh(),
        getUser: () => AuthState.user || getStoredUser(),
        getTenant: () => AuthState.tenant || getStoredTenant(),
        clearAuth: () => AuthState.clear(),
        isTokenValid,
        isTokenExpired,
        decodeJwt,

        // Auth
        login: AuthAPI.login.bind(AuthAPI),
        verifyMFA: AuthAPI.verifyMFA.bind(AuthAPI),
        register: AuthAPI.register.bind(AuthAPI),
        logout: AuthAPI.logout.bind(AuthAPI),
        sendOTP: AuthAPI.sendOTP.bind(AuthAPI),
        verifyOTP: AuthAPI.verifyOTP.bind(AuthAPI),
        resetPassword: AuthAPI.resetPassword.bind(AuthAPI),
        forgotPassword: AuthAPI.forgotPassword.bind(AuthAPI),
        socialLogin: AuthAPI.socialLogin.bind(AuthAPI),
        handleSocialCallback,

        // Sessions
        revokeAllSessions: AuthAPI.revokeAllSessions.bind(AuthAPI),
        revokeSession: AuthAPI.revokeSession.bind(AuthAPI),
        getActiveSessions: AuthAPI.getActiveSessions.bind(AuthAPI),
        getActiveSessionsCount: AuthAPI.getActiveSessionsCount.bind(AuthAPI),

        // MFA
        generateBackupCodes: AuthAPI.generateBackupCodes.bind(AuthAPI),
        verifyBackupCode: AuthAPI.verifyBackupCode.bind(AuthAPI),

        // Password
        checkPasswordExpiry: AuthAPI.checkPasswordExpiry.bind(AuthAPI),
        changePassword: AuthAPI.changePassword.bind(AuthAPI),

        // Dashboard helpers
        redirectToLogin: AuthAPI.redirectToLogin.bind(AuthAPI),
        redirectToSignup: AuthAPI.redirectToSignup.bind(AuthAPI),
        redirectToDashboard: AuthAPI.redirectToDashboard.bind(AuthAPI),
        isAuthenticatedMethod: AuthAPI.isAuthenticated.bind(AuthAPI),
        getRedirectUrl: AuthAPI.getRedirectUrl.bind(AuthAPI),

        // Health
        health: AuthAPI.health.bind(AuthAPI),
        checkBackendHealth,

        // Machines
        getMachines: AuthAPI.getMachines.bind(AuthAPI),
        addMachine: AuthAPI.addMachine.bind(AuthAPI),
        updateMachine: AuthAPI.updateMachine.bind(AuthAPI),
        deleteMachine: AuthAPI.deleteMachine.bind(AuthAPI),
        connectMachine: AuthAPI.connectMachine.bind(AuthAPI),
        simulateMachine: AuthAPI.simulateMachine.bind(AuthAPI),
        machinePredict: AuthAPI.machinePredict.bind(AuthAPI),
        createMachineDeviceKey: AuthAPI.createMachineDeviceKey.bind(AuthAPI),
        listMachineDeviceKeys: AuthAPI.listMachineDeviceKeys.bind(AuthAPI),
        revokeMachineDeviceKey: AuthAPI.revokeMachineDeviceKey.bind(AuthAPI),
        getMachineSensorData: AuthAPI.getMachineSensorData.bind(AuthAPI),

        // Predictions
        runPrediction: AuthAPI.runPrediction.bind(AuthAPI),
        runPredictionFromDataset: AuthAPI.runPredictionFromDataset.bind(AuthAPI),
        getPredictionHistory: AuthAPI.getPredictionHistory.bind(AuthAPI),
        getPredictionStats: AuthAPI.getPredictionStats.bind(AuthAPI),
        savePrediction: AuthAPI.savePrediction.bind(AuthAPI),

        // Alerts
        getAlerts: AuthAPI.getAlerts.bind(AuthAPI),
        getAlert: AuthAPI.getAlert.bind(AuthAPI),
        createAlert: AuthAPI.createAlert.bind(AuthAPI),
        resolveAlert: AuthAPI.resolveAlert.bind(AuthAPI),
        acknowledgeAlert: AuthAPI.acknowledgeAlert.bind(AuthAPI),
        escalateAlert: AuthAPI.escalateAlert.bind(AuthAPI),
        markAllAlertsRead: AuthAPI.markAllAlertsRead.bind(AuthAPI),

        // Reports
        getReports: AuthAPI.getReports.bind(AuthAPI),
        generateReport: AuthAPI.generateReport.bind(AuthAPI),
        saveReport: AuthAPI.saveReport.bind(AuthAPI),
        getReport: AuthAPI.getReport.bind(AuthAPI),
        downloadReport: AuthAPI.downloadReport.bind(AuthAPI),

        // Payments
        getPaymentPlans: AuthAPI.getPaymentPlans.bind(AuthAPI),
        getPaddleConfig: AuthAPI.getPaddleConfig.bind(AuthAPI),
        createCheckout: AuthAPI.createCheckout.bind(AuthAPI),
        getSubscription: AuthAPI.getSubscription.bind(AuthAPI),
        cancelSubscription: AuthAPI.cancelSubscription.bind(AuthAPI),
        getInvoices: AuthAPI.getInvoices.bind(AuthAPI),
        getBillingUsage: AuthAPI.getBillingUsage.bind(AuthAPI),
        getBillingStats: AuthAPI.getBillingStats.bind(AuthAPI),
        getPaymentMethods: AuthAPI.getPaymentMethods.bind(AuthAPI),
        submitEnterpriseRequest: AuthAPI.submitEnterpriseRequest.bind(AuthAPI),
        verifyPayment: AuthAPI.verifyPayment.bind(AuthAPI),

        // Profile
        getProfile: AuthAPI.getProfile.bind(AuthAPI),
        updateProfile: AuthAPI.updateProfile.bind(AuthAPI),
        uploadAvatar: AuthAPI.uploadAvatar.bind(AuthAPI),
        removeAvatar: AuthAPI.removeAvatar.bind(AuthAPI),

        // Tenant
        getTenants: AuthAPI.getTenants.bind(AuthAPI),
        switchTenant: AuthAPI.switchTenant.bind(AuthAPI),

        // Downloads
        getDownloadLinks: AuthAPI.getDownloadLinks.bind(AuthAPI),
        downloadDesktopApp: AuthAPI.downloadDesktopApp.bind(AuthAPI),
        downloadMobileApp: AuthAPI.downloadMobileApp.bind(AuthAPI),

        // Datasets
        getDatasets: AuthAPI.getDatasets.bind(AuthAPI),
        uploadDataset: AuthAPI.uploadDataset.bind(AuthAPI),
        analyzeDataset: AuthAPI.analyzeDataset.bind(AuthAPI),

        // Contact & Applications
        submitContact: AuthAPI.submitContact.bind(AuthAPI),
        submitApplication: AuthAPI.submitApplication.bind(AuthAPI),
        getApplications: AuthAPI.getApplications.bind(AuthAPI),

        // Guard
        requireAuth: AuthGuardInstance.requireAuth.bind(AuthGuardInstance),
        requireRegistered: AuthGuardInstance.requireRegistered.bind(AuthGuardInstance),
        requireMFA: AuthGuardInstance.requireMFA.bind(AuthGuardInstance),
        requireAdmin: AuthGuardInstance.requireAdmin.bind(AuthGuardInstance),
        requireSuperAdmin: AuthGuardInstance.requireSuperAdmin.bind(AuthGuardInstance),
        requirePermission: AuthGuardInstance.requirePermission.bind(AuthGuardInstance),
        requireFeature: AuthGuardInstance.requireFeature.bind(AuthGuardInstance),
        redirectIfAuthenticated: AuthGuardInstance.redirectIfAuthenticated.bind(AuthGuardInstance),
        requireVerified: AuthGuardInstance.requireVerified.bind(AuthGuardInstance),

        // Permissions
        can: AuthAPI.can.bind(AuthAPI),
        canAccess: AuthAPI.canAccess.bind(AuthAPI),
        getFeatureStatus: AuthAPI.getFeatureStatus.bind(AuthAPI),

        // UI
        updateUserInfo,
        showToast: AuthState._showToast.bind(AuthState),

        // Listeners
        onAuthChange: AuthState.addListener.bind(AuthState),
        removeAuthListener: AuthState.removeListener.bind(AuthState),

        // WS token-refresh helper for pages
        registerTokenRefreshListener(handler) {
            if (typeof handler !== 'function') return;
            window.addEventListener('synapse:token-refreshed', handler);
            return () => window.removeEventListener('synapse:token-refreshed', handler);
        },

        // Manual WS rebuild
        rebuildWebSocket() {
            AuthState._disconnectWebSocket();
            AuthState._connectWebSocket();
        },

        // Expose raw fetch helpers
        authFetch: AuthAPI.authFetch.bind(AuthAPI),
        authDownload: AuthAPI.authDownload.bind(AuthAPI),
        onAdminDataChanged(callback) {
            if (typeof callback !== 'function') return () => {};
            const handler = (event) => callback(event.detail || {});
            window.addEventListener('synapse:admin-data-changed', handler);
            return () => window.removeEventListener('synapse:admin-data-changed', handler);
        },
        onSystemStatusChanged(callback) {
            if (typeof callback !== 'function') return () => {};
            const handler = (event) => callback(event.detail || {});
            window.addEventListener('synapse:system-status-changed', handler);
            return () => window.removeEventListener('synapse:system-status-changed', handler);
        },
    };

    // ============================================================
    // AUTO-INIT ON DOM READY
    // ============================================================

    document.addEventListener('DOMContentLoaded', () => {
        if (AuthState.isAuthenticated) {
            updateUserInfo();

            AuthAPI.checkPasswordExpiry().then(result => {
                if (result && result.expired
                    && !window.location.pathname.includes('change-password.html')) {
                    try { localStorage.setItem('password_expired', 'true'); } catch (e) {}
                    window.location.href = 'change-password.html?expired=true';
                } else if (result && !result.expired && result.days_remaining <= 7) {
                    AuthState._showToast(result.message, 'warning');
                }
            }).catch(() => {});

            checkBackendHealth(true).catch(() => {});
        }

        let pending = null;
        try { pending = localStorage.getItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) {}
        if (pending && AuthState.isAuthenticated) {
            try { localStorage.removeItem(AUTH_CONFIG.REDIRECT_KEY); } catch (e) {}
            window.location.href = _safeRedirect(pending);
            return;
        }

        document.querySelectorAll('.password-toggle').forEach(toggle => {
            toggle.addEventListener('click', function () {
                const wrapper = this.closest('.password-wrapper')
                    || this.closest('.password-field')
                    || this.parentElement;
                const input = wrapper ? wrapper.querySelector('input') : null;
                if (!input) return;
                const isPassword = input.type === 'password';
                input.type = isPassword ? 'text' : 'password';
                const icon = this.querySelector('.material-symbols-outlined') || this.querySelector('i');
                if (icon) icon.textContent = isPassword ? 'visibility' : 'visibility_off';
            });
        });

        document.querySelectorAll('.social-btn[data-provider]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const provider = btn.dataset.provider;
                if (!provider) return;
                btn.disabled = true;
                try { sessionStorage.setItem(AUTH_CONFIG.OAUTH_PROVIDER, provider); } catch (e) {}
                try {
                    await AuthAPI.socialLogin(provider);
                } catch (err) {
                    AuthState._showToast(err.message || 'Social login failed', 'error');
                    btn.disabled = false;
                }
            });
        });

        document.querySelectorAll('[data-social-login]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const provider = btn.dataset.socialLogin;
                if (!provider) return;
                const original = btn.innerHTML;
                btn.innerHTML = 'Connecting...';
                btn.disabled = true;
                try {
                    await AuthAPI.socialLogin(provider);
                } catch (err) {
                    AuthState._showToast(err.message || 'Social login failed', 'error');
                    btn.innerHTML = original;
                    btn.disabled = false;
                }
            });
        });

        document.querySelectorAll('[data-logout]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const revokeAll = btn.dataset.revokeAll === 'true';
                try { await AuthAPI.logout(revokeAll); } catch (e) {}
                window.location.href = 'login.html';
            });
        });

        const path = window.location.pathname || '';
        if (/auth-success(\.html)?$/i.test(path)) {
            AuthAPI.handleSocialCallback();
        }

        console.log('✅ SynapsePM auth.js v10.0.0 initialized');
        console.log('   Authenticated:', AuthState.isAuthenticated);
        console.log('   Plan:', AuthState.plan);
        console.log('   Device:', AuthState.getDeviceId());
    });

    window.addEventListener('beforeunload', () => {
        try {
            if (AuthState._wsConnection) AuthState._wsConnection.close();
        } catch (e) {}
    });

    console.log('✅ SynapsePM auth.js v10.0.0 loaded');

})(window);