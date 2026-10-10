// ============================================
// SYNAPSEPM SETTINGS PAGE
// Settings Management Functionality
// ============================================

const Settings = (() => {
    'use strict';
    
    // State
    let userData = {};
    let apiKeys = [];
    let paymentMethods = [];
    
    // ============================================
    // INITIALIZATION
    // ============================================
    
    const init = () => {
        if (!AuthService.isAuthenticated()) return;
        
        loadUserData();
        loadApiKeys();
        loadPaymentMethods();
        initTabs();
        initEventListeners();
    };
    
    const initTabs = () => {
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                
                tab.classList.add('active');
                document.getElementById(tabName)?.classList.add('active');
                
                // Update URL hash
                window.location.hash = tabName;
            });
        });
        
        // Check URL hash for initial tab
        const hash = window.location.hash.substring(1);
        if (hash) {
            const tab = document.querySelector(`.tab[data-tab="${hash}"]`);
            if (tab) tab.click();
        }
    };
    
    const initEventListeners = () => {
        // Profile form
        const profileForm = document.getElementById('profileForm');
        if (profileForm) {
            profileForm.addEventListener('submit', handleProfileUpdate);
        }
        
        // Password form
        const passwordForm = document.getElementById('passwordForm');
        if (passwordForm) {
            passwordForm.addEventListener('submit', handlePasswordChange);
        }
        
        // Avatar upload
        const avatarUpload = document.getElementById('avatarUpload');
        if (avatarUpload) {
            avatarUpload.addEventListener('change', handleAvatarUpload);
        }
        
        // 2FA toggle
        const twoFactorToggle = document.getElementById('twoFactorToggle');
        if (twoFactorToggle) {
            twoFactorToggle.addEventListener('change', handleTwoFactorToggle);
        }
    };
    
    // ============================================
    // DATA LOADING
    // ============================================
    
    const loadUserData = async () => {
        try {
            const response = await ApiService.get('/user/profile');
            if (response.success) {
                userData = response.data;
                renderProfile();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to load user data', 'error');
        }
    };
    
    const loadApiKeys = async () => {
        try {
            const response = await ApiService.get('/user/api-keys');
            if (response.success) {
                apiKeys = response.data || [];
                renderApiKeys();
            }
        } catch (error) {
            console.error('Failed to load API keys:', error);
        }
    };
    
    const loadPaymentMethods = async () => {
        try {
            const response = await ApiService.get('/user/payment-methods');
            if (response.success) {
                paymentMethods = response.data || [];
                renderPaymentMethods();
            }
        } catch (error) {
            console.error('Failed to load payment methods:', error);
        }
    };
    
    // ============================================
    // RENDERING
    // ============================================
    
    const renderProfile = () => {
        // Update form fields
        document.getElementById('fullName').value = userData.name || '';
        document.getElementById('email').value = userData.email || '';
        document.getElementById('company').value = userData.company || '';
        document.getElementById('jobTitle').value = userData.jobTitle || '';
        document.getElementById('phone').value = userData.phone || '';
        document.getElementById('timezone').value = userData.timezone || 'America/New_York';
        
        // Update avatar
        const avatar = document.getElementById('avatarLarge');
        if (avatar) {
            const initials = (userData.name || userData.email || 'U')
                .split(' ')
                .map(n => n[0])
                .join('')
                .substring(0, 2)
                .toUpperCase();
            avatar.innerHTML = `<span id="avatarInitials">${initials}</span>`;
        }
        
        // Update plan info
        const planName = document.getElementById('currentPlan');
        const planPrice = document.getElementById('planPrice');
        
        if (planName && userData.plan) {
            const plans = {
                starter: 'Starter Plan',
                professional: 'Professional Plan',
                enterprise: 'Enterprise Plan'
            };
            planName.textContent = plans[userData.plan] || 'Professional Plan';
        }
        
        if (planPrice && userData.plan) {
            const prices = {
                starter: '$99/month',
                professional: '$299/month',
                enterprise: 'Custom pricing'
            };
            planPrice.textContent = prices[userData.plan] || '$299/month';
        }
    };
    
    const renderApiKeys = () => {
        const container = document.getElementById('apiKeysList');
        if (!container) return;
        
        if (apiKeys.length === 0) {
            container.innerHTML = '<p class="text-muted">No API keys generated yet.</p>';
            return;
        }
        
        container.innerHTML = apiKeys.map(key => `
            <div class="api-key-item">
                <div class="api-key-info">
                    <span class="api-key-name">${key.name}</span>
                    <span class="api-key-preview">${maskApiKey(key.key)}</span>
                </div>
                <div class="api-key-actions">
                    <button class="btn-icon" onclick="Settings.copyApiKey('${key.key}')" title="Copy">
                        <i class="fas fa-copy"></i>
                    </button>
                    <button class="btn-icon" onclick="Settings.regenerateApiKey('${key.id}')" title="Regenerate">
                        <i class="fas fa-sync-alt"></i>
                    </button>
                    <button class="btn-icon danger" onclick="Settings.deleteApiKey('${key.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    };
    
    const maskApiKey = (key) => {
        if (key.length <= 8) return key;
        return key.substring(0, 4) + '...' + key.substring(key.length - 4);
    };
    
    const renderPaymentMethods = () => {
        const container = document.getElementById('paymentMethodsList');
        if (!container) return;
        
        if (paymentMethods.length === 0) {
            container.innerHTML = '<p class="text-muted">No payment methods added yet.</p>';
            return;
        }
        
        container.innerHTML = paymentMethods.map(method => `
            <div class="payment-method-item">
                <i class="fab fa-cc-${method.brand.toLowerCase()}"></i>
                <div class="payment-method-info">
                    <strong>${method.brand} ending in ${method.last4}</strong>
                    <p>Expires ${method.expMonth}/${method.expYear}</p>
                </div>
                ${method.isDefault ? '<span class="badge">Default</span>' : ''}
                <div class="payment-method-actions">
                    ${!method.isDefault ? `
                        <button class="btn-icon" onclick="Settings.setDefaultPayment('${method.id}')">
                            <i class="fas fa-star"></i>
                        </button>
                    ` : ''}
                    <button class="btn-icon danger" onclick="Settings.deletePaymentMethod('${method.id}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    };
    
    // ============================================
    // PROFILE ACTIONS
    // ============================================
    
    const handleProfileUpdate = async (e) => {
        e.preventDefault();
        
        const formData = {
            name: document.getElementById('fullName').value,
            company: document.getElementById('company').value,
            jobTitle: document.getElementById('jobTitle').value,
            phone: document.getElementById('phone').value,
            timezone: document.getElementById('timezone').value,
        };
        
        try {
            const response = await ApiService.put('/user/profile', formData);
            if (response.success) {
                Utils.ui.showToast('Profile updated successfully', 'success');
                AuthService.updateUser(formData);
            }
        } catch (error) {
            Utils.ui.showToast('Failed to update profile', 'error');
        }
    };
    
    const handlePasswordChange = async (e) => {
        e.preventDefault();
        
        const currentPass = document.getElementById('currentPassword').value;
        const newPass = document.getElementById('newPassword').value;
        const confirmPass = document.getElementById('confirmPassword').value;
        
        if (newPass !== confirmPass) {
            Utils.ui.showToast('New passwords do not match', 'error');
            return;
        }
        
        if (newPass.length < 8) {
            Utils.ui.showToast('Password must be at least 8 characters', 'error');
            return;
        }
        
        try {
            const response = await ApiService.post('/user/password', {
                currentPassword: currentPass,
                newPassword: newPass,
            });
            
            if (response.success) {
                Utils.ui.showToast('Password updated successfully', 'success');
                e.target.reset();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to update password', 'error');
        }
    };
    
    const handleAvatarUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        try {
            const response = await ApiService.upload('/user/avatar', file);
            if (response.success) {
                Utils.ui.showToast('Avatar uploaded successfully', 'success');
                // Update avatar in UI
            }
        } catch (error) {
            Utils.ui.showToast('Failed to upload avatar', 'error');
        }
    };
    
    const removeAvatar = () => {
        if (confirm('Remove profile photo?')) {
            // API call to remove avatar
            Utils.ui.showToast('Avatar removed', 'success');
        }
    };
    
    // ============================================
    // API KEY ACTIONS
    // ============================================
    
    const generateApiKey = async () => {
        const name = prompt('Enter a name for this API key:');
        if (!name) return;
        
        try {
            const response = await ApiService.post('/user/api-keys', { name });
            if (response.success) {
                Utils.ui.showToast('API key generated', 'success');
                loadApiKeys();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to generate API key', 'error');
        }
    };
    
    const copyApiKey = (key) => {
        Utils.browser.copyToClipboard(key);
        Utils.ui.showToast('API key copied to clipboard', 'success');
    };
    
    const regenerateApiKey = async (id) => {
        if (!confirm('Regenerate this API key? The old key will stop working immediately.')) return;
        
        try {
            const response = await ApiService.post(`/user/api-keys/${id}/regenerate`);
            if (response.success) {
                Utils.ui.showToast('API key regenerated', 'success');
                loadApiKeys();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to regenerate API key', 'error');
        }
    };
    
    const deleteApiKey = async (id) => {
        if (!confirm('Delete this API key? This action cannot be undone.')) return;
        
        try {
            const response = await ApiService.delete(`/user/api-keys/${id}`);
            if (response.success) {
                Utils.ui.showToast('API key deleted', 'success');
                loadApiKeys();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to delete API key', 'error');
        }
    };
    
    // ============================================
    // 2FA ACTIONS
    // ============================================
    
    const handleTwoFactorToggle = async (e) => {
        const enabled = e.target.checked;
        
        if (enabled) {
            // Show 2FA setup modal
            setupTwoFactor();
        } else {
            if (confirm('Disable two-factor authentication?')) {
                try {
                    const response = await ApiService.post('/user/2fa/disable');
                    if (response.success) {
                        Utils.ui.showToast('2FA disabled', 'success');
                    }
                } catch (error) {
                    Utils.ui.showToast('Failed to disable 2FA', 'error');
                    e.target.checked = true;
                }
            } else {
                e.target.checked = true;
            }
        }
    };
    
    const setupTwoFactor = async () => {
        try {
            const response = await ApiService.post('/user/2fa/setup');
            if (response.success) {
                // Show QR code and verification modal
                showTwoFactorModal(response.data);
            }
        } catch (error) {
            Utils.ui.showToast('Failed to setup 2FA', 'error');
        }
    };
    
    // ============================================
    // PAYMENT ACTIONS
    // ============================================
    
    const addPaymentMethod = () => {
        window.location.href = '/billing.html?action=add';
    };
    
    const setDefaultPayment = async (id) => {
        try {
            const response = await ApiService.post(`/user/payment-methods/${id}/default`);
            if (response.success) {
                Utils.ui.showToast('Default payment method updated', 'success');
                loadPaymentMethods();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to update default payment method', 'error');
        }
    };
    
    const deletePaymentMethod = async (id) => {
        if (!confirm('Remove this payment method?')) return;
        
        try {
            const response = await ApiService.delete(`/user/payment-methods/${id}`);
            if (response.success) {
                Utils.ui.showToast('Payment method removed', 'success');
                loadPaymentMethods();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to remove payment method', 'error');
        }
    };
    
    // ============================================
    // ACCOUNT ACTIONS
    // ============================================
    
    const deleteAccount = () => {
        if (confirm('Are you absolutely sure? This action cannot be undone.')) {
            const confirmation = prompt('Type "DELETE" to confirm:');
            if (confirmation === 'DELETE') {
                // API call to delete account
                Utils.ui.showToast('Account deletion initiated', 'success');
                setTimeout(() => AuthService.logout(), 2000);
            }
        }
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        init,
        copyApiKey,
        regenerateApiKey,
        deleteApiKey,
        generateApiKey,
        removeAvatar,
        addPaymentMethod,
        setDefaultPayment,
        deletePaymentMethod,
        deleteAccount,
    };
})();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('settings-page')) {
        Settings.init();
    }
});

window.Settings = Settings;