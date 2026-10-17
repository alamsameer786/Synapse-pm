// ============================================
// SYNAPSEPM UTILITIES
// Production Ready Utility Functions
// ============================================

const Utils = (() => {
    'use strict';
    
    // ============================================
    // STRING UTILITIES
    // ============================================
    
    const stringUtils = {
        /**
         * Capitalize first letter of string
         */
        capitalize: (str) => {
            if (!str) return '';
            return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
        },
        
        /**
         * Capitalize each word in string
         */
        capitalizeWords: (str) => {
            if (!str) return '';
            return str.split(' ').map(word => 
                word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
            ).join(' ');
        },
        
        /**
         * Truncate string to length
         */
        truncate: (str, length = 50, suffix = '...') => {
            if (!str) return '';
            if (str.length <= length) return str;
            return str.substring(0, length) + suffix;
        },
        
        /**
         * Generate random string
         */
        randomString: (length = 10) => {
            const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
            let result = '';
            for (let i = 0; i < length; i++) {
                result += chars.charAt(Math.floor(Math.random() * chars.length));
            }
            return result;
        },
        
        /**
         * Slugify string (URL friendly)
         */
        slugify: (str) => {
            return str
                .toLowerCase()
                .replace(/[^\w\s-]/g, '')
                .replace(/[\s_-]+/g, '-')
                .replace(/^-+|-+$/g, '');
        },
        
        /**
         * Format number with commas
         */
        formatNumber: (num) => {
            return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        },
        
        /**
         * Format currency
         */
        formatCurrency: (amount, currency = 'USD') => {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: currency,
            }).format(amount);
        },
        
        /**
         * Format percentage
         */
        formatPercent: (value, decimals = 1) => {
            return `${value.toFixed(decimals)}%`;
        },
    };
    
    // ============================================
    // DATE UTILITIES
    // ============================================
    
    const dateUtils = {
        /**
         * Format date
         */
        formatDate: (date, format = 'MMM DD, YYYY') => {
            if (!date) return '';
            const d = new Date(date);
            if (isNaN(d.getTime())) return '';
            
            const options = {
                'MMM': { month: 'short' },
                'MMMM': { month: 'long' },
                'DD': { day: '2-digit' },
                'D': { day: 'numeric' },
                'YYYY': { year: 'numeric' },
                'YY': { year: '2-digit' },
                'HH': { hour: '2-digit', hour12: false },
                'hh': { hour: '2-digit', hour12: true },
                'mm': { minute: '2-digit' },
                'ss': { second: '2-digit' },
                'a': { hour12: true },
            };
            
            return format.replace(/(MMM|MMMM|DD|D|YYYY|YY|HH|hh|mm|ss|a)/g, (match) => {
                const option = options[match];
                if (!option) return match;
                return new Intl.DateTimeFormat('en-US', option).format(d);
            });
        },
        
        /**
         * Get time ago string
         */
        timeAgo: (date) => {
            if (!date) return '';
            const d = new Date(date);
            if (isNaN(d.getTime())) return '';
            
            const seconds = Math.floor((new Date() - d) / 1000);
            
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
        
        /**
         * Check if date is today
         */
        isToday: (date) => {
            const d = new Date(date);
            const today = new Date();
            return d.toDateString() === today.toDateString();
        },
        
        /**
         * Check if date is yesterday
         */
        isYesterday: (date) => {
            const d = new Date(date);
            const yesterday = new Date();
            yesterday.setDate(yesterday.getDate() - 1);
            return d.toDateString() === yesterday.toDateString();
        },
        
        /**
         * Get start of day
         */
        startOfDay: (date = new Date()) => {
            const d = new Date(date);
            d.setHours(0, 0, 0, 0);
            return d;
        },
        
        /**
         * Get end of day
         */
        endOfDay: (date = new Date()) => {
            const d = new Date(date);
            d.setHours(23, 59, 59, 999);
            return d;
        },
        
        /**
         * Get date range array
         */
        getDateRange: (days) => {
            const range = [];
            for (let i = days - 1; i >= 0; i--) {
                const date = new Date();
                date.setDate(date.getDate() - i);
                range.push(date);
            }
            return range;
        },
    };
    
    // ============================================
    // VALIDATION UTILITIES
    // ============================================
    
    const validationUtils = {
        /**
         * Validate email
         */
        isEmail: (email) => {
            const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return re.test(email);
        },
        
        /**
         * Validate phone number
         */
        isPhone: (phone) => {
            const re = /^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$/;
            return re.test(phone);
        },
        
        /**
         * Validate URL
         */
        isUrl: (url) => {
            try {
                new URL(url);
                return true;
            } catch {
                return false;
            }
        },
        
        /**
         * Validate password strength
         */
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
        
        /**
         * Validate credit card
         */
        isCreditCard: (number) => {
            const re = /^[0-9]{13,19}$/;
            return re.test(number.replace(/\s/g, ''));
        },
    };
    
    // ============================================
    // STORAGE UTILITIES
    // ============================================
    
    const storageUtils = {
        /**
         * Set item with expiration
         */
        setWithExpiry: (key, value, ttl) => {
            const now = new Date();
            const item = {
                value: value,
                expiry: now.getTime() + ttl,
            };
            localStorage.setItem(key, JSON.stringify(item));
        },
        
        /**
         * Get item with expiration check
         */
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
        
        /**
         * Secure session storage
         */
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
    };
    
    // ============================================
    // BROWSER UTILITIES
    // ============================================
    
    const browserUtils = {
        /**
         * Get cookie value
         */
        getCookie: (name) => {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        },
        
        /**
         * Set cookie
         */
        setCookie: (name, value, days = 30) => {
            const date = new Date();
            date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
            document.cookie = `${name}=${value};expires=${date.toUTCString()};path=/;Secure;SameSite=Strict`;
        },
        
        /**
         * Delete cookie
         */
        deleteCookie: (name) => {
            document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/;`;
        },
        
        /**
         * Get URL parameters
         */
        getUrlParams: () => {
            const params = new URLSearchParams(window.location.search);
            const result = {};
            for (const [key, value] of params) {
                result[key] = value;
            }
            return result;
        },
        
        /**
         * Update URL parameter
         */
        updateUrlParam: (key, value) => {
            const url = new URL(window.location.href);
            if (value === null || value === undefined) {
                url.searchParams.delete(key);
            } else {
                url.searchParams.set(key, value);
            }
            window.history.pushState({}, '', url);
        },
        
        /**
         * Copy to clipboard
         */
        copyToClipboard: async (text) => {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch {
                // Fallback
                const textarea = document.createElement('textarea');
                textarea.value = text;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                return true;
            }
        },
        
        /**
         * Detect device type
         */
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
        
        /**
         * Check online status
         */
        isOnline: () => {
            return navigator.onLine;
        },
        
        /**
         * Add online/offline listeners
         */
        addNetworkListeners: (onlineCallback, offlineCallback) => {
            window.addEventListener('online', onlineCallback);
            window.addEventListener('offline', offlineCallback);
            
            return () => {
                window.removeEventListener('online', onlineCallback);
                window.removeEventListener('offline', offlineCallback);
            };
        },
    };
    
    // ============================================
    // UI UTILITIES
    // ============================================
    
    const uiUtils = {
        /**
         * Show toast notification
         */
        showToast: (message, type = 'info', duration = 3000) => {
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `
                <i class="fas fa-${type === 'success' ? 'check-circle' : 
                                   type === 'error' ? 'exclamation-circle' : 
                                   type === 'warning' ? 'exclamation-triangle' : 
                                   'info-circle'}"></i>
                <div class="toast-content">
                    <div class="toast-message">${message}</div>
                </div>
                <button class="toast-close" onclick="this.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            `;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.style.animation = 'slideInRight 0.3s reverse';
                    setTimeout(() => toast.remove(), 300);
                }
            }, duration);
        },
        
        /**
         * Show modal
         */
        showModal: (modalId) => {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.classList.add('show');
                document.body.style.overflow = 'hidden';
            }
        },
        
        /**
         * Hide modal
         */
        hideModal: (modalId) => {
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.classList.remove('show');
                document.body.style.overflow = '';
            }
        },
        
        /**
         * Show loading overlay
         */
        showLoading: (container) => {
            const loading = document.createElement('div');
            loading.className = 'loading-overlay';
            loading.innerHTML = `
                <div class="loading-spinner"></div>
                <p>Loading...</p>
            `;
            container.appendChild(loading);
        },
        
        /**
         * Hide loading overlay
         */
        hideLoading: (container) => {
            const loading = container.querySelector('.loading-overlay');
            if (loading) loading.remove();
        },
        
        /**
         * Debounce function
         */
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
        
        /**
         * Throttle function
         */
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
    };
    
    // ============================================
    // MATH UTILITIES
    // ============================================
    
    const mathUtils = {
        /**
         * Clamp number between min and max
         */
        clamp: (num, min, max) => Math.min(Math.max(num, min), max),
        
        /**
         * Random number between min and max
         */
        random: (min, max) => Math.random() * (max - min) + min,
        
        /**
         * Random integer between min and max
         */
        randomInt: (min, max) => Math.floor(Math.random() * (max - min + 1)) + min,
        
        /**
         * Calculate percentage
         */
        percentage: (value, total) => total === 0 ? 0 : (value / total) * 100,
        
        /**
         * Round to decimal places
         */
        round: (num, decimals = 2) => {
            const factor = Math.pow(10, decimals);
            return Math.round(num * factor) / factor;
        },
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        string: stringUtils,
        date: dateUtils,
        validate: validationUtils,
        storage: storageUtils,
        browser: browserUtils,
        ui: uiUtils,
        math: mathUtils,
    };
})();

// Make available globally
window.Utils = Utils;