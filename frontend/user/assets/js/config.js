// ============================================
// SYNAPSEPM CONFIGURATION
// Production Ready Configuration
// ============================================

const CONFIG = {
    // API Configuration
    API: {
        BASE_URL: 'https://api.synapsepm.com/v1',
        TIMEOUT: 30000, // 30 seconds
        RETRY_ATTEMPTS: 3,
        RETRY_DELAY: 1000, // 1 second
    },
    
    // Authentication
    AUTH: {
        TOKEN_KEY: 'synapse_access_token',
        REFRESH_TOKEN_KEY: 'synapse_refresh_token',
        USER_KEY: 'synapse_user',
        SESSION_DURATION: 30 * 24 * 60 * 60 * 1000, // 30 days
        MFA_ENABLED: true,
    },
    
    // Features
    FEATURES: {
        DARK_MODE: true,
        NOTIFICATIONS: true,
        REAL_TIME_UPDATES: true,
        AUTO_REFRESH_INTERVAL: 30000, // 30 seconds
    },
    
    // Pagination
    PAGINATION: {
        DEFAULT_PAGE_SIZE: 20,
        MAX_PAGE_SIZE: 100,
    },
    
    // File Upload
    UPLOAD: {
        MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
        ALLOWED_TYPES: ['image/jpeg', 'image/png', 'image/gif', 'application/pdf'],
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
    
    // Feature Flags
    FEATURE_FLAGS: {
        BETA_FEATURES: false,
        EARLY_ACCESS: false,
        DEMO_MODE: false,
    },
    
    // Monitoring
    MONITORING: {
        ENABLED: true,
        SAMPLE_RATE: 0.1, // 10% of users
        ERROR_TRACKING: true,
        PERFORMANCE_TRACKING: true,
    },
};

// Environment specific overrides
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    CONFIG.API.BASE_URL = 'http://localhost:3000/api/v1';
    CONFIG.FEATURE_FLAGS.DEMO_MODE = true;
    CONFIG.MONITORING.ENABLED = false;
} else if (window.location.hostname.includes('staging')) {
    CONFIG.API.BASE_URL = 'https://staging-api.synapsepm.com/v1';
    CONFIG.FEATURE_FLAGS.BETA_FEATURES = true;
}

// Freeze configuration to prevent modifications
Object.freeze(CONFIG);