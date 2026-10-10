// ============================================
// ADMIN/LOGIN.JS - Admin Login Page Logic
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
        
        this.init();
    }
    
    /**
     * Initialize admin login
     */
    init() {
        this.checkExistingSession();
        this.loadLastLoginInfo();
        this.checkIpAddress();
        this.initEventListeners();
        this.initRobotAnimations();
        this.checkLockoutStatus();
        this.startSessionTimer();
    }
    
    /**
     * Initialize event listeners
     */
    initEventListeners() {
        // Password toggle
        this.elements.togglePassword.addEventListener('click', () => this.togglePassword());
        
        // Form submission
        this.elements.loginForm.addEventListener('submit', (e) => this.handleSubmit(e));
        
        // Input validation
        this.elements.emailInput.addEventListener('blur', () => this.validateEmail());
        this.elements.passwordInput.addEventListener('blur', () => this.validatePassword());
        
        // MFA input
        if (this.elements.mfaInput) {
            this.elements.mfaInput.addEventListener('input', (e) => this.handleMFAInput(e));
        }
        
        // Online/offline detection
        window.addEventListener('online', () => this.updateOnlineStatus());
        window.addEventListener('offline', () => this.updateOnlineStatus());
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
        
        // Clear sensitive data on page unload
        window.addEventListener('beforeunload', () => this.cleanup());
    }
    
    /**
     * Initialize robot animations
     */
    initRobotAnimations() {
        document.addEventListener('mousemove', (e) => this.moveRobot(e));
        
        // Blink occasionally
        setInterval(() => this.blinkRobot(), 3000);
    }
    
    /**
     * Move robot head with mouse
     */
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
    
    /**
     * Make robot blink
     */
    blinkRobot() {
        if (!this.elements.head) return;
        
        this.elements.head.classList.add('blink');
        setTimeout(() => {
            this.elements.head.classList.remove('blink');
        }, 200);
    }
    
    /**
     * Toggle password visibility
     */
    togglePassword() {
        const type = this.elements.passwordInput.type === 'password' ? 'text' : 'password';
        this.elements.passwordInput.type = type;
        
        const icon = this.elements.togglePassword.querySelector('i');
        icon.className = type === 'password' ? 'fas fa-eye' : 'fas fa-eye-slash';
        
        this.elements.togglePassword.setAttribute('aria-label', 
            type === 'password' ? 'Show password' : 'Hide password'
        );
    }
    
    /**
     * Check if already logged in
     */
    checkExistingSession() {
        if (authService.isAuthenticated() && authService.isAdmin()) {
            window.location.href = 'dashboard.html';
        }
    }
    
    /**
     * Load last login information
     */
    loadLastLoginInfo() {
        const lastLogin = localStorage.getItem('admin_last_login');
        const lastIp = localStorage.getItem('admin_last_ip');
        
        if (lastLogin && this.elements.lastLoginInfo) {
            const date = new Date(parseInt(lastLogin));
            this.elements.lastLoginTime.textContent = utils.formatDate(date, 'MM/DD/YYYY HH:mm');
            this.elements.lastLoginIp.textContent = lastIp || 'Unknown IP';
            this.elements.lastLoginInfo.style.display = 'flex';
        }
    }
    
    /**
     * Check IP address
     */
    async checkIpAddress() {
        try {
            const response = await fetch('https://api.ipify.org?format=json');
            const data = await response.json();
            const currentIp = data.ip;
            
            if (this.elements.currentIp) {
                this.elements.currentIp.textContent = currentIp;
            }
            
            // Check if IP is allowed (if configured)
            if (CONFIG.ADMIN.ALLOWED_IPS && CONFIG.ADMIN.ALLOWED_IPS.length > 0) {
                if (!CONFIG.ADMIN.ALLOWED_IPS.includes(currentIp)) {
                    this.showIpWarning(currentIp);
                }
            }
            
            // Store current IP
            sessionStorage.setItem('admin_current_ip', currentIp);
            
        } catch (error) {
            console.error('Failed to get IP address:', error);
        }
    }
    
    /**
     * Show IP warning
     */
    showIpWarning(ip) {
        if (this.elements.ipWarning) {
            this.elements.ipWarning.style.display = 'flex';
        }
    }
    
    /**
     * Validate email
     */
    validateEmail() {
        const email = this.elements.emailInput.value.trim();
        const errorDiv = document.getElementById('emailError');
        
        if (!email) {
            this.showFieldError('email', 'Email is required');
            return false;
        }
        
        if (!utils.validateEmail(email)) {
            this.showFieldError('email', 'Please enter a valid email address');
            return false;
        }
        
        this.clearFieldError('email');
        return true;
    }
    
    /**
     * Validate password
     */
    validatePassword() {
        const password = this.elements.passwordInput.value;
        const errorDiv = document.getElementById('passwordError');
        
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
    
    /**
     * Show field error
     */
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
    
    /**
     * Clear field error
     */
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
    
    /**
     * Handle form submission
     */
    async handleSubmit(e) {
        e.preventDefault();
        
        // Check if account is locked
        const lockoutInfo = this.checkLockoutStatus();
        if (lockoutInfo.locked) {
            this.showError(`Account locked. Try again in ${lockoutInfo.minutes} minutes.`);
            this.shakeRobot();
            return;
        }
        
        // Validate form
        if (!this.validateEmail() || !this.validatePassword()) {
            return;
        }
        
        const email = this.elements.emailInput.value.trim().toLowerCase();
        const password = this.elements.passwordInput.value;
        
        this.setLoading(true);
        this.hideAllMessages();
        
        try {
            const response = await this.attemptLogin(email, password);
            
            if (response.success) {
                await this.handleLoginSuccess(response);
            } else {
                await this.handleLoginFailure(response);
            }
            
        } catch (error) {
            this.handleError(error);
        }
    }
    
    /**
     * Attempt login
     */
    async attemptLogin(email, password) {
        // Try API login first
        try {
            const response = await apiService.post('/auth/login', {
                email,
                password,
                admin: true
            });
            
            if (response.access_token) {
                const user = response.user;
                
                // Verify admin privileges
                if (!this.isAdminUser(user)) {
                    return {
                        success: false,
                        message: 'Access denied. Administrator privileges required.'
                    };
                }
                
                return {
                    success: true,
                    user,
                    token: response.access_token,
                    refreshToken: response.refresh_token,
                    requiresMFA: response.requires_mfa || false,
                    tempToken: response.temp_token
                };
            }
            
        } catch (error) {
            if (error.status === 401) {
                return { success: false, message: 'Invalid credentials' };
            }
            if (error.status === 403) {
                return { success: false, message: 'Account locked' };
            }
            // Continue to fallback
        }
        
        // Fallback to default admin
        if (email === CONFIG.ADMIN.DEFAULT_EMAIL && password === 'Admin@123!') {
            return {
                success: true,
                user: {
                    id: 1,
                    email: CONFIG.ADMIN.DEFAULT_EMAIL,
                    role: 'super_admin',
                    name: 'System Administrator'
                },
                token: 'admin_' + Date.now(),
                isFallback: true
            };
        }
        
        return { success: false, message: 'Invalid admin credentials' };
    }
    
    /**
     * Check if user is admin
     */
    isAdminUser(user) {
        return user.role === 'admin' || 
               user.role === 'super_admin' || 
               user.isAdmin === true;
    }
    
    /**
     * Handle login success
     */
    async handleLoginSuccess(response) {
        // Reset failed attempts
        this.resetLoginAttempts();
        
        // Check if MFA required
        if (response.requiresMFA) {
            this.showMFARequired(response.tempToken);
            this.setLoading(false);
            return;
        }
        
        // Store session
        this.setAdminSession(response.user, response.token, response.refreshToken);
        
        // Store last login info
        this.updateLastLoginInfo(response.user);
        
        // Log security event
        this.logSecurityEvent('admin_login_success', {
            email: response.user.email,
            ip: sessionStorage.getItem('admin_current_ip')
        });
        
        // Show success message
        this.showSuccess('Access granted! Redirecting to admin dashboard...');
        
        // Happy robot animation
        if (this.elements.head) {
            this.elements.head.classList.add('shy');
        }
        
        // Redirect
        setTimeout(() => {
            window.location.href = 'dashboard.html';
        }, 1500);
    }
    
    /**
     * Handle login failure
     */
    async handleLoginFailure(response) {
        const attempts = this.incrementLoginAttempts();
        const remainingAttempts = this.maxAttempts - attempts;
        
        // Log failed attempt
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
    
    /**
     * Handle error
     */
    handleError(error) {
        console.error('Admin login error:', error);
        this.showError(error.message || 'Login failed. Please try again.');
        this.setLoading(false);
        this.shakeRobot();
    }
    
    /**
     * Show MFA required
     */
    showMFARequired(tempToken) {
        this.tempToken = tempToken;
        
        if (this.elements.mfaSection) {
            this.elements.mfaSection.classList.add('show');
            this.elements.mfaInput.focus();
            
            // Disable other inputs
            this.elements.emailInput.disabled = true;
            this.elements.passwordInput.disabled = true;
            
            this.showInfo('Two-factor authentication required. Please enter the code from your authenticator app.');
        }
    }
    
    /**
     * Handle MFA input
     */
    async handleMFAInput(e) {
        const code = e.target.value.replace(/\D/g, '');
        
        if (code.length === 6) {
            await this.verifyMFA(code);
        }
    }
    
    /**
     * Verify MFA code
     */
    async verifyMFA(code) {
        this.setLoading(true);
        
        try {
            const response = await apiService.post('/auth/mfa/verify', {
                temp_token: this.tempToken,
                code
            });
            
            if (response.access_token) {
                this.setAdminSession(response.user, response.access_token, response.refresh_token);
                
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
    
    /**
     * Trust device for 30 days
     */
    trustDevice() {
        const deviceId = utils.generateUUID();
        const expires = Date.now() + (30 * 24 * 60 * 60 * 1000);
        
        localStorage.setItem('trusted_device', deviceId);
        localStorage.setItem('trusted_device_expires', expires.toString());
    }
    
    /**
     * Set admin session
     */
    setAdminSession(user, token, refreshToken) {
        localStorage.setItem(CONFIG.AUTH.TOKEN_KEY, token);
        
        if (refreshToken) {
            localStorage.setItem(CONFIG.AUTH.REFRESH_KEY, refreshToken);
        }
        
        localStorage.setItem(CONFIG.AUTH.USER_KEY, JSON.stringify(user));
        localStorage.setItem('is_admin', 'true');
        localStorage.setItem('admin_login', 'true');
        localStorage.setItem('login_timestamp', Date.now().toString());
        
        // Set session expiry (30 minutes for admin)
        const expiryTime = Date.now() + CONFIG.ADMIN.SESSION_TIMEOUT;
        localStorage.setItem('session_expiry', expiryTime.toString());
    }
    
    /**
     * Update last login info
     */
    updateLastLoginInfo(user) {
        const now = Date.now();
        const ip = sessionStorage.getItem('admin_current_ip') || 'Unknown';
        
        localStorage.setItem('admin_last_login', now.toString());
        localStorage.setItem('admin_last_ip', ip);
        localStorage.setItem('admin_last_user', user.email);
    }
    
    /**
     * Check lockout status
     */
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
    
    /**
     * Get login attempts
     */
    getLoginAttempts() {
        const attempts = localStorage.getItem('admin_login_attempts');
        return attempts ? parseInt(attempts) : 0;
    }
    
    /**
     * Increment login attempts
     */
    incrementLoginAttempts() {
        const attempts = this.getLoginAttempts() + 1;
        localStorage.setItem('admin_login_attempts', attempts.toString());
        localStorage.setItem('admin_login_timestamp', Date.now().toString());
        return attempts;
    }
    
    /**
     * Reset login attempts
     */
    resetLoginAttempts() {
        localStorage.removeItem('admin_login_attempts');
        localStorage.removeItem('admin_login_timestamp');
    }
    
    /**
     * Lock account
     */
    lockAccount() {
        const lockoutUntil = Date.now() + (this.lockoutDuration * 60 * 1000);
        localStorage.setItem('admin_lockout_until', lockoutUntil.toString());
    }
    
    /**
     * Log security event
     */
    logSecurityEvent(eventType, data) {
        try {
            const securityLog = JSON.parse(localStorage.getItem('security_log') || '[]');
            securityLog.push({
                type: eventType,
                timestamp: new Date().toISOString(),
                data
            });
            
            // Keep last 100 events
            if (securityLog.length > 100) {
                securityLog.shift();
            }
            
            localStorage.setItem('security_log', JSON.stringify(securityLog));
            
            // Also log to console in development
            if (CONFIG.ENV.isDevelopment) {
                console.log(`🔒 Security Event: ${eventType}`, data);
            }
            
        } catch (error) {
            console.error('Failed to log security event:', error);
        }
    }
    
    /**
     * Start session timer
     */
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
    
    /**
     * Update online status
     */
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
    
    /**
     * Handle keyboard shortcuts
     */
    handleKeyboardShortcuts(e) {
        // Ctrl/Cmd + Enter to submit
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            this.elements.loginForm.dispatchEvent(new Event('submit'));
        }
        
        // Escape to clear messages
        if (e.key === 'Escape') {
            this.hideAllMessages();
        }
        
        // Alt + A to focus admin email (accessibility)
        if (e.altKey && e.key === 'a') {
            e.preventDefault();
            this.elements.emailInput.focus();
        }
    }
    
    /**
     * Cleanup on page unload
     */
    cleanup() {
        // Clear sensitive data
        this.elements.passwordInput.value = '';
        sessionStorage.removeItem('admin_current_ip');
    }
    
    /**
     * Shake robot animation
     */
    shakeRobot() {
        if (this.elements.head) {
            this.elements.head.classList.add('shake');
            setTimeout(() => {
                this.elements.head.classList.remove('shake');
            }, 400);
        }
    }
    
    /**
     * Show error message
     */
    showError(message) {
        this.hideAllMessages();
        this.elements.errorText.textContent = utils.sanitizeInput(message);
        this.elements.errorMessage.classList.add('show');
        utils.announceToScreenReader(message, 'assertive');
    }
    
    /**
     * Show success message
     */
    showSuccess(message) {
        this.hideAllMessages();
        this.elements.successText.textContent = utils.sanitizeInput(message);
        this.elements.successMessage.classList.add('show');
        utils.announceToScreenReader(message, 'polite');
    }
    
    /**
     * Show warning message
     */
    showWarning(message) {
        this.hideAllMessages();
        this.elements.warningText.textContent = utils.sanitizeInput(message);
        this.elements.warningMessage.classList.add('show');
        utils.announceToScreenReader(message, 'polite');
    }
    
    /**
     * Show info message
     */
    showInfo(message) {
        const infoAlert = document.getElementById('infoAlert');
        const infoText = document.getElementById('infoText');
        
        if (infoAlert && infoText) {
            infoText.textContent = message;
            infoAlert.classList.add('show');
            utils.announceToScreenReader(message, 'polite');
        }
    }
    
    /**
     * Hide all messages
     */
    hideAllMessages() {
        document.querySelectorAll('.alert').forEach(alert => {
            alert.classList.remove('show');
        });
    }
    
    /**
     * Set loading state
     */
    setLoading(isLoading) {
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

// Initialize admin login when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.adminLogin = new AdminLogin();
    });
} else {
    window.adminLogin = new AdminLogin();
}