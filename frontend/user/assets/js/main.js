// ============================================
// SYNAPSEPM - COMPLETE JAVASCRIPT
// Enterprise SaaS Platform | All 23+ Pages
// Version: 3.0.0
// ============================================

(function() {
    'use strict';

    // ============================================
    // CONFIGURATION
    // ============================================
    
    const CONFIG = {
        // API Configuration
        API: {
            BASE_URL: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
                ? 'http://localhost:3000/api/v1'
                : 'https://api.synapsepm.com/v1',
            TIMEOUT: 30000,
            RETRY_ATTEMPTS: 3,
            RETRY_DELAY: 1000,
        },
        
        // Authentication
        AUTH: {
            TOKEN_KEY: 'synapse_access_token',
            REFRESH_KEY: 'synapse_refresh_token',
            USER_KEY: 'synapse_user',
            ADMIN_TOKEN_KEY: 'synapse_admin_token',
            ADMIN_REFRESH_KEY: 'synapse_admin_refresh',
            ADMIN_USER_KEY: 'synapse_admin_user',
            SESSION_TIMEOUT: 3600000,
            REFRESH_BUFFER: 300000,
            MAX_LOGIN_ATTEMPTS: 5,
            LOCKOUT_DURATION: 5,
            ADMIN_LOCKOUT_DURATION: 60,
        },
        
        // Application
        APP: {
            NAME: 'SynapsePM',
            SUPPORT_EMAIL: 'support@synapsepm.com',
            SALES_EMAIL: 'sales@synapsepm.com',
            DEFAULT_REDIRECT: 'dashboard.html',
            ADMIN_REDIRECT: 'admin/dashboard.html',
            VERSION: '3.0.0',
            COMPANY_ADDRESS: '205 ½ N Main St., Ann Arbor, MI 48104',
            COMPANY_PHONE: '+1 (555) 123-4567',
        },
        
        // Routes - All 23+ Pages
        ROUTES: {
            PUBLIC: [
                'index.html',
                'login.html',
                'signup.html',
                'forgot-password.html',
                'reset-password.html',
                '404.html',
                '500.html',
                'about.html',
                'contact.html',
                'privacy.html',
                'terms.html',
                'security.html',
                'docs.html',
                'explore.html',
                'demo.html',
                'blog.html',
                'careers.html',
                'faq.html',
                'pricing.html'
            ],
            PROTECTED: [
                'dashboard.html',
                'machines.html',
                'machine-detail.html',
                'machine-details.html',
                'predictions.html',
                'prediction-details.html',
                'alerts.html',
                'reports.html',
                'profile.html',
                'settings.html',
                'billing.html',
                'payment.html',
                'api-keys.html',
                'team.html',
                'activity.html',
                'notifications.html',
                'integrations.html'
            ],
            ADMIN: [
                'admin/login.html',
                'admin/dashboard.html',
                'admin/users.html',
                'admin/user-detail.html',
                'admin/organizations.html',
                'admin/machines.html',
                'admin/analytics.html',
                'admin/audit-logs.html',
                'admin/settings.html',
                'admin/backup.html',
                'admin/logs.html',
                'admin/monitoring.html',
                'admin/reports.html'
            ]
        },
        
        // Validation Rules
        VALIDATION: {
            PASSWORD_MIN_LENGTH: 8,
            PASSWORD_MAX_LENGTH: 128,
            NAME_MIN_LENGTH: 2,
            NAME_MAX_LENGTH: 50,
            COMPANY_MIN_LENGTH: 2,
            COMPANY_MAX_LENGTH: 100,
            PHONE_REGEX: /^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$/,
            EMAIL_REGEX: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
            URL_REGEX: /^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$/,
        },
        
        // Features
        FEATURES: {
            ENABLE_MFA: true,
            ENABLE_SOCIAL_LOGIN: true,
            ENABLE_REMEMBER_ME: true,
            ENABLE_PASSWORD_STRENGTH: true,
            ENABLE_NOTIFICATIONS: true,
            ENABLE_REAL_TIME_UPDATES: true,
            AUTO_REFRESH_INTERVAL: 30000,
            DEMO_MODE: false,
        },
        
        // Plans
        PLANS: {
            FREE: { name: 'Free', price: 0, machines: 1, predictions: 100, support: 'Email', days: 10 },
            SMALL: { name: 'Small Business', price: 150, machines: 25, predictions: 1000, support: 'Email 24h' },
            MEDIUM: { name: 'Medium Business', price: 300, machines: 100, predictions: 5000, support: 'Priority 4h' },
            LARGE: { name: 'Large Enterprise', price: 500, machines: 'Unlimited', predictions: 'Unlimited', support: '24/7 Dedicated' },
            STARTER: { name: 'Starter', price: 99, machines: 25, predictions: 1000, support: 'Email 24h' },
            PROFESSIONAL: { name: 'Professional', price: 299, machines: 100, predictions: 'Unlimited', support: 'Priority 4h' },
            ENTERPRISE: { name: 'Enterprise', price: 'Custom', machines: 'Unlimited', predictions: 'Unlimited', support: '24/7 Dedicated' }
        },
        
        // Machine Types
        MACHINE_TYPES: [
            { id: 'turbine', name: 'Industrial Turbine', icon: 'fan' },
            { id: 'pump', name: 'Centrifugal Pump', icon: 'water' },
            { id: 'compressor', name: 'Air Compressor', icon: 'wind' },
            { id: 'motor', name: 'Electric Motor', icon: 'bolt' },
            { id: 'generator', name: 'Power Generator', icon: 'bolt' },
            { id: 'fan', name: 'Industrial Fan', icon: 'fan' },
            { id: 'conveyor', name: 'Conveyor System', icon: 'cogs' },
            { id: 'robot', name: 'Industrial Robot', icon: 'robot' },
            { id: 'hvac', name: 'HVAC System', icon: 'snowflake' },
            { id: 'other', name: 'Other Equipment', icon: 'industry' }
        ],
        
        // Environment
        ENV: {
            isDevelopment: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1',
            isStaging: window.location.hostname.includes('staging'),
            isProduction: !window.location.hostname.includes('localhost') && !window.location.hostname.includes('staging'),
        },
        
        // Date Formats
        DATE_FORMATS: {
            DISPLAY: 'MMM DD, YYYY',
            DISPLAY_TIME: 'MMM DD, YYYY HH:mm',
            ISO: 'YYYY-MM-DD',
            API: 'YYYY-MM-DDTHH:mm:ss.SSSZ',
        },
        
        // Default Settings
        DEFAULTS: {
            TIMEZONE: 'America/New_York',
            LANGUAGE: 'en',
            CURRENCY: 'USD',
        },
        
        // Pagination
        PAGINATION: {
            DEFAULT_PAGE_SIZE: 20,
            MAX_PAGE_SIZE: 100,
        },
        
        // File Upload
        UPLOAD: {
            MAX_FILE_SIZE: 10 * 1024 * 1024,
            ALLOWED_TYPES: ['image/jpeg', 'image/png', 'image/gif', 'application/pdf'],
        },
        
        // Monitoring
        MONITORING: {
            ENABLED: true,
            SAMPLE_RATE: 0.1,
            ERROR_TRACKING: true,
            PERFORMANCE_TRACKING: true,
        }
    };

    // Environment overrides
    if (CONFIG.ENV.isDevelopment) {
        CONFIG.API.BASE_URL = 'http://localhost:3000/api/v1';
        CONFIG.FEATURES.DEMO_MODE = true;
        CONFIG.MONITORING.ENABLED = false;
    } else if (CONFIG.ENV.isStaging) {
        CONFIG.API.BASE_URL = 'https://staging-api.synapsepm.com/v1';
        CONFIG.FEATURE_FLAGS = { BETA_FEATURES: true };
    }

    Object.freeze(CONFIG);

    // ============================================
    // UTILITIES
    // ============================================
    
    const Utils = (() => {
        
        // String Utilities
        const stringUtils = {
            capitalize: (str) => {
                if (!str) return '';
                return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
            },
            
            capitalizeWords: (str) => {
                if (!str) return '';
                return str.split(' ').map(word => 
                    word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
                ).join(' ');
            },
            
            truncate: (str, length = 50, suffix = '...') => {
                if (!str) return '';
                if (str.length <= length) return str;
                return str.substring(0, length) + suffix;
            },
            
            randomString: (length = 10) => {
                const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
                let result = '';
                for (let i = 0; i < length; i++) {
                    result += chars.charAt(Math.floor(Math.random() * chars.length));
                }
                return result;
            },
            
            slugify: (str) => {
                return str
                    .toLowerCase()
                    .replace(/[^\w\s-]/g, '')
                    .replace(/[\s_-]+/g, '-')
                    .replace(/^-+|-+$/g, '');
            },
            
            formatNumber: (num) => {
                return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
            },
            
            formatCurrency: (amount, currency = 'USD') => {
                return new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: currency,
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 0
                }).format(amount);
            },
            
            formatPercent: (value, decimals = 1) => {
                return `${value.toFixed(decimals)}%`;
            },
            
            generateUUID: () => {
                return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    const r = Math.random() * 16 | 0;
                    const v = c === 'x' ? r : (r & 0x3 | 0x8);
                    return v.toString(16);
                });
            },
            
            getInitials: (name) => {
                if (!name) return 'U';
                return name.split(' ')
                    .map(n => n[0])
                    .join('')
                    .substring(0, 2)
                    .toUpperCase();
            }
        };
        
        // Date Utilities
        const dateUtils = {
            formatDate: (date, format = 'MMM DD, YYYY') => {
                if (!date) return '';
                const d = new Date(date);
                if (isNaN(d.getTime())) return '';
                
                const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
                const fullMonths = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
                
                const year = d.getFullYear();
                const month = d.getMonth();
                const day = d.getDate();
                const hours = d.getHours();
                const minutes = d.getMinutes();
                const seconds = d.getSeconds();
                const ampm = hours >= 12 ? 'PM' : 'AM';
                const hour12 = hours % 12 || 12;
                
                return format
                    .replace('YYYY', year)
                    .replace('YY', String(year).slice(-2))
                    .replace('MMMM', fullMonths[month])
                    .replace('MMM', months[month])
                    .replace('MM', String(month + 1).padStart(2, '0'))
                    .replace('M', month + 1)
                    .replace('DD', String(day).padStart(2, '0'))
                    .replace('D', day)
                    .replace('HH', String(hours).padStart(2, '0'))
                    .replace('H', hours)
                    .replace('hh', String(hour12).padStart(2, '0'))
                    .replace('h', hour12)
                    .replace('mm', String(minutes).padStart(2, '0'))
                    .replace('ss', String(seconds).padStart(2, '0'))
                    .replace('A', ampm)
                    .replace('a', ampm.toLowerCase());
            },
            
            timeAgo: (timestamp) => {
                if (!timestamp) return 'Just now';
                const date = new Date(timestamp);
                if (isNaN(date.getTime())) return 'Just now';
                
                const now = new Date();
                const seconds = Math.floor((now - date) / 1000);
                
                const intervals = {
                    year: 31536000,
                    month: 2592000,
                    week: 604800,
                    day: 86400,
                    hour: 3600,
                    minute: 60,
                };
                
                for (const [unit, secondsInUnit] of Object.entries(intervals)) {
                    const interval = Math.floor(seconds / secondsInUnit);
                    if (interval >= 1) {
                        return interval === 1 ? `1 ${unit} ago` : `${interval} ${unit}s ago`;
                    }
                }
                
                return 'just now';
            },
            
            isToday: (date) => {
                const d = new Date(date);
                const today = new Date();
                return d.toDateString() === today.toDateString();
            },
            
            isYesterday: (date) => {
                const d = new Date(date);
                const yesterday = new Date();
                yesterday.setDate(yesterday.getDate() - 1);
                return d.toDateString() === yesterday.toDateString();
            },
            
            startOfDay: (date = new Date()) => {
                const d = new Date(date);
                d.setHours(0, 0, 0, 0);
                return d;
            },
            
            endOfDay: (date = new Date()) => {
                const d = new Date(date);
                d.setHours(23, 59, 59, 999);
                return d;
            },
            
            getDateRange: (days) => {
                const range = [];
                for (let i = days - 1; i >= 0; i--) {
                    const date = new Date();
                    date.setDate(date.getDate() - i);
                    range.push(date);
                }
                return range;
            },
            
            formatTimeAgo: dateUtils.timeAgo
        };
        
        // Validation Utilities
        const validationUtils = {
            isEmail: (email) => {
                return CONFIG.VALIDATION.EMAIL_REGEX.test(email);
            },
            
            isPhone: (phone) => {
                return CONFIG.VALIDATION.PHONE_REGEX.test(phone);
            },
            
            isUrl: (url) => {
                try {
                    new URL(url);
                    return true;
                } catch {
                    return false;
                }
            },
            
            validateEmail: (email) => {
                return CONFIG.VALIDATION.EMAIL_REGEX.test(email);
            },
            
            validatePhone: (phone) => {
                return CONFIG.VALIDATION.PHONE_REGEX.test(phone);
            },
            
            validateUrl: (url) => {
                return CONFIG.VALIDATION.URL_REGEX.test(url);
            },
            
            checkPasswordStrength: (password) => {
                let score = 0;
                
                if (password.length >= 8) score += 1;
                if (password.length >= 12) score += 1;
                if (/[a-z]/.test(password)) score += 1;
                if (/[A-Z]/.test(password)) score += 1;
                if (/[0-9]/.test(password)) score += 1;
                if (/[^a-zA-Z0-9]/.test(password)) score += 1;
                
                return {
                    score,
                    strength: score <= 2 ? 'weak' : score <= 4 ? 'medium' : 'strong',
                    color: score <= 2 ? '#ef4444' : score <= 4 ? '#f59e0b' : '#10b981',
                };
            },
            
            validatePassword: (password) => {
                const errors = [];
                
                if (password.length < CONFIG.VALIDATION.PASSWORD_MIN_LENGTH) {
                    errors.push(`Password must be at least ${CONFIG.VALIDATION.PASSWORD_MIN_LENGTH} characters`);
                }
                if (password.length > CONFIG.VALIDATION.PASSWORD_MAX_LENGTH) {
                    errors.push(`Password must be less than ${CONFIG.VALIDATION.PASSWORD_MAX_LENGTH} characters`);
                }
                if (!/[A-Z]/.test(password)) {
                    errors.push('Password must contain at least one uppercase letter');
                }
                if (!/[a-z]/.test(password)) {
                    errors.push('Password must contain at least one lowercase letter');
                }
                if (!/[0-9]/.test(password)) {
                    errors.push('Password must contain at least one number');
                }
                if (!/[^a-zA-Z0-9]/.test(password)) {
                    errors.push('Password must contain at least one special character');
                }
                
                return {
                    valid: errors.length === 0,
                    errors
                };
            },
            
            getPasswordStrength: (password) => {
                if (!password) return 0;
                
                let score = 0;
                
                if (password.length >= 8) score += 20;
                if (password.length >= 12) score += 10;
                if (/[a-z]/.test(password)) score += 10;
                if (/[A-Z]/.test(password)) score += 10;
                if (/[0-9]/.test(password)) score += 10;
                if (/[^a-zA-Z0-9]/.test(password)) score += 15;
                if (/(.)\1{2,}/.test(password)) score -= 10;
                if (/^[a-z]+$/i.test(password)) score -= 20;
                if (/^[0-9]+$/.test(password)) score -= 20;
                
                return Math.max(0, Math.min(100, score));
            },
            
            getPasswordStrengthLabel: (score) => {
                if (score < 30) return { label: 'Weak', class: 'weak' };
                if (score < 60) return { label: 'Medium', class: 'medium' };
                if (score < 80) return { label: 'Strong', class: 'strong' };
                return { label: 'Very Strong', class: 'very-strong' };
            },
            
            isCreditCard: (number) => {
                const re = /^[0-9]{13,19}$/;
                return re.test(number.replace(/\s/g, ''));
            },
            
            parseJwt: (token) => {
                try {
                    const base64Url = token.split('.')[1];
                    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                    const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                    }).join(''));
                    return JSON.parse(jsonPayload);
                } catch {
                    return null;
                }
            },
            
            isTokenExpired: (token) => {
                const decoded = validationUtils.parseJwt(token);
                if (!decoded || !decoded.exp) return true;
                return decoded.exp < Date.now() / 1000;
            }
        };
        
        // Storage Utilities
        const storageUtils = {
            setWithExpiry: (key, value, ttl) => {
                const now = new Date();
                const item = {
                    value: value,
                    expiry: now.getTime() + ttl,
                };
                localStorage.setItem(key, JSON.stringify(item));
            },
            
            getWithExpiry: (key) => {
                const itemStr = localStorage.getItem(key);
                if (!itemStr) return null;
                
                try {
                    const item = JSON.parse(itemStr);
                    const now = new Date();
                    
                    if (now.getTime() > item.expiry) {
                        localStorage.removeItem(key);
                        return null;
                    }
                    
                    return item.value;
                } catch {
                    return null;
                }
            },
            
            secureSet: (key, value) => {
                const encoded = btoa(JSON.stringify(value));
                sessionStorage.setItem(key, encoded);
            },
            
            secureGet: (key) => {
                const encoded = sessionStorage.getItem(key);
                if (!encoded) return null;
                
                try {
                    return JSON.parse(atob(encoded));
                } catch {
                    return null;
                }
            },
            
            getCookie: (name) => {
                const value = `; ${document.cookie}`;
                const parts = value.split(`; ${name}=`);
                if (parts.length === 2) return parts.pop().split(';').shift();
                return null;
            },
            
            setCookie: (name, value, days = 7) => {
                const date = new Date();
                date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
                document.cookie = `${name}=${value}; expires=${date.toUTCString()}; path=/; Secure; SameSite=Strict`;
            },
            
            deleteCookie: (name) => {
                document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
            }
        };
        
        // Browser Utilities
        const browserUtils = {
            getUrlParams: () => {
                const params = new URLSearchParams(window.location.search);
                const result = {};
                for (const [key, value] of params) {
                    result[key] = value;
                }
                return result;
            },
            
            setUrlParams: (params, replace = true) => {
                const url = new URL(window.location.href);
                Object.keys(params).forEach(key => {
                    if (params[key] === null || params[key] === undefined) {
                        url.searchParams.delete(key);
                    } else {
                        url.searchParams.set(key, params[key]);
                    }
                });
                if (replace) {
                    window.history.replaceState({}, '', url);
                } else {
                    window.history.pushState({}, '', url);
                }
            },
            
            removeUrlParams: (...keys) => {
                const url = new URL(window.location.href);
                keys.forEach(key => {
                    url.searchParams.delete(key);
                });
                window.history.replaceState({}, '', url);
            },
            
            redirect: (url, delay = 0) => {
                if (delay) {
                    setTimeout(() => window.location.href = url, delay);
                } else {
                    window.location.href = url;
                }
            },
            
            reload: () => {
                window.location.reload();
            },
            
            getDeviceType: () => {
                const ua = navigator.userAgent;
                if (/(tablet|ipad|playbook|silk)|(android(?!.*mobi))/i.test(ua)) {
                    return 'tablet';
                }
                if (/Mobile|Android|iP(hone|od)|IEMobile|BlackBerry|Kindle|Silk-Accelerated|(hpw|web)OS|Opera M(obi|ini)/.test(ua)) {
                    return 'mobile';
                }
                return 'desktop';
            },
            
            isOnline: () => {
                return navigator.onLine;
            },
            
            addNetworkListeners: (onlineCallback, offlineCallback) => {
                window.addEventListener('online', onlineCallback);
                window.addEventListener('offline', offlineCallback);
                
                return () => {
                    window.removeEventListener('online', onlineCallback);
                    window.removeEventListener('offline', offlineCallback);
                };
            },
            
            getDeviceInfo: () => {
                return {
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    language: navigator.language,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    screenSize: `${window.screen.width}x${window.screen.height}`,
                    viewport: `${window.innerWidth}x${window.innerHeight}`,
                    isMobile: /Mobile|Android|iPhone|iPad|iPod/i.test(navigator.userAgent),
                    isTablet: /Tablet|iPad/i.test(navigator.userAgent),
                    isDesktop: !/Mobile|Android|iPhone|iPad|iPod|Tablet/i.test(navigator.userAgent),
                };
            },
            
            copyToClipboard: async (text) => {
                try {
                    await navigator.clipboard.writeText(text);
                    uiUtils.showToast('Copied to clipboard!', 'success');
                    return true;
                } catch {
                    const textarea = document.createElement('textarea');
                    textarea.value = text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    uiUtils.showToast('Copied to clipboard!', 'success');
                    return true;
                }
            },
            
            downloadFile: (content, filename, type = 'text/plain') => {
                const blob = new Blob([content], { type });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            },
            
            downloadFromUrl: (url, filename) => {
                const a = document.createElement('a');
                a.href = url;
                a.download = filename || '';
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }
        };
        
        // UI Utilities
        const uiUtils = {
            showToast: (message, type = 'info', duration = 5000) => {
                const toast = document.createElement('div');
                toast.className = `toast ${type}`;
                
                const icons = {
                    success: 'fa-check-circle',
                    error: 'fa-exclamation-circle',
                    warning: 'fa-exclamation-triangle',
                    info: 'fa-info-circle'
                };
                
                toast.innerHTML = `
                    <i class="fas ${icons[type] || icons.info}"></i>
                    <div class="toast-content">
                        <div class="toast-message">${message}</div>
                    </div>
                    <button class="toast-close" onclick="this.parentElement.remove()">
                        <i class="fas fa-times"></i>
                    </button>
                `;
                
                document.body.appendChild(toast);
                
                setTimeout(() => toast.classList.add('show'), 10);
                
                if (duration > 0) {
                    setTimeout(() => {
                        toast.classList.remove('show');
                        setTimeout(() => toast.remove(), 300);
                    }, duration);
                }
            },
            
            showModal: (options) => {
                const modalId = options.id || 'dynamicModal';
                let modal = document.getElementById(modalId);
                
                if (!modal) {
                    modal = document.createElement('div');
                    modal.id = modalId;
                    modal.className = 'modal';
                    document.body.appendChild(modal);
                }
                
                modal.innerHTML = `
                    <div class="modal-content ${options.size || ''}">
                        <div class="modal-header">
                            <h2><i class="fas fa-${options.icon || 'info-circle'}"></i> ${options.title || 'Notification'}</h2>
                            <button class="modal-close" onclick="UI.hideModal('${modalId}')">&times;</button>
                        </div>
                        <div class="modal-body">
                            ${options.message}
                        </div>
                        <div class="modal-footer">
                            ${options.buttons ? options.buttons.map(btn => `
                                <button class="btn btn-${btn.type || 'primary'}" onclick="(${btn.onClick})(); UI.hideModal('${modalId}')">
                                    ${btn.text}
                                </button>
                            `).join('') : `
                                <button class="btn btn-primary" onclick="UI.hideModal('${modalId}')">OK</button>
                            `}
                        </div>
                    </div>
                `;
                
                modal.classList.add('show');
                document.body.style.overflow = 'hidden';
                
                return modal;
            },
            
            hideModal: (modalId) => {
                const modal = document.getElementById(modalId);
                if (modal) {
                    modal.classList.remove('show');
                    document.body.style.overflow = '';
                    setTimeout(() => modal.remove(), 300);
                }
            },
            
            showLoginPrompt: () => {
                uiUtils.showModal({
                    title: 'Authentication Required',
                    icon: 'lock',
                    message: '<p>Please log in or create an account to access this page.</p>',
                    buttons: [
                        { text: 'Log In', type: 'primary', onClick: 'window.location.href="/login.html"' },
                        { text: 'Sign Up', type: 'secondary', onClick: 'window.location.href="/signup.html"' },
                        { text: 'Cancel', type: 'text', onClick: '' }
                    ]
                });
            },
            
            showAccessDenied: () => {
                uiUtils.showModal({
                    title: 'Access Denied',
                    icon: 'exclamation-triangle',
                    message: '<p>You don\'t have permission to access this page.</p>',
                    buttons: [
                        { text: 'Go to Dashboard', type: 'primary', onClick: 'window.location.href="/dashboard.html"' },
                        { text: 'Switch Account', type: 'text', onClick: 'window.location.href="/login.html"' }
                    ]
                });
            },
            
            showConfirm: (options) => {
                return new Promise((resolve) => {
                    uiUtils.showModal({
                        id: 'confirmModal',
                        title: options.title || 'Confirm Action',
                        icon: options.icon || 'question-circle',
                        message: options.message,
                        buttons: [
                            { text: options.confirmText || 'Confirm', type: options.confirmType || 'danger', onClick: `resolve(true)` },
                            { text: options.cancelText || 'Cancel', type: 'text', onClick: `resolve(false)` }
                        ]
                    });
                });
            },
            
            showLoading: (container) => {
                const loading = document.createElement('div');
                loading.className = 'loading-overlay';
                loading.innerHTML = `
                    <div class="loading-spinner"></div>
                    <p>Loading...</p>
                `;
                container.appendChild(loading);
            },
            
            hideLoading: (container) => {
                const loading = container.querySelector('.loading-overlay');
                if (loading) loading.remove();
            },
            
            showLoadingOverlay: (message = 'Loading...') => {
                const overlay = document.createElement('div');
                overlay.id = 'loadingOverlay';
                overlay.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0, 0, 0, 0.5);
                    z-index: 9999;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    backdrop-filter: blur(4px);
                `;
                
                overlay.innerHTML = `
                    <div style="background: var(--color-surface); padding: 2rem; border-radius: 16px; text-align: center; max-width: 300px;">
                        <div class="loading-spinner" style="width: 40px; height: 40px; margin: 0 auto 1rem;"></div>
                        <p style="color: var(--color-text); margin: 0;">${message}</p>
                    </div>
                `;
                
                document.body.appendChild(overlay);
                return overlay;
            },
            
            hideLoadingOverlay: () => {
                const overlay = document.getElementById('loadingOverlay');
                if (overlay) overlay.remove();
            },
            
            announceToScreenReader: (message, priority = 'polite') => {
                let announcer = document.getElementById('sr-announcer');
                if (!announcer) {
                    announcer = document.createElement('div');
                    announcer.id = 'sr-announcer';
                    announcer.className = 'sr-only';
                    announcer.setAttribute('aria-live', priority);
                    announcer.setAttribute('aria-atomic', 'true');
                    document.body.appendChild(announcer);
                }
                announcer.textContent = message;
                
                setTimeout(() => {
                    announcer.textContent = '';
                }, 1000);
            },
            
            isInViewport: (element) => {
                const rect = element.getBoundingClientRect();
                return (
                    rect.top >= 0 &&
                    rect.left >= 0 &&
                    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                );
            },
            
            scrollToElement: (element, offset = 0) => {
                const elementPosition = element.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - offset;
                
                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            },
            
            debounce: (func, wait = 300) => {
                let timeout;
                return function executedFunction(...args) {
                    const later = () => {
                        clearTimeout(timeout);
                        func(...args);
                    };
                    clearTimeout(timeout);
                    timeout = setTimeout(later, wait);
                };
            },
            
            throttle: (func, limit = 300) => {
                let inThrottle;
                return function executedFunction(...args) {
                    if (!inThrottle) {
                        func(...args);
                        inThrottle = true;
                        setTimeout(() => inThrottle = false, limit);
                    }
                };
            },
            
            sanitizeInput: (str) => {
                if (!str) return '';
                const div = document.createElement('div');
                div.textContent = str;
                return div.innerHTML;
            },
            
            showFormErrors: (errors) => {
                Object.keys(errors).forEach(field => {
                    const input = document.getElementById(field);
                    const errorDiv = document.getElementById(`${field}Error`);
                    
                    if (input) {
                        input.classList.add('error');
                    }
                    
                    if (errorDiv) {
                        errorDiv.textContent = errors[field];
                        errorDiv.classList.add('show');
                    }
                });
            },
            
            clearFormErrors: (formId) => {
                const form = document.getElementById(formId);
                if (!form) return;
                
                form.querySelectorAll('.form-input, .form-select, .form-textarea').forEach(el => {
                    el.classList.remove('error');
                });
                
                form.querySelectorAll('.form-error').forEach(el => {
                    el.classList.remove('show');
                });
            },
            
            updatePasswordStrength: (password) => {
                const strengthFill = document.getElementById('strengthFill');
                const strengthText = document.getElementById('strengthText');
                
                if (!strengthFill || !strengthText) return;
                
                const score = validationUtils.getPasswordStrength(password);
                const { label, class: className } = validationUtils.getPasswordStrengthLabel(score);
                
                strengthFill.style.width = `${score}%`;
                strengthFill.className = `strength-fill strength-${className}`;
                strengthText.textContent = label;
            },
            
            initMobileMenu: () => {
                const toggle = document.getElementById('mobileToggle');
                const menu = document.getElementById('mobileMenu');
                const close = document.getElementById('mobileClose');
                
                if (!toggle || !menu) return;
                
                toggle.addEventListener('click', () => {
                    menu.classList.add('active');
                    document.body.style.overflow = 'hidden';
                });
                
                if (close) {
                    close.addEventListener('click', () => {
                        menu.classList.remove('active');
                        document.body.style.overflow = '';
                    });
                }
                
                document.addEventListener('click', (e) => {
                    if (menu.classList.contains('active') && !menu.contains(e.target) && !toggle.contains(e.target)) {
                        menu.classList.remove('active');
                        document.body.style.overflow = '';
                    }
                });
                
                document.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape' && menu.classList.contains('active')) {
                        menu.classList.remove('active');
                        document.body.style.overflow = '';
                    }
                });
            },
            
            initThemeToggle: () => {
                const toggle = document.getElementById('themeToggle');
                if (!toggle) return;
                
                const savedTheme = localStorage.getItem('theme') || 'light';
                document.body.className = `theme-${savedTheme}`;
                
                const icon = toggle.querySelector('i');
                if (icon) {
                    icon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
                }
                
                toggle.addEventListener('click', () => {
                    const isLight = document.body.classList.contains('theme-light');
                    const newTheme = isLight ? 'dark' : 'light';
                    
                    document.body.classList.remove('theme-light', 'theme-dark');
                    document.body.classList.add(`theme-${newTheme}`);
                    
                    localStorage.setItem('theme', newTheme);
                    
                    if (icon) {
                        icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
                    }
                    
                    uiUtils.announceToScreenReader(`Switched to ${newTheme} mode`);
                });
            },
            
            initTooltips: () => {
                document.querySelectorAll('[data-tooltip]').forEach(el => {
                    el.classList.add('tooltip');
                    
                    el.addEventListener('mouseenter', (e) => {
                        const tooltip = document.createElement('div');
                        tooltip.className = 'tooltip-popup';
                        tooltip.textContent = e.target.dataset.tooltip;
                        document.body.appendChild(tooltip);
                        
                        const rect = e.target.getBoundingClientRect();
                        tooltip.style.top = rect.top - tooltip.offsetHeight - 10 + 'px';
                        tooltip.style.left = rect.left + (rect.width / 2) - (tooltip.offsetWidth / 2) + 'px';
                        
                        e.target.addEventListener('mouseleave', () => {
                            tooltip.remove();
                        }, { once: true });
                    });
                });
            },
            
            initTabs: () => {
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.addEventListener('click', () => {
                        const tabName = tab.dataset.tab;
                        
                        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                        
                        tab.classList.add('active');
                        document.getElementById(tabName)?.classList.add('active');
                        
                        window.location.hash = tabName;
                    });
                });
                
                const hash = window.location.hash.substring(1);
                if (hash) {
                    const tab = document.querySelector(`.tab[data-tab="${hash}"]`);
                    if (tab) tab.click();
                }
            },
            
            initPasswordToggle: () => {
                document.querySelectorAll('.password-toggle').forEach(toggle => {
                    toggle.addEventListener('click', (e) => {
                        const wrapper = e.target.closest('.password-wrapper');
                        if (!wrapper) return;
                        const input = wrapper.querySelector('input');
                        const type = input.type === 'password' ? 'text' : 'password';
                        input.type = type;
                        e.target.querySelector('i').className = type === 'password' ? 'fas fa-eye' : 'fas fa-eye-slash';
                    });
                });
            },
            
            initPasswordStrength: () => {
                const input = document.getElementById('password');
                if (input) {
                    input.addEventListener('input', (e) => uiUtils.updatePasswordStrength(e.target.value));
                }
            },
            
            initSearch: (inputId, callback) => {
                const input = document.getElementById(inputId);
                if (input) {
                    input.addEventListener('input', uiUtils.debounce((e) => callback(e.target.value), 300));
                }
            },
            
            initSelectAll: (selectAllId, checkboxClass) => {
                const selectAll = document.getElementById(selectAllId);
                if (!selectAll) return;
                
                selectAll.addEventListener('change', (e) => {
                    document.querySelectorAll(`.${checkboxClass}`).forEach(cb => {
                        cb.checked = e.target.checked;
                    });
                });
                
                document.querySelectorAll(`.${checkboxClass}`).forEach(cb => {
                    cb.addEventListener('change', () => {
                        const allChecked = [...document.querySelectorAll(`.${checkboxClass}`)].every(cb => cb.checked);
                        selectAll.checked = allChecked;
                        selectAll.indeterminate = !allChecked && [...document.querySelectorAll(`.${checkboxClass}`)].some(cb => cb.checked);
                    });
                });
            },
            
            initCopyButtons: () => {
                document.querySelectorAll('[data-copy]').forEach(btn => {
                    btn.addEventListener('click', () => browserUtils.copyToClipboard(btn.dataset.copy));
                });
            },
            
            initDatePicker: (inputId) => {
                const input = document.getElementById(inputId);
                if (input) {
                    input.addEventListener('click', () => {
                        input.showPicker();
                    });
                }
            }
        };
        
        // Math Utilities
        const mathUtils = {
            clamp: (num, min, max) => Math.min(Math.max(num, min), max),
            random: (min, max) => Math.random() * (max - min) + min,
            randomInt: (min, max) => Math.floor(Math.random() * (max - min + 1)) + min,
            percentage: (value, total) => total === 0 ? 0 : (value / total) * 100,
            round: (num, decimals = 2) => {
                const factor = Math.pow(10, decimals);
                return Math.round(num * factor) / factor;
            }
        };
        
        return {
            ...stringUtils,
            ...dateUtils,
            ...validationUtils,
            ...storageUtils,
            ...browserUtils,
            ...uiUtils,
            ...mathUtils,
            string: stringUtils,
            date: dateUtils,
            validate: validationUtils,
            storage: storageUtils,
            browser: browserUtils,
            ui: uiUtils,
            math: mathUtils
        };
    })();

    // ============================================
    // API SERVICE
    // ============================================

    class ApiService {
        constructor() {
            this.baseURL = CONFIG.API.BASE_URL;
            this.timeout = CONFIG.API.TIMEOUT;
            this.retryAttempts = CONFIG.API.RETRY_ATTEMPTS;
            this.retryDelay = CONFIG.API.RETRY_DELAY;
            this.refreshPromise = null;
            this.requestInterceptors = [];
            this.responseInterceptors = [];
            this.cache = new Map();
            this.cacheTimeout = 300000;
            this.method = 'GET';
        }

        getAuthHeaders() {
            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-Client-Version': CONFIG.APP.VERSION,
            };
            
            const token = localStorage.getItem(CONFIG.AUTH.TOKEN_KEY) || 
                          localStorage.getItem(CONFIG.AUTH.ADMIN_TOKEN_KEY);
            
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            
            const orgId = localStorage.getItem('organization_id');
            if (orgId) {
                headers['X-Organization-ID'] = orgId;
            }
            
            if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(this.method)) {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
                if (csrfToken) {
                    headers['X-CSRF-Token'] = csrfToken;
                }
            }
            
            return headers;
        }

        async request(endpoint, options = {}, retryCount = 0) {
            const url = endpoint.startsWith('http') ? endpoint : `${this.baseURL}${endpoint}`;
            this.method = options.method || 'GET';
            
            const defaultOptions = {
                method: 'GET',
                headers: this.getAuthHeaders(),
                credentials: 'include',
                mode: 'cors'
            };
            
            const finalOptions = { ...defaultOptions, ...options };
            
            finalOptions.headers['X-Request-ID'] = Utils.generateUUID();
            
            for (const interceptor of this.requestInterceptors) {
                await interceptor(finalOptions);
            }
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.timeout);
            finalOptions.signal = controller.signal;
            
            try {
                const response = await fetch(url, finalOptions);
                clearTimeout(timeoutId);
                
                if (response.status === 429) {
                    const retryAfter = response.headers.get('Retry-After') || 60;
                    throw new Error(`Rate limited. Try again in ${retryAfter} seconds.`);
                }
                
                if (response.status === 401) {
                    const isAdmin = window.location.pathname.includes('/admin/');
                    const tokenKey = isAdmin ? CONFIG.AUTH.ADMIN_TOKEN_KEY : CONFIG.AUTH.TOKEN_KEY;
                    const refreshKey = isAdmin ? CONFIG.AUTH.ADMIN_REFRESH_KEY : CONFIG.AUTH.REFRESH_KEY;
                    
                    if (localStorage.getItem(refreshKey)) {
                        const refreshed = await this.refreshToken(isAdmin);
                        if (refreshed) {
                            finalOptions.headers['Authorization'] = `Bearer ${localStorage.getItem(tokenKey)}`;
                            return this.request(endpoint, options, retryCount);
                        }
                    }
                    
                    if (isAdmin) {
                        window.location.href = '/admin/login.html';
                    } else {
                        Utils.ui.showLoginPrompt();
                    }
                    throw new Error('Session expired');
                }
                
                if (response.status === 403) {
                    throw new Error('Access denied');
                }
                
                if (response.status === 404) {
                    throw new Error('Resource not found');
                }
                
                let data;
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    data = await response.json();
                } else if (contentType && contentType.includes('text/')) {
                    data = await response.text();
                } else {
                    data = await response.blob();
                }
                
                for (const interceptor of this.responseInterceptors) {
                    await interceptor(response, data);
                }
                
                if (!response.ok) {
                    const error = new Error(data.message || 'Request failed');
                    error.status = response.status;
                    error.data = data;
                    throw error;
                }
                
                return data;
                
            } catch (error) {
                clearTimeout(timeoutId);
                
                if (error.name === 'AbortError') {
                    throw new Error('Request timeout');
                }
                
                if (!navigator.onLine) {
                    throw new Error('No internet connection');
                }
                
                if (retryCount < this.retryAttempts && this.shouldRetry(error)) {
                    await this.delay(this.retryDelay * Math.pow(2, retryCount));
                    return this.request(endpoint, options, retryCount + 1);
                }
                
                throw error;
            }
        }

        shouldRetry(error) {
            return !error.status || (error.status >= 500 && error.status <= 599) || error.status === 408;
        }

        delay(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

        async refreshToken(isAdmin = false) {
            if (this.refreshPromise) {
                return this.refreshPromise;
            }
            
            const refreshKey = isAdmin ? CONFIG.AUTH.ADMIN_REFRESH_KEY : CONFIG.AUTH.REFRESH_KEY;
            const tokenKey = isAdmin ? CONFIG.AUTH.ADMIN_TOKEN_KEY : CONFIG.AUTH.TOKEN_KEY;
            
            this.refreshPromise = new Promise(async (resolve) => {
                try {
                    const refreshToken = localStorage.getItem(refreshKey);
                    if (!refreshToken) {
                        resolve(false);
                        return;
                    }
                    
                    const response = await fetch(`${this.baseURL}/auth/refresh`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ refresh_token: refreshToken }),
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        localStorage.setItem(tokenKey, data.access_token);
                        if (data.refresh_token) {
                            localStorage.setItem(refreshKey, data.refresh_token);
                        }
                        
                        const expiresIn = data.expires_in || 3600;
                        localStorage.setItem('session_expiry', (Date.now() + expiresIn * 1000).toString());
                        
                        resolve(true);
                    } else {
                        if (isAdmin) {
                            AuthService.adminLogout(false);
                        } else {
                            AuthService.logout(false);
                        }
                        resolve(false);
                    }
                } catch (error) {
                    console.error('Token refresh failed:', error);
                    resolve(false);
                } finally {
                    this.refreshPromise = null;
                }
            });
            
            return this.refreshPromise;
        }

        clearCache() {
            this.cache.clear();
        }

        async getCached(key, fetcher, ttl = this.cacheTimeout) {
            const cached = this.cache.get(key);
            if (cached && Date.now() - cached.timestamp < ttl) {
                return cached.data;
            }
            
            const data = await fetcher();
            this.cache.set(key, {
                data,
                timestamp: Date.now(),
            });
            return data;
        }

        invalidateCache(key) {
            this.cache.delete(key);
        }

        addRequestInterceptor(interceptor) {
            this.requestInterceptors.push(interceptor);
        }

        addResponseInterceptor(interceptor) {
            this.responseInterceptors.push(interceptor);
        }

        async get(endpoint, params = {}, options = {}) {
            const queryString = new URLSearchParams(params).toString();
            const url = queryString ? `${endpoint}?${queryString}` : endpoint;
            return this.request(url, { method: 'GET', ...options });
        }

        async post(endpoint, data = {}, options = {}) {
            return this.request(endpoint, {
                method: 'POST',
                body: JSON.stringify(data),
                ...options
            });
        }

        async put(endpoint, data = {}, options = {}) {
            return this.request(endpoint, {
                method: 'PUT',
                body: JSON.stringify(data),
                ...options
            });
        }

        async patch(endpoint, data = {}, options = {}) {
            return this.request(endpoint, {
                method: 'PATCH',
                body: JSON.stringify(data),
                ...options
            });
        }

        async delete(endpoint, options = {}) {
            return this.request(endpoint, { method: 'DELETE', ...options });
        }

        async upload(endpoint, file, onProgress = null) {
            const formData = new FormData();
            formData.append('file', file);
            
            if (file.size > CONFIG.UPLOAD.MAX_FILE_SIZE) {
                throw new Error(`File too large. Max size: ${CONFIG.UPLOAD.MAX_FILE_SIZE / 1024 / 1024}MB`);
            }
            
            if (!CONFIG.UPLOAD.ALLOWED_TYPES.includes(file.type)) {
                throw new Error('File type not allowed');
            }
            
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', `${this.baseURL}${endpoint}`, true);
                
                const token = localStorage.getItem(CONFIG.AUTH.TOKEN_KEY);
                if (token) {
                    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
                }
                
                if (onProgress) {
                    xhr.upload.addEventListener('progress', (e) => {
                        if (e.lengthComputable) {
                            onProgress(Math.round((e.loaded / e.total) * 100));
                        }
                    });
                }
                
                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            resolve(JSON.parse(xhr.responseText));
                        } catch {
                            resolve(xhr.responseText);
                        }
                    } else {
                        reject(new Error(`Upload failed: ${xhr.status}`));
                    }
                };
                
                xhr.onerror = () => reject(new Error('Network error'));
                xhr.send(formData);
            });
        }

        async batch(requests) {
            return this.post('/batch', { requests });
        }

        async download(endpoint, filename) {
            const response = await this.request(endpoint, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([response]));
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        }
    }

    // ============================================
    // AUTH SERVICE
    // ============================================

    class AuthService {
        constructor(apiService) {
            this.apiService = apiService;
            this.tokenKey = CONFIG.AUTH.TOKEN_KEY;
            this.refreshKey = CONFIG.AUTH.REFRESH_KEY;
            this.userKey = CONFIG.AUTH.USER_KEY;
            this.adminTokenKey = CONFIG.AUTH.ADMIN_TOKEN_KEY;
            this.adminRefreshKey = CONFIG.AUTH.ADMIN_REFRESH_KEY;
            this.adminUserKey = CONFIG.AUTH.ADMIN_USER_KEY;
            this.maxAttempts = CONFIG.AUTH.MAX_LOGIN_ATTEMPTS;
            this.lockoutDuration = CONFIG.AUTH.LOCKOUT_DURATION;
            this.adminLockoutDuration = CONFIG.AUTH.ADMIN_LOCKOUT_DURATION;
        }

        isAuthenticated() {
            const token = localStorage.getItem(this.tokenKey);
            const expiry = localStorage.getItem('session_expiry');
            
            if (!token || !expiry) return false;
            
            if (Date.now() > parseInt(expiry)) {
                this.logout(false);
                return false;
            }
            
            if (Utils.validate.isTokenExpired(token)) {
                this.refreshToken();
                return false;
            }
            
            return true;
        }

        isAdminAuthenticated() {
            const token = localStorage.getItem(this.adminTokenKey);
            const adminLogin = localStorage.getItem('admin_login');
            
            if (!token || !adminLogin) return false;
            
            if (Utils.validate.isTokenExpired(token)) {
                this.adminLogout(false);
                return false;
            }
            
            return true;
        }

        isAdmin() {
            const user = this.getCurrentUser();
            if (!user) return false;
            
            return user.role === 'admin' || 
                   user.role === 'super_admin' || 
                   user.isAdmin === true || 
                   localStorage.getItem('is_admin') === 'true';
        }

        getCurrentUser() {
            const userStr = localStorage.getItem(this.userKey);
            if (!userStr) return null;
            
            try {
                return JSON.parse(userStr);
            } catch {
                return null;
            }
        }

        getCurrentAdmin() {
            const userStr = localStorage.getItem(this.adminUserKey);
            if (!userStr) return null;
            
            try {
                return JSON.parse(userStr);
            } catch {
                return null;
            }
        }

        setSession(authResponse) {
            localStorage.setItem(this.tokenKey, authResponse.access_token);
            
            if (authResponse.refresh_token) {
                localStorage.setItem(this.refreshKey, authResponse.refresh_token);
            }
            
            if (authResponse.user) {
                localStorage.setItem(this.userKey, JSON.stringify(authResponse.user));
                
                if (authResponse.user.role === 'admin' || authResponse.user.role === 'super_admin') {
                    localStorage.setItem('is_admin', 'true');
                }
            }
            
            const expiresIn = authResponse.expires_in || 3600;
            const expiryTime = Date.now() + (expiresIn * 1000);
            localStorage.setItem('session_expiry', expiryTime.toString());
            
            localStorage.setItem('login_timestamp', Date.now().toString());
        }

        setAdminSession(authResponse) {
            localStorage.setItem(this.adminTokenKey, authResponse.access_token);
            
            if (authResponse.refresh_token) {
                localStorage.setItem(this.adminRefreshKey, authResponse.refresh_token);
            }
            
            if (authResponse.user) {
                localStorage.setItem(this.adminUserKey, JSON.stringify(authResponse.user));
            }
            
            localStorage.setItem('admin_login', 'true');
            localStorage.setItem('admin_login_timestamp', Date.now().toString());
        }

        async login(email, password, options = {}) {
            try {
                const response = await this.apiService.post('/auth/login', {
                    email,
                    password,
                    remember_me: options.rememberMe || false,
                });
                
                if (response.access_token) {
                    this.setSession(response);
                    
                    const user = await this.getUserProfile();
                    
                    this.resetLoginAttempts(email);
                    
                    this.trackEvent('Auth', 'Login Success', email);
                    
                    return {
                        success: true,
                        user,
                        requiresMFA: response.requires_mfa || false,
                        tempToken: response.temp_token,
                        message: 'Login successful',
                    };
                }
                
                this.incrementLoginAttempts(email);
                this.trackEvent('Auth', 'Login Failed', email);
                
                return {
                    success: false,
                    message: response.message || 'Invalid credentials',
                };
                
            } catch (error) {
                console.error('Login error:', error);
                
                this.incrementLoginAttempts(email);
                this.trackError(error, { context: 'login', email });
                
                if (error.status === 401) {
                    return { success: false, message: 'Invalid email or password' };
                } else if (error.status === 403) {
                    return { success: false, message: 'Account is locked. Please reset your password or contact support.' };
                } else if (error.status === 422) {
                    return { success: false, message: 'Invalid input. Please check your credentials.' };
                } else if (error.status === 429) {
                    return { success: false, message: 'Too many attempts. Please try again later.' };
                } else {
                    return { success: false, message: 'Unable to connect. Please check your internet connection.' };
                }
            }
        }

        async adminLogin(email, password, options = {}) {
            try {
                const response = await this.apiService.post('/auth/admin/login', {
                    email,
                    password,
                    remember_me: options.rememberMe || false,
                });
                
                if (response.access_token) {
                    this.setAdminSession(response);
                    
                    this.resetLoginAttempts(email, true);
                    
                    this.trackEvent('Auth', 'Admin Login Success', email);
                    
                    return {
                        success: true,
                        user: response.user,
                        requiresMFA: response.requires_mfa || false,
                        tempToken: response.temp_token,
                        message: 'Admin login successful',
                    };
                }
                
                this.incrementLoginAttempts(email, true);
                this.trackEvent('Auth', 'Admin Login Failed', email);
                
                return {
                    success: false,
                    message: response.message || 'Invalid credentials',
                };
                
            } catch (error) {
                console.error('Admin login error:', error);
                
                this.incrementLoginAttempts(email, true);
                this.trackError(error, { context: 'admin_login', email });
                
                if (error.status === 401) {
                    return { success: false, message: 'Invalid email or password' };
                } else if (error.status === 403) {
                    return { success: false, message: 'Access denied. Admin privileges required.' };
                } else {
                    return { success: false, message: 'Unable to connect. Please try again.' };
                }
            }
        }

        async register(userData) {
            try {
                const response = await this.apiService.post('/auth/register', {
                    first_name: userData.firstName,
                    last_name: userData.lastName,
                    company: userData.company,
                    email: userData.email,
                    password: userData.password,
                    marketing_consent: userData.marketingConsent || false,
                    referral_code: userData.referralCode,
                    timezone: userData.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
                });
                
                if (response.access_token) {
                    this.setSession(response);
                    
                    this.trackEvent('Auth', 'Registration Success', userData.email);
                    
                    return {
                        success: true,
                        autoLogin: true,
                        message: 'Registration successful',
                    };
                }
                
                this.trackEvent('Auth', 'Registration Pending', userData.email);
                
                return {
                    success: true,
                    autoLogin: false,
                    message: 'Registration successful. Please check your email to verify your account.',
                };
                
            } catch (error) {
                console.error('Registration error:', error);
                
                this.trackError(error, { context: 'registration', email: userData.email });
                
                if (error.status === 409) {
                    return { success: false, code: 'EMAIL_EXISTS', message: 'This email is already registered' };
                } else if (error.status === 422) {
                    return { 
                        success: false, 
                        code: 'VALIDATION_ERROR', 
                        message: 'Please check your input', 
                        errors: error.data?.errors 
                    };
                } else {
                    return { success: false, message: 'Registration failed. Please try again.' };
                }
            }
        }

        async getUserProfile() {
            try {
                const user = await this.apiService.get('/users/profile');
                localStorage.setItem(this.userKey, JSON.stringify(user));
                return user;
            } catch (error) {
                console.error('Failed to get user profile:', error);
                return this.getCurrentUser();
            }
        }

        async updateProfile(profileData) {
            try {
                const response = await this.apiService.put('/users/profile', profileData);
                localStorage.setItem(this.userKey, JSON.stringify(response));
                
                this.trackEvent('User', 'Profile Updated');
                
                return { success: true, user: response };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to update profile' 
                };
            }
        }

        async changePassword(currentPassword, newPassword) {
            try {
                await this.apiService.post('/users/change-password', {
                    current_password: currentPassword,
                    new_password: newPassword,
                });
                
                this.trackEvent('User', 'Password Changed');
                
                return { success: true };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to change password' 
                };
            }
        }

        async refreshToken() {
            return this.apiService.refreshToken(false);
        }

        async refreshAdminToken() {
            return this.apiService.refreshToken(true);
        }

        async logout(redirect = true) {
            try {
                await this.apiService.post('/auth/logout');
                
                this.trackEvent('Auth', 'Logout');
                
            } catch (error) {
                console.error('Logout error:', error);
            } finally {
                localStorage.removeItem(this.tokenKey);
                localStorage.removeItem(this.refreshKey);
                localStorage.removeItem(this.userKey);
                localStorage.removeItem('session_expiry');
                localStorage.removeItem('login_timestamp');
                localStorage.removeItem('is_admin');
                localStorage.removeItem('organization_id');
                localStorage.removeItem('remembered_email');
                
                sessionStorage.clear();
                
                document.cookie.split(';').forEach(c => {
                    document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=' + new Date().toUTCString() + ';path=/');
                });
                
                if (redirect) {
                    window.location.href = '/login.html';
                }
            }
        }

        async adminLogout(redirect = true) {
            try {
                await this.apiService.post('/auth/admin/logout');
                
                this.trackEvent('Auth', 'Admin Logout');
                
            } catch (error) {
                console.error('Admin logout error:', error);
            } finally {
                localStorage.removeItem(this.adminTokenKey);
                localStorage.removeItem(this.adminRefreshKey);
                localStorage.removeItem(this.adminUserKey);
                localStorage.removeItem('admin_login');
                localStorage.removeItem('admin_login_timestamp');
                
                if (redirect) {
                    window.location.href = '/admin/login.html';
                }
            }
        }

        requireAuth(redirect = true) {
            if (!this.isAuthenticated()) {
                if (redirect) {
                    const currentPath = window.location.pathname;
                    const redirectUrl = encodeURIComponent(currentPath);
                    window.location.href = `/login.html?redirect=${redirectUrl}`;
                }
                return false;
            }
            return true;
        }

        requireAdminAuth(redirect = true) {
            if (!this.isAdminAuthenticated()) {
                if (redirect) {
                    const currentPath = window.location.pathname;
                    const redirectUrl = encodeURIComponent(currentPath);
                    window.location.href = `/admin/login.html?redirect=${redirectUrl}`;
                }
                return false;
            }
            return true;
        }

        requireAdmin(redirect = true) {
            if (!this.isAuthenticated() || !this.isAdmin()) {
                if (redirect) {
                    if (!this.isAuthenticated()) {
                        this.requireAuth(redirect);
                    } else {
                        Utils.ui.showAccessDenied();
                    }
                }
                return false;
            }
            return true;
        }

        getLoginAttempts(email, isAdmin = false) {
            const prefix = isAdmin ? 'admin_' : '';
            const key = `${prefix}login_attempts_${email}`;
            const attempts = localStorage.getItem(key);
            const timestamp = localStorage.getItem(`${key}_timestamp`);
            
            if (!attempts || !timestamp) return 0;
            
            if (Date.now() - parseInt(timestamp) > 3600000) {
                this.resetLoginAttempts(email, isAdmin);
                return 0;
            }
            
            return parseInt(attempts);
        }

        incrementLoginAttempts(email, isAdmin = false) {
            const prefix = isAdmin ? 'admin_' : '';
            const key = `${prefix}login_attempts_${email}`;
            const attempts = this.getLoginAttempts(email, isAdmin) + 1;
            localStorage.setItem(key, attempts.toString());
            localStorage.setItem(`${key}_timestamp`, Date.now().toString());
            return attempts;
        }

        resetLoginAttempts(email, isAdmin = false) {
            const prefix = isAdmin ? 'admin_' : '';
            const key = `${prefix}login_attempts_${email}`;
            localStorage.removeItem(key);
            localStorage.removeItem(`${key}_timestamp`);
        }

        isAccountLocked(email, isAdmin = false) {
            const prefix = isAdmin ? 'admin_' : '';
            const key = `${prefix}login_lockout_${email}`;
            const lockout = localStorage.getItem(key);
            if (!lockout) return false;
            
            if (Date.now() > parseInt(lockout)) {
                localStorage.removeItem(key);
                return false;
            }
            
            return true;
        }

        lockAccount(email, isAdmin = false) {
            const prefix = isAdmin ? 'admin_' : '';
            const key = `${prefix}login_lockout_${email}`;
            const duration = isAdmin ? this.adminLockoutDuration : this.lockoutDuration;
            const lockoutUntil = Date.now() + (duration * 60 * 1000);
            localStorage.setItem(key, lockoutUntil.toString());
        }

        async forgotPassword(email) {
            try {
                await this.apiService.post('/auth/forgot-password', { email });
                
                this.trackEvent('Auth', 'Password Reset Request', email);
                
                return { success: true };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to send reset email' 
                };
            }
        }

        async resetPassword(token, password) {
            try {
                await this.apiService.post('/auth/reset-password', {
                    token,
                    password,
                });
                
                this.trackEvent('Auth', 'Password Reset Success');
                
                return { success: true };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to reset password' 
                };
            }
        }

        async verifyEmail(token) {
            try {
                await this.apiService.get(`/auth/verify/${token}`);
                
                this.trackEvent('Auth', 'Email Verified');
                
                return { success: true };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to verify email' 
                };
            }
        }

        async checkEmail(email) {
            try {
                const response = await this.apiService.post('/auth/check-email', { email });
                return { exists: response.exists };
            } catch (error) {
                console.error('Email check failed:', error);
                return { exists: false };
            }
        }

        async verifyMFA(tempToken, code) {
            try {
                const response = await this.apiService.post('/auth/mfa/verify', {
                    temp_token: tempToken,
                    code,
                });
                
                if (response.access_token) {
                    this.setSession(response);
                    
                    this.trackEvent('Auth', 'MFA Success');
                    
                    return { success: true, user: response.user };
                }
                
                return { success: false, message: 'Invalid verification code' };
                
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Verification failed' 
                };
            }
        }

        async setupMFA() {
            try {
                const response = await this.apiService.post('/auth/mfa/setup');
                
                this.trackEvent('Auth', 'MFA Setup');
                
                return {
                    success: true,
                    secret: response.secret,
                    qrCode: response.qr_code,
                    backupCodes: response.backup_codes,
                };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to setup MFA' 
                };
            }
        }

        async enableMFA(code) {
            try {
                await this.apiService.post('/auth/mfa/enable', { code });
                
                this.trackEvent('Auth', 'MFA Enabled');
                
                return { success: true };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to enable MFA' 
                };
            }
        }

        async disableMFA(code) {
            try {
                await this.apiService.post('/auth/mfa/disable', { code });
                
                this.trackEvent('Auth', 'MFA Disabled');
                
                return { success: true };
            } catch (error) {
                return { 
                    success: false, 
                    message: error.data?.message || 'Failed to disable MFA' 
                };
            }
        }

        socialLogin(provider) {
            const redirectUri = encodeURIComponent(`${window.location.origin}/auth/callback`);
            const state = Utils.randomString(32);
            sessionStorage.setItem('oauth_state', state);
            
            window.location.href = `${CONFIG.API.BASE_URL}/auth/${provider}?redirect_uri=${redirectUri}&state=${state}`;
        }

        trackEvent(category, action, label) {
            if (typeof gtag !== 'undefined') {
                gtag('event', action, {
                    'event_category': category,
                    'event_label': label
                });
            }
            
            if (!CONFIG.ENV.isDevelopment && CONFIG.MONITORING.ENABLED) {
                try {
                    this.apiService.post('/analytics/event', {
                        category,
                        action,
                        label,
                        timestamp: new Date().toISOString(),
                        url: window.location.href
                    }).catch(() => {});
                } catch (error) {
                    // Silently fail
                }
            }
            
            console.log(`[Analytics] ${category} - ${action}`, { label });
        }

        trackError(error, context = {}) {
            this.trackEvent('Error', error.name || 'Error', error.message);
            
            if (!CONFIG.ENV.isDevelopment && CONFIG.MONITORING.ERROR_TRACKING) {
                try {
                    this.apiService.post('/monitoring/errors', {
                        message: error.message,
                        stack: error.stack,
                        context,
                        timestamp: new Date().toISOString(),
                        url: window.location.href,
                        userAgent: navigator.userAgent
                    }).catch(() => {});
                } catch (error) {
                    // Silently fail
                }
            }
        }
    }

    // ============================================
    // DASHBOARD SERVICE
    // ============================================

    class DashboardService {
        constructor(apiService) {
            this.apiService = apiService;
            this.refreshInterval = null;
            this.charts = {};
        }

        init() {
            this.loadStats();
            this.loadMachines();
            this.loadAlerts();
            this.loadActivity();
            this.initCharts();
            this.startAutoRefresh();
        }

        startAutoRefresh() {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
            }
            this.refreshInterval = setInterval(() => {
                this.refresh();
            }, CONFIG.FEATURES.AUTO_REFRESH_INTERVAL);
        }

        stopAutoRefresh() {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
                this.refreshInterval = null;
            }
        }

        refresh() {
            this.loadStats();
            this.loadAlerts();
            this.loadActivity();
        }

        async loadStats() {
            try {
                const stats = await this.apiService.get('/dashboard/stats');
                this.updateStats(stats);
            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }

        updateStats(stats) {
            const elements = {
                totalMachines: document.getElementById('totalMachines'),
                activeAlerts: document.getElementById('activeAlerts'),
                avgConfidence: document.getElementById('avgConfidence'),
                predictionsToday: document.getElementById('predictionsToday'),
                healthScore: document.getElementById('healthScore'),
                uptime: document.getElementById('uptime'),
                totalUsers: document.getElementById('totalUsers'),
                totalPredictions: document.getElementById('totalPredictions'),
                revenue: document.getElementById('revenue'),
            };

            Object.entries(elements).forEach(([key, el]) => {
                if (el && stats[key] !== undefined) {
                    if (key === 'revenue') {
                        el.textContent = Utils.formatCurrency(stats[key]);
                    } else if (key === 'avgConfidence' || key === 'healthScore' || key === 'uptime') {
                        el.textContent = stats[key] + '%';
                    } else if (key === 'predictionsToday' || key === 'totalPredictions') {
                        el.textContent = Utils.formatNumber(stats[key]);
                    } else {
                        el.textContent = stats[key];
                    }
                }
            });

            const machinesBadge = document.getElementById('machinesBadge');
            if (machinesBadge && stats.totalMachines) {
                machinesBadge.textContent = stats.totalMachines;
            }

            const alertsBadge = document.getElementById('alertsBadge');
            if (alertsBadge && stats.activeAlerts) {
                alertsBadge.textContent = stats.activeAlerts;
                alertsBadge.style.display = stats.activeAlerts > 0 ? 'inline-block' : 'none';
            }

            const trends = {
                machinesChange: document.querySelector('#machinesChange span'),
                alertsChange: document.querySelector('#alertsChange span'),
                confidenceChange: document.querySelector('#confidenceChange span'),
                predictionsChange: document.querySelector('#predictionsChange span'),
                userGrowth: document.querySelector('#userGrowth span'),
                machineGrowth: document.querySelector('#machineGrowth span'),
                predictionGrowth: document.querySelector('#predictionGrowth span'),
                revenueGrowth: document.querySelector('#revenueGrowth span'),
            };

            Object.entries(trends).forEach(([key, el]) => {
                if (el && stats[key]) {
                    el.textContent = stats[key];
                }
            });
        }

        async loadMachines(limit = 6) {
            try {
                const response = await this.apiService.get('/machines', { limit });
                if (response.data) {
                    this.renderMachines(response.data);
                }
            } catch (error) {
                console.error('Failed to load machines:', error);
            }
        }

        renderMachines(machines) {
            const grid = document.getElementById('machinesGrid');
            if (!grid) return;

            if (!machines || machines.length === 0) {
                grid.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-industry"></i>
                        <h3>No Machines Yet</h3>
                        <p>Add your first machine to start monitoring</p>
                        <a href="/machines.html?action=add" class="btn btn-primary">Add Machine</a>
                    </div>
                `;
                return;
            }

            grid.innerHTML = machines.slice(0, 6).map(machine => `
                <div class="machine-card" onclick="window.location.href='/machine-detail.html?id=${machine.id}'">
                    <div class="machine-header">
                        <div class="machine-icon">
                            <i class="fas fa-${this.getMachineIcon(machine.type)}"></i>
                        </div>
                        <div class="machine-info">
                            <div class="machine-name">${Utils.sanitizeInput(machine.name)}</div>
                            <div class="machine-location">
                                <i class="fas fa-map-marker-alt"></i> ${machine.location || 'No location'}
                            </div>
                        </div>
                        <span class="machine-status status-${machine.status}">${machine.status}</span>
                    </div>
                    <div class="machine-body">
                        <div class="sensor-grid">
                            <div class="sensor-item">
                                <div class="sensor-label">Temp</div>
                                <div class="sensor-value">${machine.temperature || '--'}<span class="sensor-unit">°C</span></div>
                            </div>
                            <div class="sensor-item">
                                <div class="sensor-label">Vibration</div>
                                <div class="sensor-value">${machine.vibration || '--'}<span class="sensor-unit">mm/s</span></div>
                            </div>
                            <div class="sensor-item">
                                <div class="sensor-label">Pressure</div>
                                <div class="sensor-value">${machine.pressure || '--'}<span class="sensor-unit">PSI</span></div>
                            </div>
                        </div>
                        <div class="health-section">
                            <div class="health-header">
                                <span>Health Score</span>
                                <span>${machine.health || 0}%</span>
                            </div>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${machine.health || 0}%"></div>
                            </div>
                        </div>
                    </div>
                    <div class="machine-footer">
                        <div class="last-seen">
                            <i class="fas fa-clock"></i> ${Utils.date.timeAgo(machine.lastSeen)}
                        </div>
                        <div class="machine-actions" onclick="event.stopPropagation()">
                            <button class="btn-icon" onclick="window.location.href='/machine-detail.html?id=${machine.id}'" title="View Details">
                                <i class="fas fa-chart-line"></i>
                            </button>
                            <button class="btn-icon" onclick="window.location.href='/predictions.html?machine=${machine.id}'" title="Run Prediction">
                                <i class="fas fa-brain"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        getMachineIcon(type) {
            const machineType = CONFIG.MACHINE_TYPES.find(m => m.id === type);
            return machineType ? machineType.icon : 'industry';
        }

        async loadAlerts() {
            try {
                const response = await this.apiService.get('/alerts', { status: 'active', limit: 5 });
                if (response.data) {
                    this.updateAlertsBadge(response.data);
                }
            } catch (error) {
                console.error('Failed to load alerts:', error);
            }
        }

        updateAlertsBadge(alerts) {
            const badge = document.getElementById('alertsBadge');
            if (badge) {
                const criticalCount = alerts.filter(a => a.severity === 'critical').length;
                badge.textContent = criticalCount;
                badge.style.display = criticalCount > 0 ? 'inline-block' : 'none';
            }
        }

        async loadActivity() {
            try {
                const response = await this.apiService.get('/activity', { limit: 5 });
                if (response.data) {
                    this.renderActivity(response.data);
                }
            } catch (error) {
                console.error('Failed to load activity:', error);
            }
        }

        renderActivity(activities) {
            const list = document.getElementById('activityList');
            if (!list) return;

            if (!activities || activities.length === 0) {
                list.innerHTML = '<p class="text-muted text-center">No recent activity</p>';
                return;
            }

            list.innerHTML = activities.map(activity => `
                <div class="activity-item">
                    <div class="activity-icon">
                        <i class="fas fa-${this.getActivityIcon(activity.type)}"></i>
                    </div>
                    <div class="activity-content">
                        <div class="activity-title">${Utils.sanitizeInput(activity.title)}</div>
                        <div class="activity-time">${Utils.date.timeAgo(activity.createdAt)}</div>
                    </div>
                    <div class="activity-meta">${activity.machine || ''}</div>
                </div>
            `).join('');
        }

        getActivityIcon(type) {
            const icons = {
                prediction: 'brain',
                alert: 'bell',
                machine: 'industry',
                user: 'user',
                system: 'cog',
                default: 'circle'
            };
            return icons[type] || icons.default;
        }

        initCharts() {
            this.initTrendChart();
            this.initHealthChart();
            this.initActivityChart();
            this.initUserChart();
        }

        initTrendChart() {
            const ctx = document.getElementById('trendChart')?.getContext('2d');
            if (!ctx || typeof Chart === 'undefined') return;

            this.charts.trend = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: this.getLast30Days(),
                    datasets: [{
                        label: 'Predictions',
                        data: this.generateTrendData(30, 10, 50),
                        borderColor: '#2563eb',
                        backgroundColor: 'rgba(37, 99, 235, 0.1)',
                        tension: 0.4,
                        fill: true,
                        pointBackgroundColor: '#2563eb'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    scales: {
                        y: { 
                            beginAtZero: true,
                            grid: { display: false },
                            ticks: { stepSize: 10 }
                        },
                        x: { 
                            grid: { display: false },
                            ticks: { maxTicksLimit: 7 }
                        }
                    }
                }
            });
        }

        initHealthChart() {
            const ctx = document.getElementById('healthChart')?.getContext('2d');
            if (!ctx || typeof Chart === 'undefined') return;

            this.charts.health = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Healthy', 'Warning', 'Critical'],
                    datasets: [{
                        data: [0, 0, 0],
                        backgroundColor: ['#10b981', '#f59e0b', '#ef4444'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { 
                            position: 'bottom',
                            labels: { usePointStyle: true, padding: 20 }
                        }
                    },
                    cutout: '70%'
                }
            });
        }

        initActivityChart() {
            const ctx = document.getElementById('activityChart')?.getContext('2d');
            if (!ctx || typeof Chart === 'undefined') return;

            this.charts.activity = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: this.getLast30Days(),
                    datasets: [
                        {
                            label: 'Users',
                            data: this.generateTrendData(30, 50, 150),
                            borderColor: '#2563eb',
                            backgroundColor: 'rgba(37, 99, 235, 0.1)',
                            tension: 0.4,
                            fill: true
                        },
                        {
                            label: 'Predictions',
                            data: this.generateTrendData(30, 200, 500),
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            tension: 0.4,
                            fill: true
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top' }
                    },
                    scales: {
                        y: { beginAtZero: true, grid: { display: false } },
                        x: { grid: { display: false }, ticks: { maxTicksLimit: 7 } }
                    }
                }
            });
        }

        initUserChart() {
            const ctx = document.getElementById('userChart')?.getContext('2d');
            if (!ctx || typeof Chart === 'undefined') return;

            this.charts.user = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Free', 'Starter', 'Professional', 'Enterprise'],
                    datasets: [{
                        data: [45, 30, 20, 5],
                        backgroundColor: ['#94a3b8', '#2563eb', '#f59e0b', '#10b981'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom' }
                    },
                    cutout: '70%'
                }
            });
        }

        getLast30Days() {
            const days = [];
            for (let i = 29; i >= 0; i--) {
                const date = new Date();
                date.setDate(date.getDate() - i);
                days.push(date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
            }
            return days;
        }

        getLast7Days() {
            const days = [];
            for (let i = 6; i >= 0; i--) {
                const date = new Date();
                date.setDate(date.getDate() - i);
                days.push(date.toLocaleDateString('en-US', { weekday: 'short' }));
            }
            return days;
        }

        generateTrendData(days, min, max) {
            return Array.from({ length: days }, () => Math.floor(Math.random() * (max - min) + min));
        }

        updateHealthChart(healthy, warning, critical) {
            if (this.charts.health) {
                this.charts.health.data.datasets[0].data = [healthy, warning, critical];
                this.charts.health.update();
            }
        }

        updateUserChart(distribution) {
            if (this.charts.user) {
                this.charts.user.data.datasets[0].data = distribution;
                this.charts.user.update();
            }
        }

        runBatchPrediction() {
            window.location.href = '/predictions.html?batch=true';
        }

        cleanup() {
            this.stopAutoRefresh();
            Object.values(this.charts).forEach(chart => {
                if (chart && typeof chart.destroy === 'function') {
                    chart.destroy();
                }
            });
            this.charts = {};
        }
    }

    // ============================================
    // MACHINES SERVICE
    // ============================================

    class MachinesService {
        constructor(apiService) {
            this.apiService = apiService;
            this.machines = [];
            this.filteredMachines = [];
            this.currentPage = 1;
            this.totalPages = 1;
            this.pageSize = 20;
        }

        async loadMachines(params = {}) {
            try {
                const response = await this.apiService.get('/machines', {
                    page: this.currentPage,
                    limit: this.pageSize,
                    ...params
                });
                
                this.machines = response.data || [];
                this.filteredMachines = [...this.machines];
                this.totalPages = response.totalPages || 1;
                
                return this.machines;
            } catch (error) {
                console.error('Failed to load machines:', error);
                throw error;
            }
        }

        async getMachine(id) {
            try {
                return await this.apiService.get(`/machines/${id}`);
            } catch (error) {
                console.error('Failed to get machine:', error);
                throw error;
            }
        }

        async createMachine(machineData) {
            try {
                const response = await this.apiService.post('/machines', machineData);
                Utils.ui.showToast('Machine created successfully', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to create machine', 'error');
                throw error;
            }
        }

        async updateMachine(id, machineData) {
            try {
                const response = await this.apiService.put(`/machines/${id}`, machineData);
                Utils.ui.showToast('Machine updated successfully', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to update machine', 'error');
                throw error;
            }
        }

        async deleteMachine(id) {
            try {
                await this.apiService.delete(`/machines/${id}`);
                Utils.ui.showToast('Machine deleted successfully', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to delete machine', 'error');
                throw error;
            }
        }

        async runPrediction(id, model = 'lstm') {
            try {
                const response = await this.apiService.post(`/machines/${id}/predict`, { model });
                Utils.ui.showToast('Prediction completed successfully', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to run prediction', 'error');
                throw error;
            }
        }

        async getMetrics(id, timeRange = '24h') {
            try {
                return await this.apiService.get(`/machines/${id}/metrics`, { timeRange });
            } catch (error) {
                console.error('Failed to get machine metrics:', error);
                throw error;
            }
        }

        filterMachines(searchTerm = '', status = '', type = '') {
            this.filteredMachines = this.machines.filter(machine => {
                const matchesSearch = searchTerm === '' || 
                    machine.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    machine.location?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    machine.manufacturer?.toLowerCase().includes(searchTerm.toLowerCase());
                
                const matchesStatus = status === '' || machine.status === status;
                const matchesType = type === '' || machine.type === type;
                
                return matchesSearch && matchesStatus && matchesType;
            });
            
            return this.filteredMachines;
        }

        clearFilters() {
            this.filteredMachines = [...this.machines];
            return this.filteredMachines;
        }
    }

    // ============================================
    // PREDICTIONS SERVICE
    // ============================================

    class PredictionsService {
        constructor(apiService) {
            this.apiService = apiService;
            this.predictions = [];
        }

        async getPredictions(machineId, params = {}) {
            try {
                const response = await this.apiService.get(`/predictions/machine/${machineId}`, params);
                return response.data || [];
            } catch (error) {
                console.error('Failed to get predictions:', error);
                throw error;
            }
        }

        async runPrediction(machineId, model, options = {}) {
            try {
                const response = await this.apiService.post('/predictions/run', {
                    machineId,
                    model,
                    horizon: options.horizon || 30,
                    confidenceThreshold: options.confidenceThreshold || 0.8
                });
                
                Utils.ui.showToast('Prediction completed successfully', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to run prediction', 'error');
                throw error;
            }
        }

        async runBatchPrediction(machineIds) {
            try {
                const response = await this.apiService.post('/predictions/batch', { machineIds });
                Utils.ui.showToast('Batch prediction started', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to start batch prediction', 'error');
                throw error;
            }
        }

        async getHistory(params = {}) {
            try {
                const response = await this.apiService.get('/predictions/history', params);
                this.predictions = response.data || [];
                return this.predictions;
            } catch (error) {
                console.error('Failed to get prediction history:', error);
                throw error;
            }
        }

        async getPrediction(id) {
            try {
                return await this.apiService.get(`/predictions/${id}`);
            } catch (error) {
                console.error('Failed to get prediction:', error);
                throw error;
            }
        }
    }

    // ============================================
    // ALERTS SERVICE
    // ============================================

    class AlertsService {
        constructor(apiService) {
            this.apiService = apiService;
            this.alerts = [];
            this.filteredAlerts = [];
            this.settings = {};
        }

        async getAlerts(params = {}) {
            try {
                const response = await this.apiService.get('/alerts', params);
                this.alerts = response.data || [];
                this.filteredAlerts = [...this.alerts];
                return this.alerts;
            } catch (error) {
                console.error('Failed to get alerts:', error);
                throw error;
            }
        }

        async acknowledgeAlert(id) {
            try {
                await this.apiService.post(`/alerts/${id}/acknowledge`);
                Utils.ui.showToast('Alert acknowledged', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to acknowledge alert', 'error');
                throw error;
            }
        }

        async resolveAlert(id) {
            try {
                await this.apiService.post(`/alerts/${id}/resolve`);
                Utils.ui.showToast('Alert resolved', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to resolve alert', 'error');
                throw error;
            }
        }

        async getSettings() {
            try {
                const settings = await this.apiService.get('/alerts/settings');
                this.settings = settings;
                return settings;
            } catch (error) {
                console.error('Failed to get alert settings:', error);
                throw error;
            }
        }

        async updateSettings(settings) {
            try {
                const response = await this.apiService.put('/alerts/settings', settings);
                Utils.ui.showToast('Alert settings updated', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to update alert settings', 'error');
                throw error;
            }
        }

        filterAlerts(filters = {}) {
            this.filteredAlerts = this.alerts.filter(alert => {
                let matches = true;
                
                if (filters.severity && alert.severity !== filters.severity) matches = false;
                if (filters.status && alert.status !== filters.status) matches = false;
                if (filters.machineId && alert.machineId !== filters.machineId) matches = false;
                if (filters.search) {
                    const search = filters.search.toLowerCase();
                    matches = matches && (
                        alert.title?.toLowerCase().includes(search) ||
                        alert.message?.toLowerCase().includes(search)
                    );
                }
                
                return matches;
            });
            
            return this.filteredAlerts;
        }
    }

    // ============================================
    // REPORTS SERVICE
    // ============================================

    class ReportsService {
        constructor(apiService) {
            this.apiService = apiService;
            this.reports = [];
            this.schedules = [];
            
            this.templates = {
                overview: {
                    name: 'System Overview Report',
                    description: 'Comprehensive overview of all machines and system health'
                },
                predictions: {
                    name: 'Prediction Analysis Report',
                    description: 'Detailed analysis of all AI predictions and remaining useful life'
                },
                maintenance: {
                    name: 'Maintenance History Report',
                    description: 'Complete history of maintenance activities and recommendations'
                },
                performance: {
                    name: 'Machine Performance Report',
                    description: 'Performance metrics and trends for all machines'
                },
                cost: {
                    name: 'Cost Analysis Report',
                    description: 'Maintenance costs, savings, and ROI analysis'
                },
                alerts: {
                    name: 'Alert Summary Report',
                    description: 'Summary of all alerts, response times, and resolutions'
                }
            };
        }

        async getReports(params = {}) {
            try {
                const response = await this.apiService.get('/reports', params);
                this.reports = response.data || [];
                return this.reports;
            } catch (error) {
                console.error('Failed to get reports:', error);
                throw error;
            }
        }

        async generateReport(params) {
            try {
                const response = await this.apiService.post('/reports/generate', params);
                Utils.ui.showToast('Report generation started', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to generate report', 'error');
                throw error;
            }
        }

        async downloadReport(id, format = 'pdf') {
            try {
                await this.apiService.download(`/reports/${id}/download?format=${format}`, `report-${id}.${format}`);
                Utils.ui.showToast('Download started', 'success');
            } catch (error) {
                Utils.ui.showToast('Failed to download report', 'error');
                throw error;
            }
        }

        async deleteReport(id) {
            try {
                await this.apiService.delete(`/reports/${id}`);
                Utils.ui.showToast('Report deleted', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to delete report', 'error');
                throw error;
            }
        }

        async getSchedules() {
            try {
                const response = await this.apiService.get('/reports/schedules');
                this.schedules = response.data || [];
                return this.schedules;
            } catch (error) {
                console.error('Failed to get report schedules:', error);
                throw error;
            }
        }

        async createSchedule(scheduleData) {
            try {
                const response = await this.apiService.post('/reports/schedules', scheduleData);
                Utils.ui.showToast('Schedule created', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to create schedule', 'error');
                throw error;
            }
        }

        async updateSchedule(id, scheduleData) {
            try {
                const response = await this.apiService.put(`/reports/schedules/${id}`, scheduleData);
                Utils.ui.showToast('Schedule updated', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to update schedule', 'error');
                throw error;
            }
        }

        async deleteSchedule(id) {
            try {
                await this.apiService.delete(`/reports/schedules/${id}`);
                Utils.ui.showToast('Schedule deleted', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to delete schedule', 'error');
                throw error;
            }
        }

        getReportIcon(type) {
            const icons = {
                overview: 'chart-pie',
                predictions: 'brain',
                maintenance: 'tools',
                performance: 'chart-line',
                cost: 'dollar-sign',
                alerts: 'bell',
                default: 'file-alt'
            };
            return icons[type] || icons.default;
        }
    }

    // ============================================
    // SETTINGS SERVICE
    // ============================================

    class SettingsService {
        constructor(apiService) {
            this.apiService = apiService;
            this.userData = {};
            this.apiKeys = [];
            this.paymentMethods = [];
        }

        async loadUserData() {
            try {
                const user = await this.apiService.get('/users/profile');
                this.userData = user;
                return user;
            } catch (error) {
                console.error('Failed to load user data:', error);
                throw error;
            }
        }

        async loadApiKeys() {
            try {
                const response = await this.apiService.get('/users/api-keys');
                this.apiKeys = response.data || [];
                return this.apiKeys;
            } catch (error) {
                console.error('Failed to load API keys:', error);
                throw error;
            }
        }

        async loadPaymentMethods() {
            try {
                const response = await this.apiService.get('/users/payment-methods');
                this.paymentMethods = response.data || [];
                return this.paymentMethods;
            } catch (error) {
                console.error('Failed to load payment methods:', error);
                throw error;
            }
        }

        async generateApiKey(name) {
            try {
                const response = await this.apiService.post('/users/api-keys', { name });
                Utils.ui.showToast('API key generated', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to generate API key', 'error');
                throw error;
            }
        }

        async regenerateApiKey(id) {
            try {
                const response = await this.apiService.post(`/users/api-keys/${id}/regenerate`);
                Utils.ui.showToast('API key regenerated', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to regenerate API key', 'error');
                throw error;
            }
        }

        async deleteApiKey(id) {
            try {
                await this.apiService.delete(`/users/api-keys/${id}`);
                Utils.ui.showToast('API key deleted', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to delete API key', 'error');
                throw error;
            }
        }

        maskApiKey(key) {
            if (key.length <= 8) return key;
            return key.substring(0, 4) + '...' + key.substring(key.length - 4);
        }

        async addPaymentMethod(paymentData) {
            try {
                const response = await this.apiService.post('/users/payment-methods', paymentData);
                Utils.ui.showToast('Payment method added', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to add payment method', 'error');
                throw error;
            }
        }

        async setDefaultPayment(id) {
            try {
                const response = await this.apiService.post(`/users/payment-methods/${id}/default`);
                Utils.ui.showToast('Default payment method updated', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to update default payment method', 'error');
                throw error;
            }
        }

        async deletePaymentMethod(id) {
            try {
                await this.apiService.delete(`/users/payment-methods/${id}`);
                Utils.ui.showToast('Payment method removed', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to remove payment method', 'error');
                throw error;
            }
        }

        async updateNotificationSettings(settings) {
            try {
                const response = await this.apiService.put('/users/notifications', settings);
                Utils.ui.showToast('Notification settings updated', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to update notification settings', 'error');
                throw error;
            }
        }
    }

    // ============================================
    // BILLING SERVICE
    // ============================================

    class BillingService {
        constructor(apiService) {
            this.apiService = apiService;
            this.plans = CONFIG.PLANS;
            this.invoices = [];
            this.subscription = null;
        }

        async getCurrentSubscription() {
            try {
                const subscription = await this.apiService.get('/billing/subscription');
                this.subscription = subscription;
                return subscription;
            } catch (error) {
                console.error('Failed to load subscription:', error);
                throw error;
            }
        }

        async getInvoices(params = {}) {
            try {
                const response = await this.apiService.get('/billing/invoices', params);
                this.invoices = response.data || [];
                return this.invoices;
            } catch (error) {
                console.error('Failed to load invoices:', error);
                throw error;
            }
        }

        async createSubscription(planId, billingPeriod = 'monthly', paymentMethodId) {
            try {
                const response = await this.apiService.post('/billing/subscribe', {
                    plan_id: planId,
                    billing_period: billingPeriod,
                    payment_method_id: paymentMethodId
                });
                Utils.ui.showToast('Subscription created successfully', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to create subscription', 'error');
                throw error;
            }
        }

        async updateSubscription(planId, billingPeriod = 'monthly') {
            try {
                const response = await this.apiService.put('/billing/subscription', {
                    plan_id: planId,
                    billing_period: billingPeriod
                });
                Utils.ui.showToast('Subscription updated successfully', 'success');
                return response;
            } catch (error) {
                Utils.ui.showToast('Failed to update subscription', 'error');
                throw error;
            }
        }

        async cancelSubscription(reason = '') {
            try {
                await this.apiService.post('/billing/cancel', { reason });
                Utils.ui.showToast('Subscription cancelled', 'success');
                return true;
            } catch (error) {
                Utils.ui.showToast('Failed to cancel subscription', 'error');
                throw error;
            }
        }

        async createPaymentIntent(amount, currency = 'USD') {
            try {
                const response = await this.apiService.post('/billing/payment-intent', {
                    amount,
                    currency
                });
                return response;
            } catch (error) {
                console.error('Failed to create payment intent:', error);
                throw error;
            }
        }

        calculatePrice(planId, billingPeriod = 'monthly', isBlackFriday = false) {
            const basePrice = CONFIG.PLANS[planId]?.price || 0;
            if (basePrice === 0) return 0;
            
            let price = basePrice;
            
            if (billingPeriod === 'annual') {
                price = Math.round(basePrice * 0.83);
            }
            
            if (isBlackFriday) {
                price = Math.round(price * 0.7);
            }
            
            return price;
        }

        getPlanDetails(planId) {
            return CONFIG.PLANS[planId] || null;
        }

        checkBlackFriday() {
            const now = new Date();
            const month = now.getMonth();
            return month === 10; // November
        }
    }

    // ============================================
    // ROUTE GUARD
    // ============================================

    const RouteGuard = {
        checkRoute() {
            const path = window.location.pathname;
            const filename = path.split('/').pop() || 'index.html';
            const isAdminRoute = path.includes('/admin/');
            
            if (CONFIG.ROUTES.PUBLIC.includes(filename)) {
                return true;
            }
            
            if (isAdminRoute) {
                if (!AuthService.isAdminAuthenticated()) {
                    window.location.href = '/admin/login.html';
                    return false;
                }
            } else {
                if (!AuthService.isAuthenticated()) {
                    Utils.ui.showLoginPrompt();
                    return false;
                }
            }
            
            if (CONFIG.ROUTES.ADMIN.includes(filename) && !AuthService.isAdmin()) {
                Utils.ui.showAccessDenied();
                return false;
            }
            
            return true;
        },

        init() {
            this.checkRoute();
            window.addEventListener('popstate', () => this.checkRoute());
        }
    };

    // ============================================
    // SESSION MANAGER
    // ============================================

    const SessionManager = {
        init() {
            this.checkSession();
            setInterval(() => this.checkSession(), 60000);
        },

        checkSession() {
            const expiry = localStorage.getItem('session_expiry');
            if (!expiry) return;
            
            const timeLeft = parseInt(expiry) - Date.now();
            
            if (timeLeft > 0 && timeLeft < 300000) {
                Utils.ui.showSessionWarning(Math.ceil(timeLeft / 60000));
            }
            
            if (timeLeft <= 0) {
                AuthService.logout();
            }
        },

        extendSession() {
            const currentExpiry = localStorage.getItem('session_expiry');
            if (!currentExpiry) return;
            
            const newExpiry = Date.now() + CONFIG.AUTH.SESSION_TIMEOUT;
            localStorage.setItem('session_expiry', newExpiry.toString());
        }
    };

    // ============================================
    // ADMIN LOGIN CLASS
    // ============================================

    class AdminLogin {
        constructor() {
            this.elements = {
                head: document.getElementById('robotHead'),
                pupils: document.querySelectorAll('.pupil'),
                emailInput: document.getElementById('adminEmail'),
                passwordInput: document.getElementById('adminPassword'),
                loginForm: document.getElementById('adminLoginForm'),
                loginBtn: document.getElementById('loginBtn'),
                btnText: document.getElementById('btnText'),
                loader: document.getElementById('loader'),
                errorMessage: document.getElementById('errorMessage'),
                errorText: document.getElementById('errorText'),
                successMessage: document.getElementById('successMessage'),
                successText: document.getElementById('successText'),
                warningMessage: document.getElementById('warningMessage'),
                warningText: document.getElementById('warningText'),
                togglePassword: document.getElementById('togglePassword'),
                offlineBanner: document.getElementById('offlineBanner'),
                rateLimitInfo: document.getElementById('rateLimitInfo'),
                rateLimitText: document.getElementById('rateLimitText'),
                mfaSection: document.getElementById('mfaSection'),
                mfaInput: document.getElementById('mfaCode'),
                trustDevice: document.getElementById('trustDevice'),
                lastLoginInfo: document.getElementById('lastLoginInfo'),
                lastLoginTime: document.getElementById('lastLoginTime'),
                lastLoginIp: document.getElementById('lastLoginIp'),
                sessionTimer: document.getElementById('sessionTimer'),
                ipWarning: document.getElementById('ipWarning'),
                currentIp: document.getElementById('currentIp')
            };
            
            this.tempToken = null;
            this.failedAttempts = 0;
            this.maxAttempts = CONFIG.AUTH.MAX_LOGIN_ATTEMPTS;
            this.lockoutDuration = CONFIG.AUTH.ADMIN_LOCKOUT_DURATION;
            
            if (this.elements.loginForm) {
                this.init();
            }
        }

        init() {
            this.checkExistingSession();
            this.loadLastLoginInfo();
            this.checkIpAddress();
            this.initEventListeners();
            this.initRobotAnimations();
            this.checkLockoutStatus();
            this.startSessionTimer();
        }

        initEventListeners() {
            if (this.elements.togglePassword) {
                this.elements.togglePassword.addEventListener('click', () => this.togglePassword());
            }
            
            if (this.elements.loginForm) {
                this.elements.loginForm.addEventListener('submit', (e) => this.handleSubmit(e));
            }
            
            if (this.elements.emailInput) {
                this.elements.emailInput.addEventListener('blur', () => this.validateEmail());
            }
            
            if (this.elements.passwordInput) {
                this.elements.passwordInput.addEventListener('blur', () => this.validatePassword());
            }
            
            if (this.elements.mfaInput) {
                this.elements.mfaInput.addEventListener('input', (e) => this.handleMFAInput(e));
            }
            
            window.addEventListener('online', () => this.updateOnlineStatus());
            window.addEventListener('offline', () => this.updateOnlineStatus());
            
            document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
            
            window.addEventListener('beforeunload', () => this.cleanup());
        }

        initRobotAnimations() {
            if (!this.elements.head) return;
            
            document.addEventListener('mousemove', (e) => this.moveRobot(e));
            setInterval(() => this.blinkRobot(), 3000);
        }

        moveRobot(e) {
            if (!this.elements.head || this.elements.head.classList.contains('shy')) return;
            
            const rect = this.elements.head.getBoundingClientRect();
            const headX = rect.left + rect.width / 2;
            const headY = rect.top + rect.height / 2;
            
            const tiltY = (e.clientX - headX) / 20;
            const tiltX = (headY - e.clientY) / 20;
            
            this.elements.head.style.transform = `rotateX(${tiltX}deg) rotateY(${tiltY}deg)`;
            
            const angle = Math.atan2(e.clientY - headY, e.clientX - headX);
            const dist = 3;
            
            this.elements.pupils.forEach(pupil => {
                pupil.style.transform = `translate(${Math.cos(angle) * dist}px, ${Math.sin(angle) * dist}px)`;
            });
        }

        blinkRobot() {
            if (!this.elements.head) return;
            
            this.elements.head.classList.add('blink');
            setTimeout(() => {
                this.elements.head.classList.remove('blink');
            }, 200);
        }

        togglePassword() {
            const type = this.elements.passwordInput.type === 'password' ? 'text' : 'password';
            this.elements.passwordInput.type = type;
            
            const icon = this.elements.togglePassword.querySelector('i');
            icon.className = type === 'password' ? 'fas fa-eye' : 'fas fa-eye-slash';
        }

        checkExistingSession() {
            if (AuthService.isAdminAuthenticated()) {
                window.location.href = 'dashboard.html';
            }
        }

        loadLastLoginInfo() {
            const lastLogin = localStorage.getItem('admin_last_login');
            const lastIp = localStorage.getItem('admin_last_ip');
            
            if (lastLogin && this.elements.lastLoginInfo) {
                const date = new Date(parseInt(lastLogin));
                this.elements.lastLoginTime.textContent = Utils.date.formatDate(date, 'MM/DD/YYYY HH:mm');
                this.elements.lastLoginIp.textContent = lastIp || 'Unknown IP';
                this.elements.lastLoginInfo.style.display = 'flex';
            }
        }

        async checkIpAddress() {
            try {
                const response = await fetch('https://api.ipify.org?format=json');
                const data = await response.json();
                const currentIp = data.ip;
                
                if (this.elements.currentIp) {
                    this.elements.currentIp.textContent = currentIp;
                }
                
                if (CONFIG.ADMIN?.ALLOWED_IPS && CONFIG.ADMIN.ALLOWED_IPS.length > 0) {
                    if (!CONFIG.ADMIN.ALLOWED_IPS.includes(currentIp)) {
                        this.showIpWarning(currentIp);
                    }
                }
                
                sessionStorage.setItem('admin_current_ip', currentIp);
                
            } catch (error) {
                console.error('Failed to get IP address:', error);
            }
        }

        showIpWarning(ip) {
            if (this.elements.ipWarning) {
                this.elements.ipWarning.style.display = 'flex';
            }
        }

        validateEmail() {
            const email = this.elements.emailInput.value.trim();
            
            if (!email) {
                this.showFieldError('email', 'Email is required');
                return false;
            }
            
            if (!Utils.validate.validateEmail(email)) {
                this.showFieldError('email', 'Please enter a valid email address');
                return false;
            }
            
            this.clearFieldError('email');
            return true;
        }

        validatePassword() {
            const password = this.elements.passwordInput.value;
            
            if (!password) {
                this.showFieldError('password', 'Password is required');
                return false;
            }
            
            if (password.length < 6) {
                this.showFieldError('password', 'Password must be at least 6 characters');
                return false;
            }
            
            this.clearFieldError('password');
            return true;
        }

        showFieldError(field, message) {
            const input = document.getElementById(`admin${field.charAt(0).toUpperCase() + field.slice(1)}`);
            const errorDiv = document.getElementById(`${field}Error`);
            
            if (input) {
                input.classList.add('error');
            }
            
            if (errorDiv) {
                errorDiv.textContent = message;
                errorDiv.classList.add('show');
            }
        }

        clearFieldError(field) {
            const input = document.getElementById(`admin${field.charAt(0).toUpperCase() + field.slice(1)}`);
            const errorDiv = document.getElementById(`${field}Error`);
            
            if (input) {
                input.classList.remove('error');
            }
            
            if (errorDiv) {
                errorDiv.classList.remove('show');
            }
        }

        async handleSubmit(e) {
            e.preventDefault();
            
            const lockoutInfo = this.checkLockoutStatus();
            if (lockoutInfo.locked) {
                this.showError(`Account locked. Try again in ${lockoutInfo.minutes} minutes.`);
                this.shakeRobot();
                return;
            }
            
            if (!this.validateEmail() || !this.validatePassword()) {
                return;
            }
            
            const email = this.elements.emailInput.value.trim().toLowerCase();
            const password = this.elements.passwordInput.value;
            
            this.setLoading(true);
            this.hideAllMessages();
            
            try {
                const response = await AuthService.adminLogin(email, password);
                
                if (response.success) {
                    await this.handleLoginSuccess(response);
                } else {
                    await this.handleLoginFailure(response);
                }
                
            } catch (error) {
                this.handleError(error);
            }
        }

        async handleLoginSuccess(response) {
            this.resetLoginAttempts();
            
            if (response.requiresMFA) {
                this.showMFARequired(response.tempToken);
                this.setLoading(false);
                return;
            }
            
            this.updateLastLoginInfo(response.user);
            
            this.logSecurityEvent('admin_login_success', {
                email: response.user.email,
                ip: sessionStorage.getItem('admin_current_ip')
            });
            
            this.showSuccess('Access granted! Redirecting to admin dashboard...');
            
            if (this.elements.head) {
                this.elements.head.classList.add('shy');
            }
            
            setTimeout(() => {
                window.location.href = 'dashboard.html';
            }, 1500);
        }

        async handleLoginFailure(response) {
            const attempts = this.incrementLoginAttempts();
            const remainingAttempts = this.maxAttempts - attempts;
            
            this.logSecurityEvent('admin_login_failed', {
                email: this.elements.emailInput.value.trim(),
                attempts,
                ip: sessionStorage.getItem('admin_current_ip')
            });
            
            if (attempts >= this.maxAttempts) {
                this.lockAccount();
                this.showError(`Too many failed attempts. Account locked for ${this.lockoutDuration} minutes.`);
            } else {
                const message = remainingAttempts <= 2 
                    ? `${response.message || 'Invalid credentials'}. ${remainingAttempts} attempt${remainingAttempts > 1 ? 's' : ''} remaining.`
                    : response.message || 'Invalid admin credentials';
                
                this.showError(message);
            }
            
            this.shakeRobot();
            this.setLoading(false);
        }

        handleError(error) {
            console.error('Admin login error:', error);
            this.showError(error.message || 'Login failed. Please try again.');
            this.setLoading(false);
            this.shakeRobot();
        }

        showMFARequired(tempToken) {
            this.tempToken = tempToken;
            
            if (this.elements.mfaSection) {
                this.elements.mfaSection.classList.add('show');
                this.elements.mfaInput.focus();
                
                this.elements.emailInput.disabled = true;
                this.elements.passwordInput.disabled = true;
            }
        }

        async handleMFAInput(e) {
            const code = e.target.value.replace(/\D/g, '');
            
            if (code.length === 6) {
                await this.verifyMFA(code);
            }
        }

        async verifyMFA(code) {
            this.setLoading(true);
            
            try {
                const response = await AuthService.verifyMFA(this.tempToken, code);
                
                if (response.success) {
                    if (this.elements.trustDevice && this.elements.trustDevice.checked) {
                        this.trustDevice();
                    }
                    
                    this.showSuccess('Verification successful! Redirecting...');
                    
                    setTimeout(() => {
                        window.location.href = 'dashboard.html';
                    }, 1500);
                    
                } else {
                    this.showFieldError('mfaCode', 'Invalid verification code');
                    this.elements.mfaInput.value = '';
                    this.elements.mfaInput.focus();
                    this.setLoading(false);
                }
                
            } catch (error) {
                this.showFieldError('mfaCode', 'Verification failed');
                this.elements.mfaInput.value = '';
                this.elements.mfaInput.focus();
                this.setLoading(false);
            }
        }

        trustDevice() {
            const deviceId = Utils.generateUUID();
            const expires = Date.now() + (30 * 24 * 60 * 60 * 1000);
            
            localStorage.setItem('trusted_device', deviceId);
            localStorage.setItem('trusted_device_expires', expires.toString());
        }

        updateLastLoginInfo(user) {
            const now = Date.now();
            const ip = sessionStorage.getItem('admin_current_ip') || 'Unknown';
            
            localStorage.setItem('admin_last_login', now.toString());
            localStorage.setItem('admin_last_ip', ip);
            localStorage.setItem('admin_last_user', user.email);
        }

        checkLockoutStatus() {
            const lockoutUntil = localStorage.getItem('admin_lockout_until');
            
            if (!lockoutUntil) {
                return { locked: false };
            }
            
            const lockoutTime = parseInt(lockoutUntil);
            
            if (Date.now() < lockoutTime) {
                const minutes = Math.ceil((lockoutTime - Date.now()) / 60000);
                return { locked: true, minutes };
            }
            
            localStorage.removeItem('admin_lockout_until');
            this.resetLoginAttempts();
            
            return { locked: false };
        }

        getLoginAttempts() {
            const attempts = localStorage.getItem('admin_login_attempts');
            return attempts ? parseInt(attempts) : 0;
        }

        incrementLoginAttempts() {
            const attempts = this.getLoginAttempts() + 1;
            localStorage.setItem('admin_login_attempts', attempts.toString());
            localStorage.setItem('admin_login_timestamp', Date.now().toString());
            return attempts;
        }

        resetLoginAttempts() {
            localStorage.removeItem('admin_login_attempts');
            localStorage.removeItem('admin_login_timestamp');
        }

        lockAccount() {
            const lockoutUntil = Date.now() + (this.lockoutDuration * 60 * 1000);
            localStorage.setItem('admin_lockout_until', lockoutUntil.toString());
        }

        logSecurityEvent(eventType, data) {
            try {
                const securityLog = JSON.parse(localStorage.getItem('security_log') || '[]');
                securityLog.push({
                    type: eventType,
                    timestamp: new Date().toISOString(),
                    data
                });
                
                if (securityLog.length > 100) {
                    securityLog.shift();
                }
                
                localStorage.setItem('security_log', JSON.stringify(securityLog));
                
            } catch (error) {
                console.error('Failed to log security event:', error);
            }
        }

        startSessionTimer() {
            if (!this.elements.sessionTimer) return;
            
            setInterval(() => {
                const expiry = localStorage.getItem('session_expiry');
                if (!expiry) return;
                
                const timeLeft = parseInt(expiry) - Date.now();
                
                if (timeLeft > 0) {
                    const minutes = Math.floor(timeLeft / 60000);
                    const seconds = Math.floor((timeLeft % 60000) / 1000);
                    this.elements.sessionTimer.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                }
            }, 1000);
        }

        updateOnlineStatus() {
            if (!navigator.onLine) {
                this.elements.offlineBanner.classList.add('show');
                this.elements.loginBtn.disabled = true;
            } else {
                this.elements.offlineBanner.classList.remove('show');
                
                if (!this.checkLockoutStatus().locked) {
                    this.elements.loginBtn.disabled = false;
                }
            }
        }

        handleKeyboardShortcuts(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                this.elements.loginForm.dispatchEvent(new Event('submit'));
            }
            
            if (e.key === 'Escape') {
                this.hideAllMessages();
            }
            
            if (e.altKey && e.key === 'a') {
                e.preventDefault();
                this.elements.emailInput.focus();
            }
        }

        cleanup() {
            if (this.elements.passwordInput) {
                this.elements.passwordInput.value = '';
            }
            sessionStorage.removeItem('admin_current_ip');
        }

        shakeRobot() {
            if (this.elements.head) {
                this.elements.head.classList.add('shake');
                setTimeout(() => {
                    this.elements.head.classList.remove('shake');
                }, 400);
            }
        }

        showError(message) {
            this.hideAllMessages();
            if (this.elements.errorText) {
                this.elements.errorText.textContent = Utils.sanitizeInput(message);
                this.elements.errorMessage.classList.add('show');
            }
            Utils.ui.announceToScreenReader(message, 'assertive');
        }

        showSuccess(message) {
            this.hideAllMessages();
            if (this.elements.successText) {
                this.elements.successText.textContent = Utils.sanitizeInput(message);
                this.elements.successMessage.classList.add('show');
            }
            Utils.ui.announceToScreenReader(message, 'polite');
        }

        showWarning(message) {
            this.hideAllMessages();
            if (this.elements.warningText) {
                this.elements.warningText.textContent = Utils.sanitizeInput(message);
                this.elements.warningMessage.classList.add('show');
            }
            Utils.ui.announceToScreenReader(message, 'polite');
        }

        hideAllMessages() {
            document.querySelectorAll('.alert').forEach(alert => {
                alert.classList.remove('show');
            });
        }

        setLoading(isLoading) {
            if (!this.elements.loginBtn) return;
            
            this.elements.loginBtn.disabled = isLoading;
            
            if (isLoading) {
                this.elements.btnText.textContent = 'Authenticating...';
                this.elements.loader.classList.remove('hidden');
                this.elements.loginBtn.setAttribute('aria-busy', 'true');
            } else {
                this.elements.btnText.textContent = 'Login as Admin';
                this.elements.loader.classList.add('hidden');
                this.elements.loginBtn.setAttribute('aria-busy', 'false');
            }
        }
    }

    // ============================================
    // PAGE INITIALIZERS
    // ============================================

    const PageInitializers = {
        init() {
            const path = window.location.pathname;
            const page = path.split('/').pop() || 'index.html';
            
            Utils.ui.initMobileMenu();
            Utils.ui.initThemeToggle();
            Utils.ui.initTooltips();
            Utils.ui.initPasswordToggle();
            Utils.ui.initCopyButtons();
            
            switch(page) {
                case 'login.html':
                    this.initLoginPage();
                    break;
                case 'signup.html':
                    this.initSignupPage();
                    break;
                case 'dashboard.html':
                    this.initDashboardPage();
                    break;
                case 'machines.html':
                    this.initMachinesPage();
                    break;
                case 'machine-detail.html':
                case 'machine-details.html':
                    this.initMachineDetailPage();
                    break;
                case 'predictions.html':
                    this.initPredictionsPage();
                    break;
                case 'prediction-details.html':
                    this.initPredictionDetailsPage();
                    break;
                case 'alerts.html':
                    this.initAlertsPage();
                    break;
                case 'reports.html':
                    this.initReportsPage();
                    break;
                case 'settings.html':
                    this.initSettingsPage();
                    break;
                case 'profile.html':
                    this.initProfilePage();
                    break;
                case 'billing.html':
                case 'payment.html':
                    this.initBillingPage();
                    break;
                case 'api-keys.html':
                    this.initApiKeysPage();
                    break;
                case 'team.html':
                    this.initTeamPage();
                    break;
                case 'activity.html':
                    this.initActivityPage();
                    break;
                case 'notifications.html':
                    this.initNotificationsPage();
                    break;
                case 'integrations.html':
                    this.initIntegrationsPage();
                    break;
                case 'docs.html':
                    this.initDocsPage();
                    break;
                case 'demo.html':
                    this.initDemoPage();
                    break;
                case 'contact.html':
                    this.initContactPage();
                    break;
                case 'explore.html':
                    this.initExplorePage();
                    break;
                case 'about.html':
                    this.initAboutPage();
                    break;
                case 'blog.html':
                    this.initBlogPage();
                    break;
                case 'careers.html':
                    this.initCareersPage();
                    break;
                case 'faq.html':
                    this.initFaqPage();
                    break;
                case 'pricing.html':
                    this.initPricingPage();
                    break;
                case 'privacy.html':
                    this.initPrivacyPage();
                    break;
                case 'terms.html':
                    this.initTermsPage();
                    break;
                case 'security.html':
                    this.initSecurityPage();
                    break;
                case 'admin/login.html':
                    this.initAdminLoginPage();
                    break;
                case 'admin/dashboard.html':
                    this.initAdminDashboardPage();
                    break;
                case 'admin/users.html':
                    this.initAdminUsersPage();
                    break;
                case 'admin/user-detail.html':
                    this.initAdminUserDetailPage();
                    break;
                case 'admin/organizations.html':
                    this.initAdminOrganizationsPage();
                    break;
                case 'admin/machines.html':
                    this.initAdminMachinesPage();
                    break;
                case 'admin/analytics.html':
                    this.initAdminAnalyticsPage();
                    break;
                case 'admin/audit-logs.html':
                    this.initAdminAuditLogsPage();
                    break;
                case 'admin/settings.html':
                    this.initAdminSettingsPage();
                    break;
                case 'admin/backup.html':
                    this.initAdminBackupPage();
                    break;
                case 'admin/logs.html':
                    this.initAdminLogsPage();
                    break;
                case 'admin/monitoring.html':
                    this.initAdminMonitoringPage();
                    break;
                case 'admin/reports.html':
                    this.initAdminReportsPage();
                    break;
            }
            
            this.trackPageView(page);
        },

        initLoginPage() {
            Utils.ui.initPasswordToggle();
            Utils.ui.initPasswordStrength();
            
            const params = Utils.browser.getUrlParams();
            if (params.email) {
                const input = document.getElementById('email');
                if (input) input.value = params.email;
            }
            if (params.registered) {
                Utils.ui.showToast('Account created successfully! Please sign in.', 'success');
            }
        },

        initSignupPage() {
            Utils.ui.initPasswordToggle();
            Utils.ui.initPasswordStrength();
            
            const params = Utils.browser.getUrlParams();
            if (params.plan) {
                sessionStorage.setItem('selected_plan', params.plan);
            }
        },

        initDashboardPage() {
            if (!AuthService.requireAuth()) return;
            
            window.dashboardService = new DashboardService(apiService);
            dashboardService.init();
            
            window.addEventListener('beforeunload', () => {
                dashboardService.cleanup();
            });
        },

        initMachinesPage() {
            if (!AuthService.requireAuth()) return;
            
            window.machinesService = new MachinesService(apiService);
            machinesService.loadMachines();
            
            Utils.ui.initSearch('searchInput', (value) => {
                machinesService.filterMachines(value);
            });
        },

        initMachineDetailPage() {
            if (!AuthService.requireAuth()) return;
            
            const params = Utils.browser.getUrlParams();
            const machineId = params.id;
            
            if (machineId) {
                window.machineDetailService = new MachinesService(apiService);
                machineDetailService.getMachine(machineId).then(machine => {
                    // Render machine details
                });
            }
        },

        initPredictionsPage() {
            if (!AuthService.requireAuth()) return;
            
            window.predictionsService = new PredictionsService(apiService);
            predictionsService.getHistory();
        },

        initPredictionDetailsPage() {
            if (!AuthService.requireAuth()) return;
            
            const params = Utils.browser.getUrlParams();
            const predictionId = params.id;
            
            if (predictionId) {
                window.predictionDetailService = new PredictionsService(apiService);
                predictionDetailService.getPrediction(predictionId).then(prediction => {
                    // Render prediction details
                });
            }
        },

        initAlertsPage() {
            if (!AuthService.requireAuth()) return;
            
            window.alertsService = new AlertsService(apiService);
            alertsService.getAlerts();
        },

        initReportsPage() {
            if (!AuthService.requireAuth()) return;
            
            window.reportsService = new ReportsService(apiService);
            reportsService.getReports();
        },

        initSettingsPage() {
            if (!AuthService.requireAuth()) return;
            
            Utils.ui.initTabs();
            window.settingsService = new SettingsService(apiService);
            settingsService.loadUserData();
            settingsService.loadApiKeys();
            settingsService.loadPaymentMethods();
        },

        initProfilePage() {
            if (!AuthService.requireAuth()) return;
            
            window.settingsService = new SettingsService(apiService);
            settingsService.loadUserData();
        },

        initBillingPage() {
            if (!AuthService.requireAuth()) return;
            
            window.billingService = new BillingService(apiService);
            billingService.getCurrentSubscription();
            billingService.getInvoices();
        },

        initApiKeysPage() {
            if (!AuthService.requireAuth()) return;
            
            window.settingsService = new SettingsService(apiService);
            settingsService.loadApiKeys();
        },

        initTeamPage() {
            if (!AuthService.requireAuth()) return;
            // Team page initialization
        },

        initActivityPage() {
            if (!AuthService.requireAuth()) return;
            // Activity page initialization
        },

        initNotificationsPage() {
            if (!AuthService.requireAuth()) return;
            // Notifications page initialization
        },

        initIntegrationsPage() {
            if (!AuthService.requireAuth()) return;
            // Integrations page initialization
        },

        initDocsPage() {
            // No auth required
        },

        initDemoPage() {
            // No auth required
        },

        initContactPage() {
            // No auth required
        },

        initExplorePage() {
            // No auth required
        },

        initAboutPage() {
            // No auth required
        },

        initBlogPage() {
            // No auth required
        },

        initCareersPage() {
            // No auth required
        },

        initFaqPage() {
            // No auth required
        },

        initPricingPage() {
            // No auth required
            window.billingService = new BillingService(apiService);
        },

        initPrivacyPage() {
            // No auth required
        },

        initTermsPage() {
            // No auth required
        },

        initSecurityPage() {
            // No auth required
        },

        initAdminLoginPage() {
            Utils.ui.initPasswordToggle();
            window.adminLogin = new AdminLogin();
        },

        initAdminDashboardPage() {
            if (!AuthService.requireAdminAuth()) return;
            
            window.adminDashboardService = new DashboardService(apiService);
            adminDashboardService.init();
        },

        initAdminUsersPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin users page initialization
        },

        initAdminUserDetailPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin user detail page initialization
        },

        initAdminOrganizationsPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin organizations page initialization
        },

        initAdminMachinesPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin machines page initialization
        },

        initAdminAnalyticsPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin analytics page initialization
        },

        initAdminAuditLogsPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin audit logs page initialization
        },

        initAdminSettingsPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin settings page initialization
        },

        initAdminBackupPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin backup page initialization
        },

        initAdminLogsPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin logs page initialization
        },

        initAdminMonitoringPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin monitoring page initialization
        },

        initAdminReportsPage() {
            if (!AuthService.requireAdminAuth()) return;
            // Admin reports page initialization
        },

        trackPageView(page) {
            if (typeof gtag !== 'undefined') {
                gtag('config', 'GA_MEASUREMENT_ID', {
                    'page_path': page
                });
            }
            
            if (!CONFIG.ENV.isDevelopment && CONFIG.MONITORING.ENABLED) {
                try {
                    apiService.post('/analytics/pageview', {
                        page,
                        timestamp: new Date().toISOString(),
                        referrer: document.referrer,
                        userAgent: navigator.userAgent
                    }).catch(() => {});
                } catch (error) {
                    // Silently fail
                }
            }
            
            console.log(`[Analytics] Page view: ${page}`);
        }
    };

    // ============================================
    // GLOBAL ERROR HANDLING
    // ============================================

    window.addEventListener('error', (event) => {
        console.error('Global error:', event.error);
        
        if (!CONFIG.ENV.isDevelopment && CONFIG.MONITORING.ERROR_TRACKING) {
            try {
                apiService.post('/monitoring/errors', {
                    message: event.error?.message,
                    filename: event.filename,
                    lineno: event.lineno,
                    colno: event.colno,
                    stack: event.error?.stack,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    timestamp: new Date().toISOString()
                }).catch(() => {});
            } catch (error) {
                // Silently fail
            }
        }
        
        if (!CONFIG.ENV.isDevelopment || event.error?.critical) {
            Utils.ui.showToast('An error occurred. Our team has been notified.', 'error');
        }
    });

    window.addEventListener('unhandledrejection', (event) => {
        console.error('Unhandled promise rejection:', event.reason);
        
        if (!CONFIG.ENV.isDevelopment && CONFIG.MONITORING.ERROR_TRACKING) {
            try {
                apiService.post('/monitoring/errors', {
                    message: event.reason?.message || 'Unhandled Promise Rejection',
                    stack: event.reason?.stack,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    timestamp: new Date().toISOString()
                }).catch(() => {});
            } catch (error) {
                // Silently fail
            }
        }
    });

    window.addEventListener('online', () => {
        Utils.ui.showToast('You are back online', 'success');
    });

    window.addEventListener('offline', () => {
        Utils.ui.showToast('You are offline. Some features may be unavailable.', 'warning');
    });

    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const search = document.getElementById('globalSearch');
            if (search) search.focus();
        }
        
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            Utils.ui.showModal({
                title: 'Keyboard Shortcuts',
                icon: 'keyboard',
                message: `
                    <ul style="text-align: left;">
                        <li><kbd>Ctrl/Cmd + K</kbd> - Focus search</li>
                        <li><kbd>Escape</kbd> - Close modals</li>
                        <li><kbd>?</kbd> - Show this help</li>
                        <li><kbd>Ctrl/Cmd + /</kbd> - Show this help</li>
                    </ul>
                `,
                buttons: [{ text: 'Got it', type: 'primary' }]
            });
        }
        
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.show').forEach(modal => {
                modal.classList.remove('show');
                document.body.style.overflow = '';
            });
        }
        
        if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            Utils.ui.showModal({
                title: 'Keyboard Shortcuts',
                icon: 'keyboard',
                message: `
                    <ul style="text-align: left;">
                        <li><kbd>Ctrl/Cmd + K</kbd> - Focus search</li>
                        <li><kbd>Escape</kbd> - Close modals</li>
                        <li><kbd>?</kbd> - Show this help</li>
                        <li><kbd>Ctrl/Cmd + /</kbd> - Show this help</li>
                    </ul>
                `,
                buttons: [{ text: 'Got it', type: 'primary' }]
            });
        }
    });

    // ============================================
    // GLOBAL INSTANCES & INITIALIZATION
    // ============================================

    const apiService = new ApiService();
    const AuthService = new AuthService(apiService);

    window.CONFIG = CONFIG;
    window.Utils = Utils;
    window.apiService = apiService;
    window.AuthService = AuthService;
    window.UI = Utils.ui;
    window.RouteGuard = RouteGuard;
    window.SessionManager = SessionManager;
    window.DashboardService = DashboardService;
    window.MachinesService = MachinesService;
    window.PredictionsService = PredictionsService;
    window.AlertsService = AlertsService;
    window.ReportsService = ReportsService;
    window.SettingsService = SettingsService;
    window.BillingService = BillingService;
    window.AdminLogin = AdminLogin;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            RouteGuard.init();
            SessionManager.init();
            PageInitializers.init();
        });
    } else {
        RouteGuard.init();
        SessionManager.init();
        PageInitializers.init();
    }

    setInterval(() => {
        if (AuthService.isAuthenticated() && !AuthService.isAdminAuthenticated()) {
            AuthService.refreshToken();
        }
        if (AuthService.isAdminAuthenticated()) {
            AuthService.refreshAdminToken();
        }
    }, 15 * 60 * 1000);

})();