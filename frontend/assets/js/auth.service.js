// ============================================
// SYNAPSEPM AUTH SERVICE
// Production Ready Authentication Service
// ============================================

const AuthService = (() => {
    'use strict';
    
    // ============================================
    // CONSTANTS
    // ============================================
    
    const TOKEN_KEY = CONFIG.AUTH.TOKEN_KEY;
    const REFRESH_TOKEN_KEY = CONFIG.AUTH.REFRESH_TOKEN_KEY;
    const USER_KEY = CONFIG.AUTH.USER_KEY;
    
    // ============================================
    // TOKEN MANAGEMENT
    // ============================================
    
    const setTokens = (accessToken, refreshToken) => {
        localStorage.setItem(TOKEN_KEY, accessToken);
        if (refreshToken) {
            localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
        }
    };
    
    const getToken = () => {
        return localStorage.getItem(TOKEN_KEY);
    };
    
    const getRefreshToken = () => {
        return localStorage.getItem(REFRESH_TOKEN_KEY);
    };
    
    const removeTokens = () => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    };
    
    // ============================================
    // USER MANAGEMENT
    // ============================================
    
    const setUser = (user) => {
        localStorage.setItem(USER_KEY, JSON.stringify(user));
    };
    
    const getUser = () => {
        const userStr = localStorage.getItem(USER_KEY);
        if (!userStr) return null;
        
        try {
            return JSON.parse(userStr);
        } catch {
            return null;
        }
    };
    
    const updateUser = (updates) => {
        const user = getUser();
        if (user) {
            setUser({ ...user, ...updates });
        }
    };
    
    // ============================================
    // AUTHENTICATION STATE
    // ============================================
    
    const isAuthenticated = () => {
        const token = getToken();
        if (!token) return false;
        
        // Check if token is expired
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const exp = payload.exp * 1000; // Convert to milliseconds
            return Date.now() < exp;
        } catch {
            return true; // If we can't decode, assume valid
        }
    };
    
    const isAdmin = () => {
        const user = getUser();
        return user?.role === 'admin' || user?.role === 'super_admin';
    };
    
    // ============================================
    // LOGIN
    // ============================================
    
    const login = async (email, password, rememberMe = false) => {
        try {
            const response = await ApiService.post('/auth/login', {
                email,
                password,
                rememberMe,
            });
            
            if (response.success) {
                const { token, refreshToken, user, requiresMFA } = response.data;
                
                if (requiresMFA) {
                    return { requiresMFA: true, tempToken: token };
                }
                
                setTokens(token, refreshToken);
                setUser(user);
                
                // Log audit
                logAuditEvent('login_success', { email });
                
                return { success: true, user };
            }
            
            return { success: false, message: response.data?.message || 'Login failed' };
            
        } catch (error) {
            logAuditEvent('login_failed', { email, error: error.message });
            throw error;
        }
    };
    
    // ============================================
    // MFA VERIFICATION
    // ============================================
    
    const verifyMFA = async (tempToken, code) => {
        try {
            const response = await ApiService.post('/auth/mfa/verify', {
                token: tempToken,
                code,
            });
            
            if (response.success) {
                const { token, refreshToken, user } = response.data;
                setTokens(token, refreshToken);
                setUser(user);
                return { success: true, user };
            }
            
            return { success: false, message: response.data?.message || 'Verification failed' };
            
        } catch (error) {
            throw error;
        }
    };
    
    // ============================================
    // REGISTER
    // ============================================
    
    const register = async (userData) => {
        try {
            const response = await ApiService.post('/auth/register', userData);
            
            if (response.success) {
                const { token, refreshToken, user } = response.data;
                
                setTokens(token, refreshToken);
                setUser(user);
                
                logAuditEvent('registration_success', { email: user.email });
                
                return { success: true, user };
            }
            
            return { success: false, message: response.data?.message || 'Registration failed' };
            
        } catch (error) {
            logAuditEvent('registration_failed', { email: userData.email, error: error.message });
            throw error;
        }
    };
    
    // ============================================
    // LOGOUT
    // ============================================
    
    const logout = async () => {
        try {
            const token = getToken();
            if (token) {
                await ApiService.post('/auth/logout', {}, { headers: { 'Authorization': `Bearer ${token}` } });
            }
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            removeTokens();
            window.location.href = '/login.html';
        }
    };
    
    // ============================================
    // REFRESH TOKEN
    // ============================================
    
    const refreshToken = async () => {
        const refreshToken = getRefreshToken();
        if (!refreshToken) return false;
        
        try {
            const response = await ApiService.post('/auth/refresh', {
                refreshToken,
            });
            
            if (response.success) {
                const { token, refreshToken: newRefreshToken } = response.data;
                setTokens(token, newRefreshToken);
                return true;
            }
            
            removeTokens();
            return false;
            
        } catch (error) {
            removeTokens();
            return false;
        }
    };
    
    // ============================================
    // PASSWORD RESET
    // ============================================
    
    const requestPasswordReset = async (email) => {
        const response = await ApiService.post('/auth/password/reset-request', { email });
        return response.success;
    };
    
    const resetPassword = async (token, newPassword) => {
        const response = await ApiService.post('/auth/password/reset', {
            token,
            password: newPassword,
        });
        return response.success;
    };
    
    const changePassword = async (currentPassword, newPassword) => {
        const response = await ApiService.post('/auth/password/change', {
            currentPassword,
            newPassword,
        });
        return response.success;
    };
    
    // ============================================
    // SOCIAL AUTH
    // ============================================
    
    const socialLogin = (provider) => {
        const redirectUri = encodeURIComponent(`${window.location.origin}/auth/callback`);
        const state = Utils.string.randomString(32);
        sessionStorage.setItem('oauth_state', state);
        
        window.location.href = `${CONFIG.API.BASE_URL}/auth/${provider}?redirect_uri=${redirectUri}&state=${state}`;
    };
    
    // ============================================
    // AUDIT LOGGING
    // ============================================
    
    const logAuditEvent = (action, details = {}) => {
        if (!CONFIG.MONITORING.ENABLED) return;
        
        const event = {
            action,
            details,
            timestamp: new Date().toISOString(),
            userAgent: navigator.userAgent,
            url: window.location.href,
            referrer: document.referrer,
        };
        
        // Send to analytics in background
        fetch(`${CONFIG.API.BASE_URL}/audit/log`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(event),
            keepalive: true,
        }).catch(() => {});
    };
    
    // ============================================
    // SESSION MANAGEMENT
    // ============================================
    
    const checkSession = () => {
        const token = getToken();
        if (!token) return false;
        
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const exp = payload.exp * 1000;
            
            // Refresh if token expires in less than 5 minutes
            if (exp - Date.now() < 300000) {
                refreshToken();
            }
            
            return true;
        } catch {
            return false;
        }
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        login,
        register,
        logout,
        verifyMFA,
        refreshToken,
        requestPasswordReset,
        resetPassword,
        changePassword,
        socialLogin,
        isAuthenticated,
        isAdmin,
        getUser,
        updateUser,
        getToken,
        checkSession,
    };
})();

// Make available globally
window.AuthService = AuthService;

// Auto-refresh token periodically
setInterval(() => {
    if (AuthService.isAuthenticated()) {
        AuthService.refreshToken();
    }
}, 15 * 60 * 1000); // Every 15 minutes