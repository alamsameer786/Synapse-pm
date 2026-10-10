// ============================================================
// SYNAPSEPM - COMPLETE ADMIN MODULE v3.0
// Enterprise Admin Dashboard with Auth.js Integration
// All features: RBAC, CRUD, Charts, Reports, System Control
// ============================================================

// ============================================================
// 1. ADMIN CONFIGURATION
// ============================================================
const ADMIN_CONFIG = {
    API_BASE_URL: window.ENV?.API_URL || window.location.origin,
    TOKEN_KEY: 'synapse_admin_token',
    USER_KEY: 'synapse_admin_user',
    REDIRECT_KEY: 'redirectAfterAdminLogin',
    ALLOWED_ROLES: ['super_admin', 'admin'],
    SESSION_TIMEOUT: 30 * 60 * 1000, // 30 minutes
    AUTO_REFRESH_INTERVAL: 30000, // 30 seconds
    MAX_ACTIVITIES: 500,
    DEFAULT_PLAN: 'free',
    PLANS: {
        free: { label: 'Free', color: 'bg-slate-100 text-slate-700' },
        starter: { label: 'Starter', color: 'bg-green-100 text-green-700' },
        professional: { label: 'Professional', color: 'bg-blue-100 text-blue-700' },
        enterprise: { label: 'Enterprise', color: 'bg-purple-100 text-purple-700' }
    }
};

// ============================================================
// 2. ADMIN STATE
// ============================================================
let currentAdmin = null;
let pendingDelete = { type: null, id: null };
let users = [], machines = [], alerts = [], predictions = [], activities = [];
let userGrowthChart = null, adminTrendChart = null;
let isSystemOnline = true;
let autoRefreshInterval = null;
let currentSection = 'dashboard';
let adminStats = {};

// ============================================================
// 3. ADMIN AUTHENTICATION - USING AUTH.JS
// ============================================================

/**
 * Check if current user is admin
 */
function isAdmin() {
    try {
        const user = window.Auth?.user;
        return user && ADMIN_CONFIG.ALLOWED_ROLES.includes(user.role);
    } catch (e) {
        return false;
    }
}

/**
 * Check admin authentication and initialize dashboard
 */
function checkAdminAuth() {
    try {
        // Check if Auth module is loaded
        if (typeof window.Auth === 'undefined') {
            console.warn('Auth module not loaded, using localStorage fallback');
            return checkAdminAuthFallback();
        }

        // Use Auth.js to check authentication
        if (!window.Auth.isAuthenticated) {
            showAuthModal();
            return false;
        }

        const user = window.Auth.user;
        if (!user || !ADMIN_CONFIG.ALLOWED_ROLES.includes(user.role)) {
            showAuthModal();
            return false;
        }

        // Store admin data
        currentAdmin = user;
        localStorage.setItem(ADMIN_CONFIG.USER_KEY, JSON.stringify(user));
        localStorage.setItem(ADMIN_CONFIG.TOKEN_KEY, window.Auth.token || '');

        // Show dashboard
        showDashboardContent();
        updateAdminInfo();
        loadAllData();
        loadSystemStatus();
        startAutoRefresh();

        // Log admin login
        logActivity('admin_login', 'Admin logged in', user.email);

        return true;
    } catch (e) {
        console.error('Admin auth error:', e);
        showAuthModal();
        return false;
    }
}

/**
 * Fallback authentication if Auth.js not loaded
 */
function checkAdminAuthFallback() {
    try {
        const token = localStorage.getItem(ADMIN_CONFIG.TOKEN_KEY);
        const adminStr = localStorage.getItem(ADMIN_CONFIG.USER_KEY);

        if (!token || !adminStr) {
            showAuthModal();
            return false;
        }

        currentAdmin = JSON.parse(adminStr);
        if (!ADMIN_CONFIG.ALLOWED_ROLES.includes(currentAdmin.role)) {
            showAuthModal();
            return false;
        }

        showDashboardContent();
        updateAdminInfo();
        loadAllData();
        loadSystemStatus();
        startAutoRefresh();

        return true;
    } catch (e) {
        console.error('Fallback auth error:', e);
        showAuthModal();
        return false;
    }
}

/**
 * Show dashboard content
 */
function showDashboardContent() {
    const content = document.getElementById('dashboardContent');
    const modal = document.getElementById('authModal');
    if (content) content.style.display = 'block';
    if (modal) modal.classList.remove('active');
    document.body.style.overflow = '';
}

/**
 * Show authentication modal
 */
function showAuthModal() {
    const modal = document.getElementById('authModal');
    const content = document.getElementById('dashboardContent');
    if (modal) modal.classList.add('active');
    if (content) content.style.display = 'none';
    document.body.style.overflow = 'hidden';
}

/**
 * Hide authentication modal
 */
function hideAuthModal() {
    const modal = document.getElementById('authModal');
    const content = document.getElementById('dashboardContent');
    if (modal) modal.classList.remove('active');
    if (content) content.style.display = 'block';
    document.body.style.overflow = '';
}

/**
 * Update admin info in UI
 */
function updateAdminInfo() {
    try {
        if (!currentAdmin) return;

        const name = currentAdmin.display_name || currentAdmin.full_name || currentAdmin.name || 'Administrator';
        const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
        const email = currentAdmin.email || '';

        const elements = {
            'adminName': name,
            'adminEmail': email,
            'adminAvatar': initials,
            'headerAdminName': name,
            'mobileAdminName': name,
            'mobileAdminEmail': email,
            'mobileAdminAvatar': initials,
            'mobileAdminAvatarFull': initials,
            'adminRole': currentAdmin.role?.replace('_', ' ').toUpperCase() || 'ADMIN'
        };

        Object.entries(elements).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });

        // Update role badge
        const roleBadge = document.getElementById('adminRoleBadge');
        if (roleBadge) {
            const isSuper = currentAdmin.role === 'super_admin';
            roleBadge.textContent = isSuper ? '🔑 Super Admin' : '⚙️ Admin';
            roleBadge.className = `text-xs px-3 py-1 rounded-full ${isSuper ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`;
        }

    } catch (e) {
        console.error('Error updating admin info:', e);
    }
}

/**
 * Admin logout
 */
function adminLogout() {
    try {
        if (autoRefreshInterval) {
            clearInterval(autoRefreshInterval);
            autoRefreshInterval = null;
        }

        // Log logout
        logActivity('admin_logout', 'Admin logged out', currentAdmin?.email || 'Admin');

        // Clear storage
        localStorage.removeItem(ADMIN_CONFIG.TOKEN_KEY);
        localStorage.removeItem(ADMIN_CONFIG.USER_KEY);
        sessionStorage.removeItem(ADMIN_CONFIG.TOKEN_KEY);
        sessionStorage.removeItem(ADMIN_CONFIG.USER_KEY);
        currentAdmin = null;

        // If Auth.js is available, use it
        if (typeof window.Auth !== 'undefined' && window.Auth.logout) {
            window.Auth.logout();
        }

        showAuthModal();
        showToast('Logged out successfully', 'success');

        // Redirect to login after 1.5s
        setTimeout(() => {
            window.location.href = 'login.html';
        }, 1500);

    } catch (e) {
        console.error('Logout error:', e);
        window.location.href = 'login.html';
    }
}

// ============================================================
// 4. SYSTEM STATUS
// ============================================================

function loadSystemStatus() {
    try {
        const saved = localStorage.getItem('synapse_system_online');
        isSystemOnline = saved !== null ? saved === 'true' : true;
    } catch (e) {
        isSystemOnline = true;
    }
    updateSystemStatusUI();
}

function updateSystemStatusUI() {
    const statusBadge = document.getElementById('systemStatusBadge');
    if (statusBadge) {
        statusBadge.textContent = isSystemOnline ? '🟢 Online' : '🔴 Offline';
        statusBadge.className = isSystemOnline ? 
            'text-lg sm:text-3xl font-bold text-success mt-1' : 
            'text-lg sm:text-3xl font-bold text-error mt-1';
    }

    const offlineOverlay = document.getElementById('systemOfflineOverlay');
    if (offlineOverlay) {
        if (!isSystemOnline) {
            offlineOverlay.classList.add('active');
            offlineOverlay.style.display = 'flex';
        } else {
            offlineOverlay.classList.remove('active');
            offlineOverlay.style.display = 'none';
        }
    }

    // Update status indicator in sidebar
    const statusIndicator = document.getElementById('systemStatusIndicator');
    if (statusIndicator) {
        statusIndicator.className = `w-2 h-2 rounded-full ${isSystemOnline ? 'bg-success' : 'bg-error'}`;
        statusIndicator.title = isSystemOnline ? 'System Online' : 'System Offline';
    }
}

function toggleSystemStatus() {
    isSystemOnline = !isSystemOnline;
    localStorage.setItem('synapse_system_online', isSystemOnline.toString());
    updateSystemStatusUI();
    logActivity('system_status_changed', 
        `System status changed to ${isSystemOnline ? 'Online' : 'Offline'}`, 
        currentAdmin?.email || 'Admin');
    showToast(`System is now ${isSystemOnline ? 'Online' : 'Offline'}`, 
        isSystemOnline ? 'success' : 'warning');

    // If going offline, stop auto-refresh
    if (!isSystemOnline && autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    } else if (isSystemOnline && !autoRefreshInterval) {
        startAutoRefresh();
    }
}

// ============================================================
// 5. ACTIVITY LOGGING (Real Database Storage)
// ============================================================

function logActivity(action, details, adminName) {
    try {
        const activity = {
            id: 'act_' + Date.now() + '_' + Math.random().toString(36).substring(2, 8),
            action: action,
            details: details || '',
            admin: adminName || currentAdmin?.email || 'System',
            admin_id: currentAdmin?.id || 'system',
            timestamp: new Date().toISOString(),
            ip: getClientIP(),
            user_agent: navigator.userAgent
        };

        // Store locally
        const activities = getActivities();
        activities.unshift(activity);
        if (activities.length > ADMIN_CONFIG.MAX_ACTIVITIES) {
            activities.splice(ADMIN_CONFIG.MAX_ACTIVITIES);
        }
        saveActivities(activities);

        // Send to backend if available
        if (typeof window.Auth !== 'undefined' && window.Auth.isAuthenticated) {
            try {
                fetch(`${ADMIN_CONFIG.API_BASE_URL}/api/v1/admin/activities`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${localStorage.getItem(ADMIN_CONFIG.TOKEN_KEY) || ''}`
                    },
                    body: JSON.stringify(activity)
                }).catch(() => {});
            } catch (e) {}
        }

        // Update UI if on activities section
        if (currentSection === 'activities') {
            renderActivitiesTable();
        }

        return activity;
    } catch (e) {
        console.error('Error logging activity:', e);
        return null;
    }
}

function getClientIP() {
    try {
        // Try to get IP from API
        return fetch('https://api.ipify.org?format=json')
            .then(res => res.json())
            .then(data => data.ip)
            .catch(() => 'unknown');
    } catch {
        return 'unknown';
    }
}

// ============================================================
// 6. DATABASE HELPERS (localStorage + API)
// ============================================================

function getUsers() {
    try {
        const data = localStorage.getItem('synapse_users');
        return data ? JSON.parse(data) : [];
    } catch (e) {
        console.error('Error loading users:', e);
        return [];
    }
}

function saveUsers(data) {
    try {
        localStorage.setItem('synapse_users', JSON.stringify(data));
        // Sync with backend
        syncToBackend('users', data);
    } catch (e) {
        console.error('Error saving users:', e);
    }
}

function getMachines() {
    try {
        const data = localStorage.getItem('synapse_machines');
        return data ? JSON.parse(data) : [];
    } catch (e) {
        console.error('Error loading machines:', e);
        return [];
    }
}

function saveMachines(data) {
    try {
        localStorage.setItem('synapse_machines', JSON.stringify(data));
        syncToBackend('machines', data);
    } catch (e) {
        console.error('Error saving machines:', e);
    }
}

function getAlerts() {
    try {
        const data = localStorage.getItem('synapse_alerts');
        return data ? JSON.parse(data) : [];
    } catch (e) {
        console.error('Error loading alerts:', e);
        return [];
    }
}

function saveAlerts(data) {
    try {
        localStorage.setItem('synapse_alerts', JSON.stringify(data));
        syncToBackend('alerts', data);
    } catch (e) {
        console.error('Error saving alerts:', e);
    }
}

function getPredictions() {
    try {
        const data = localStorage.getItem('synapse_prediction_history');
        return data ? JSON.parse(data) : [];
    } catch (e) {
        console.error('Error loading predictions:', e);
        return [];
    }
}

function savePredictions(data) {
    try {
        localStorage.setItem('synapse_prediction_history', JSON.stringify(data));
        syncToBackend('predictions', data);
    } catch (e) {
        console.error('Error saving predictions:', e);
    }
}

function getActivities() {
    try {
        const data = localStorage.getItem('synapse_admin_activities');
        return data ? JSON.parse(data) : [];
    } catch (e) {
        console.error('Error loading activities:', e);
        return [];
    }
}

function saveActivities(data) {
    try {
        localStorage.setItem('synapse_admin_activities', JSON.stringify(data));
        syncToBackend('activities', data);
    } catch (e) {
        console.error('Error saving activities:', e);
    }
}

function syncToBackend(collection, data) {
    try {
        if (typeof window.Auth !== 'undefined' && window.Auth.isAuthenticated) {
            fetch(`${ADMIN_CONFIG.API_BASE_URL}/api/v1/admin/sync/${collection}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem(ADMIN_CONFIG.TOKEN_KEY) || ''}`
                },
                body: JSON.stringify(data)
            }).catch(() => {});
        }
    } catch (e) {}
}

// ============================================================
// 7. API CALLS (Real Backend Integration)
// ============================================================

async function adminApiRequest(endpoint, options = {}) {
    const token = localStorage.getItem(ADMIN_CONFIG.TOKEN_KEY) || window.Auth?.token || '';
    const url = `${ADMIN_CONFIG.API_BASE_URL}${endpoint}`;
    
    const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Admin-Request': 'true',
        ...(token && { 'Authorization': `Bearer ${token}` }),
        ...options.headers
    };

    try {
        const response = await fetch(url, {
            ...options,
            headers,
            credentials: 'include'
        });

        if (response.status === 401 || response.status === 403) {
            adminLogout();
            throw new Error('Session expired or insufficient permissions');
        }

        if (response.status === 429) {
            const retryAfter = response.headers.get('Retry-After') || 60;
            throw new Error(`Rate limited. Try again in ${retryAfter}s`);
        }

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.message || error.error || `HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`Admin API Error (${endpoint}):`, error);
        throw error;
    }
}

async function fetchAdminStats() {
    try {
        const data = await adminApiRequest('/api/v1/admin/stats');
        adminStats = data;
        return data;
    } catch (error) {
        console.error('Failed to fetch admin stats:', error);
        return null;
    }
}

async function fetchAdminUsers(page = 1, limit = 50) {
    try {
        const data = await adminApiRequest(`/api/v1/admin/users?page=${page}&limit=${limit}`);
        if (data && data.items) {
            users = data.items;
            saveUsers(users);
        }
        return data;
    } catch (error) {
        console.error('Failed to fetch admin users:', error);
        return null;
    }
}

async function fetchAdminOrganizations() {
    try {
        return await adminApiRequest('/api/v1/admin/organizations');
    } catch (error) {
        console.error('Failed to fetch organizations:', error);
        return null;
    }
}

async function deleteUserAPI(userId) {
    try {
        return await adminApiRequest(`/api/v1/admin/users/${userId}`, {
            method: 'DELETE'
        });
    } catch (error) {
        console.error('Failed to delete user:', error);
        throw error;
    }
}

async function deleteMachineAPI(machineId) {
    try {
        return await adminApiRequest(`/api/v1/admin/machines/${machineId}`, {
            method: 'DELETE'
        });
    } catch (error) {
        console.error('Failed to delete machine:', error);
        throw error;
    }
}

// ============================================================
// 8. LOAD DATA
// ============================================================

function loadAllData() {
    try {
        // Load from localStorage (fast)
        users = getUsers();
        machines = getMachines();
        alerts = getAlerts();
        predictions = getPredictions();
        activities = getActivities();

        // Ensure at least one admin exists
        ensureDefaultAdmin();

        // Update UI
        updateDashboardStats();
        updateCharts();
        renderAllTables();
        updateRecentUsers();
        updateBadges();

        // Fetch fresh data from backend (async)
        fetchAdminData();

    } catch (e) {
        console.error('Error loading data:', e);
        showToast('Error loading data. Please refresh.', 'error');
    }
}

function ensureDefaultAdmin() {
    try {
        const hasAdmin = users.some(u => ADMIN_CONFIG.ALLOWED_ROLES.includes(u.role));
        if (!hasAdmin) {
            const defaultAdmin = {
                id: 'admin_' + Date.now(),
                name: 'System Administrator',
                email: 'admin@synapsepm.com',
                role: 'super_admin',
                plan: 'enterprise',
                createdAt: new Date().toISOString(),
                verified: true,
                mfa_enabled: false
            };
            users.push(defaultAdmin);
            saveUsers(users);
            console.log('✅ Default admin created');
        }
    } catch (e) {
        console.error('Error ensuring default admin:', e);
    }
}

async function fetchAdminData() {
    try {
        // Fetch stats
        const stats = await fetchAdminStats();
        if (stats) {
            document.getElementById('totalUsers').textContent = stats.total_users || users.length;
            document.getElementById('totalMachines').textContent = stats.total_machines || machines.length;
            document.getElementById('totalAlerts').textContent = stats.active_alerts || alerts.filter(a => a.status !== 'resolved').length;
            document.getElementById('totalRevenue').textContent = `$${(stats.revenue || 0).toLocaleString()}`;
            document.getElementById('activeSubscriptions').textContent = stats.active_subscriptions || 0;
        }

        // Fetch users
        const usersData = await fetchAdminUsers();
        if (usersData && usersData.items) {
            users = usersData.items;
            renderUsersTable();
            updateRecentUsers();
            updateDashboardStats();
        }

    } catch (error) {
        console.error('Failed to fetch admin data:', error);
    }
}

function renderAllTables() {
    renderUsersTable();
    renderMachinesTable();
    renderAlertsTable();
    renderActivitiesTable();
}

// ============================================================
// 9. RENDER FUNCTIONS
// ============================================================

function renderUsersTable() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    try {
        const regularUsers = users.filter(u => !ADMIN_CONFIG.ALLOWED_ROLES.includes(u.role));
        if (regularUsers.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-slate-500">No users found</td></tr>`;
            return;
        }

        tbody.innerHTML = regularUsers.map(user => {
            const planConfig = ADMIN_CONFIG.PLANS[user.plan] || ADMIN_CONFIG.PLANS[ADMIN_CONFIG.DEFAULT_PLAN];
            return `
            <tr class="border-b border-border-light hover:bg-slate-50 transition-colors">
                <td class="px-4 sm:px-6 py-3">
                    <div class="flex items-center gap-2 sm:gap-3">
                        <div class="w-7 h-7 sm:w-8 sm:h-8 rounded-full gradient-primary flex items-center justify-center text-white text-[10px] sm:text-xs font-bold">
                            ${escapeHtml((user.name || user.email?.[0] || 'U').substring(0,2).toUpperCase())}
                        </div>
                        <span class="font-medium text-primary text-sm">${escapeHtml(user.name || user.email?.split('@')[0] || 'User')}</span>
                    </div>
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">${escapeHtml(user.email || '')}</td>
                <td class="px-4 sm:px-6 py-3">
                    <span class="text-[10px] sm:text-xs px-2 py-1 rounded-full ${planConfig.color}">
                        ${planConfig.label}
                    </span>
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">
                    ${machines.filter(m => m.userId === user.id).length}
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">
                    ${user.createdAt ? formatDate(user.createdAt) : 'N/A'}
                </td>
                <td class="px-4 sm:px-6 py-3">
                    <div class="flex gap-1 sm:gap-2">
                        <button onclick="editUser('${user.id}')" class="p-1.5 rounded-lg hover:bg-slate-100 transition-colors" title="Edit">
                            <span class="material-symbols-outlined text-sm text-info">edit</span>
                        </button>
                        <button onclick="deleteUser('${user.id}')" class="p-1.5 rounded-lg hover:bg-slate-100 transition-colors" title="Delete">
                            <span class="material-symbols-outlined text-sm text-error">delete</span>
                        </button>
                    </div>
                </td>
            </tr>
        `}).join('');
    } catch (e) {
        console.error('Error rendering users:', e);
        tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-red-500">Error loading users</td></tr>`;
    }
}

function renderMachinesTable() {
    const tbody = document.getElementById('machinesTableBody');
    if (!tbody) return;

    try {
        if (machines.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-slate-500">No machines found</td></tr>`;
            return;
        }

        const ownerNames = Object.fromEntries(users.map(u => [u.id, u.name || u.email]));

        tbody.innerHTML = machines.map(machine => {
            const statusColors = {
                critical: 'bg-red-100 text-red-700',
                warning: 'bg-yellow-100 text-yellow-700',
                good: 'bg-green-100 text-green-700',
                offline: 'bg-slate-100 text-slate-700'
            };
            const statusLabel = (machine.status || 'good').charAt(0).toUpperCase() + (machine.status || 'good').slice(1);
            const health = machine.health || 85;
            const healthColor = health < 40 ? 'bg-red-500' : health < 70 ? 'bg-yellow-500' : 'bg-green-500';
            
            return `
            <tr class="border-b border-border-light hover:bg-slate-50 transition-colors">
                <td class="px-4 sm:px-6 py-3">
                    <div class="flex items-center gap-2">
                        <span class="material-symbols-outlined text-secondary text-base sm:text-lg">precision_manufacturing</span>
                        <span class="font-medium text-primary text-sm">${escapeHtml(machine.name || 'Unnamed')}</span>
                    </div>
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">
                    ${escapeHtml(ownerNames[machine.userId] || 'Unknown')}
                </td>
                <td class="px-4 sm:px-6 py-3">
                    <span class="text-[10px] sm:text-xs px-2 py-1 rounded-full ${statusColors[machine.status] || statusColors.good}">
                        ${statusLabel}
                    </span>
                </td>
                <td class="px-4 sm:px-6 py-3">
                    <div class="flex items-center gap-2">
                        <div class="w-12 sm:w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div class="h-full ${healthColor}" style="width: ${health}%"></div>
                        </div>
                        <span class="text-xs sm:text-sm font-medium">${health}%</span>
                    </div>
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">
                    ${escapeHtml(machine.location || 'Not set')}
                </td>
                <td class="px-4 sm:px-6 py-3">
                    <div class="flex gap-1 sm:gap-2">
                        <button onclick="editMachine('${machine.id}')" class="p-1.5 rounded-lg hover:bg-slate-100 transition-colors" title="Edit">
                            <span class="material-symbols-outlined text-sm text-info">edit</span>
                        </button>
                        <button onclick="deleteMachine('${machine.id}')" class="p-1.5 rounded-lg hover:bg-slate-100 transition-colors" title="Delete">
                            <span class="material-symbols-outlined text-sm text-error">delete</span>
                        </button>
                    </div>
                </td>
            </tr>
        `}).join('');
    } catch (e) {
        console.error('Error rendering machines:', e);
        tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-red-500">Error loading machines</td></tr>`;
    }
}

function renderAlertsTable() {
    const tbody = document.getElementById('alertsTableBody');
    if (!tbody) return;

    try {
        if (alerts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-slate-500">No alerts found</td></tr>`;
            return;
        }

        const ownerNames = Object.fromEntries(users.map(u => [u.id, u.name || u.email]));
        const machineNames = Object.fromEntries(machines.map(m => [m.id, m.name]));

        tbody.innerHTML = alerts.slice(0, 100).map(alert => {
            const severityColors = {
                critical: 'bg-red-100 text-red-700',
                high: 'bg-orange-100 text-orange-700',
                warning: 'bg-yellow-100 text-yellow-700',
                info: 'bg-blue-100 text-blue-700'
            };
            const statusColors = {
                resolved: 'bg-green-100 text-green-700',
                acknowledged: 'bg-blue-100 text-blue-700',
                active: 'bg-yellow-100 text-yellow-700'
            };
            
            return `
            <tr class="border-b border-border-light hover:bg-slate-50 transition-colors">
                <td class="px-4 sm:px-6 py-3">
                    <div class="flex items-center gap-2">
                        <span class="material-symbols-outlined ${alert.severity === 'critical' ? 'text-error' : alert.severity === 'high' ? 'text-orange-500' : alert.severity === 'warning' ? 'text-warning' : 'text-info'} text-base sm:text-lg">
                            ${alert.severity === 'critical' ? 'emergency' : 'warning'}
                        </span>
                        <span class="font-medium text-primary text-sm">${escapeHtml(alert.title || 'Equipment Alert')}</span>
                    </div>
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">
                    ${escapeHtml(ownerNames[alert.userId] || 'Unknown')}
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">
                    ${escapeHtml(machineNames[alert.machineId] || 'Unknown')}
                </td>
                <td class="px-4 sm:px-6 py-3">
                    <span class="text-[10px] sm:text-xs px-2 py-1 rounded-full ${severityColors[alert.severity] || severityColors.info}">
                        ${alert.severity || 'info'}
                    </span>
                </td>
                <td class="px-4 sm:px-6 py-3 text-xs sm:text-sm text-slate-600">
                    ${formatTimeAgo(alert.timestamp)}
                </td>
                <td class="px-4 sm:px-6 py-3">
                    <span class="text-[10px] sm:text-xs px-2 py-1 rounded-full ${statusColors[alert.status] || statusColors.active}">
                        ${alert.status || 'active'}
                    </span>
                </td>
            </tr>
        `}).join('');
    } catch (e) {
        console.error('Error rendering alerts:', e);
        tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-8 text-center text-red-500">Error loading alerts</td></tr>`;
    }
}

function renderActivitiesTable() {
    const tbody = document.getElementById('activitiesTableBody');
    if (!tbody) return;

    try {
        if (activities.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="px-6 py-8 text-center text-slate-500">No activities logged</td></tr>`;
            return;
        }

        tbody.innerHTML = activities.slice(0, 100).map(act => `
            <tr class="border-b border-border-light hover:bg-slate-50 transition-colors">
                <td class="px-4 sm:px-6 py-3">
                    <span class="text-sm font-medium text-slate-700">${escapeHtml(act.action)}</span>
                </td>
                <td class="px-4 sm:px-6 py-3 text-sm text-slate-500">${escapeHtml(act.details)}</td>
                <td class="px-4 sm:px-6 py-3 text-sm text-slate-500">${escapeHtml(act.admin)}</td>
                <td class="px-4 sm:px-6 py-3 text-sm text-slate-500">${formatTimeAgo(act.timestamp)}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Error rendering activities:', e);
        tbody.innerHTML = `<tr><td colspan="4" class="px-6 py-8 text-center text-red-500">Error loading activities</td></tr>`;
    }
}

// ============================================================
// 10. DASHBOARD STATS
// ============================================================

function updateDashboardStats() {
    try {
        const regularUsers = users.filter(u => !ADMIN_CONFIG.ALLOWED_ROLES.includes(u.role));
        const totalUsers = regularUsers.length;
        const totalMachines = machines.length;
        const activeAlerts = alerts.filter(a => a.status !== 'resolved').length;
        const paidUsers = regularUsers.filter(u => u.plan && u.plan !== 'free').length;
        const estimatedRevenue = paidUsers * 99;

        // Update stat cards
        const stats = {
            totalUsers: totalUsers,
            totalMachines: totalMachines,
            totalAlerts: activeAlerts,
            totalRevenue: estimatedRevenue,
            activeSubscriptions: paidUsers
        };

        Object.entries(stats).forEach(([key, value]) => {
            const el = document.getElementById(key);
            if (el) {
                if (key === 'totalRevenue') {
                    el.textContent = `$${value.toLocaleString()}`;
                } else {
                    el.textContent = value;
                }
            }
        });

        // Update sidebar badges
        const badges = {
            sidebarUsersBadge: totalUsers,
            sidebarMachinesBadge: totalMachines,
            sidebarAlertsBadge: activeAlerts
        };
        Object.entries(badges).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = value;
                el.style.display = value > 0 ? 'inline-block' : 'none';
            }
        });

        // Update admin stats
        adminStats = stats;

    } catch (e) {
        console.error('Error updating dashboard stats:', e);
    }
}

function updateRecentUsers() {
    const container = document.getElementById('recentUsersList');
    if (!container) return;

    try {
        const recent = users
            .filter(u => !ADMIN_CONFIG.ALLOWED_ROLES.includes(u.role))
            .sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0))
            .slice(0, 5);

        if (recent.length === 0) {
            container.innerHTML = `<div class="px-4 sm:px-6 py-6 sm:py-8 text-center text-slate-500 text-sm">No users yet</div>`;
            return;
        }

        container.innerHTML = recent.map(user => {
            const planConfig = ADMIN_CONFIG.PLANS[user.plan] || ADMIN_CONFIG.PLANS[ADMIN_CONFIG.DEFAULT_PLAN];
            return `
            <div class="px-4 sm:px-6 py-3 sm:py-4 flex flex-wrap justify-between items-center hover:bg-slate-50 gap-3 transition-colors">
                <div class="flex items-center gap-2 sm:gap-3">
                    <div class="w-8 h-8 sm:w-10 sm:h-10 rounded-full gradient-primary flex items-center justify-center text-white font-bold text-xs sm:text-sm">
                        ${escapeHtml((user.name || user.email?.[0] || 'U').substring(0,2).toUpperCase())}
                    </div>
                    <div>
                        <p class="font-medium text-primary text-sm">${escapeHtml(user.name || user.email?.split('@')[0] || 'User')}</p>
                        <p class="text-[10px] sm:text-xs text-slate-500">${escapeHtml(user.email || '')}</p>
                    </div>
                </div>
                <div class="text-right">
                    <span class="text-[10px] sm:text-xs px-2 py-1 rounded-full ${planConfig.color}">
                        ${planConfig.label}
                    </span>
                    <p class="text-[10px] sm:text-xs text-slate-400 mt-1">${user.createdAt ? formatDate(user.createdAt) : 'N/A'}</p>
                </div>
            </div>
        `}).join('');
    } catch (e) {
        console.error('Error updating recent users:', e);
        container.innerHTML = `<div class="px-4 sm:px-6 py-6 sm:py-8 text-center text-red-500 text-sm">Error loading recent users</div>`;
    }
}

function updateBadges() {
    const regularUsers = users.filter(u => !ADMIN_CONFIG.ALLOWED_ROLES.includes(u.role));
    const activeAlerts = alerts.filter(a => a.status !== 'resolved').length;
    
    const badges = {
        sidebarUsersBadge: regularUsers.length,
        sidebarMachinesBadge: machines.length,
        sidebarAlertsBadge: activeAlerts
    };
    
    Object.entries(badges).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = value;
            el.style.display = value > 0 ? 'inline-block' : 'none';
        }
    });
}

// ============================================================
// 11. CHARTS
// ============================================================

function initCharts() {
    try {
        const ctx1 = document.getElementById('userGrowthChart')?.getContext('2d');
        const ctx2 = document.getElementById('adminTrendChart')?.getContext('2d');

        if (ctx1 && typeof Chart !== 'undefined') {
            userGrowthChart = new Chart(ctx1, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'New Users',
                        data: [],
                        borderColor: '#00b4aa',
                        backgroundColor: 'rgba(0, 180, 170, 0.05)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 3,
                        pointBackgroundColor: '#00b4aa'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.8)',
                            titleColor: '#fff',
                            bodyColor: '#fff'
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(0,0,0,0.05)' }
                        },
                        x: {
                            grid: { display: false }
                        }
                    }
                }
            });
        }

        if (ctx2 && typeof Chart !== 'undefined') {
            adminTrendChart = new Chart(ctx2, {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Predictions',
                        data: [],
                        backgroundColor: '#3b82f6',
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(0,0,0,0.8)',
                            titleColor: '#fff',
                            bodyColor: '#fff'
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(0,0,0,0.05)' }
                        },
                        x: {
                            grid: { display: false }
                        }
                    }
                }
            });
        }
    } catch (e) {
        console.error('Error initializing charts:', e);
    }
}

function updateCharts() {
    try {
        const last30Days = Array.from({ length: 30 }, (_, i) => {
            const d = new Date();
            d.setDate(d.getDate() - (29 - i));
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        });

        // User growth data
        const userCounts = last30Days.map(date => {
            return users.filter(u => u.createdAt && 
                new Date(u.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) === date).length;
        });

        // Prediction data
        const predCounts = last30Days.map(date => {
            return predictions.filter(p => p.timestamp && 
                new Date(p.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) === date).length;
        });

        // Update user growth chart
        if (userGrowthChart) {
            userGrowthChart.data.labels = last30Days;
            userGrowthChart.data.datasets[0].data = userCounts;
            userGrowthChart.update('none');
        }

        // Update prediction trend chart
        if (adminTrendChart) {
            adminTrendChart.data.labels = last30Days;
            adminTrendChart.data.datasets[0].data = predCounts;
            adminTrendChart.update('none');
        }
    } catch (e) {
        console.error('Error updating charts:', e);
    }
}

// ============================================================
// 12. CRUD OPERATIONS
// ============================================================

function openUserModal(userId = null) {
    try {
        const title = document.getElementById('userModalTitle');
        const idField = document.getElementById('editUserId');
        const nameField = document.getElementById('userName');
        const emailField = document.getElementById('userEmail');
        const planField = document.getElementById('userPlan');

        if (userId) {
            const user = users.find(u => u.id === userId);
            if (user) {
                title.textContent = 'Edit User';
                idField.value = user.id;
                nameField.value = user.name || '';
                emailField.value = user.email || '';
                planField.value = user.plan || ADMIN_CONFIG.DEFAULT_PLAN;
            }
        } else {
            title.textContent = 'Add User';
            idField.value = '';
            nameField.value = '';
            emailField.value = '';
            planField.value = ADMIN_CONFIG.DEFAULT_PLAN;
        }

        document.getElementById('userModal').classList.add('active');
        document.body.style.overflow = 'hidden';
    } catch (e) {
        console.error('Error opening user modal:', e);
        showToast('Error opening modal', 'error');
    }
}

function closeUserModal() {
    document.getElementById('userModal').classList.remove('active');
    document.body.style.overflow = '';
}

function editUser(id) { openUserModal(id); }

function deleteUser(id) {
    const user = users.find(u => u.id === id);
    if (!user) {
        showToast('User not found', 'error');
        return;
    }
    
    if (ADMIN_CONFIG.ALLOWED_ROLES.includes(user.role)) {
        showToast('Cannot delete admin user', 'error');
        return;
    }

    pendingDelete = { type: 'user', id: id };
    document.getElementById('deleteMessage').textContent = 
        `Are you sure you want to delete user "${user.name || user.email}"? This will also delete all their machines and data.`;
    document.getElementById('deleteModal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function openMachineModal(machineId = null) {
    try {
        const ownerSelect = document.getElementById('machineOwner');
        const regularUsers = users.filter(u => !ADMIN_CONFIG.ALLOWED_ROLES.includes(u.role));
        
        ownerSelect.innerHTML = '<option value="">Select owner</option>' + 
            regularUsers.map(u => `<option value="${u.id}">${escapeHtml(u.name || u.email)}</option>`).join('');

        const title = document.getElementById('machineModalTitle');
        const idField = document.getElementById('editMachineId');
        const nameField = document.getElementById('machineName');
        const locationField = document.getElementById('machineLocation');

        if (machineId) {
            const machine = machines.find(m => m.id === machineId);
            if (machine) {
                title.textContent = 'Edit Machine';
                idField.value = machine.id;
                nameField.value = machine.name || '';
                ownerSelect.value = machine.userId || '';
                locationField.value = machine.location || '';
            }
        } else {
            title.textContent = 'Add Machine';
            idField.value = '';
            nameField.value = '';
            ownerSelect.value = '';
            locationField.value = '';
        }

        document.getElementById('machineModal').classList.add('active');
        document.body.style.overflow = 'hidden';
    } catch (e) {
        console.error('Error opening machine modal:', e);
        showToast('Error opening modal', 'error');
    }
}

function closeMachineModal() {
    document.getElementById('machineModal').classList.remove('active');
    document.body.style.overflow = '';
}

function editMachine(id) { openMachineModal(id); }

function deleteMachine(id) {
    const machine = machines.find(m => m.id === id);
    if (!machine) {
        showToast('Machine not found', 'error');
        return;
    }

    pendingDelete = { type: 'machine', id: id };
    document.getElementById('deleteMessage').textContent = 
        `Are you sure you want to delete machine "${machine.name}"? This will also delete all predictions and alerts for this machine.`;
    document.getElementById('deleteModal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function confirmDelete() {
    try {
        if (pendingDelete.type === 'user') {
            // Delete user and associated data
            const userMachines = machines.filter(m => m.userId === pendingDelete.id);
            const machineIds = userMachines.map(m => m.id);
            
            machines = machines.filter(m => m.userId !== pendingDelete.id);
            alerts = alerts.filter(a => !machineIds.includes(a.machineId));
            predictions = predictions.filter(p => !machineIds.includes(p.machineId));
            users = users.filter(u => u.id !== pendingDelete.id);

            saveUsers(users);
            saveMachines(machines);
            saveAlerts(alerts);
            savePredictions(predictions);

            // API call
            deleteUserAPI(pendingDelete.id).catch(() => {});

            logActivity('user_deleted', `Deleted user: ${pendingDelete.id}`, currentAdmin?.email || 'Admin');
            showToast('User deleted successfully', 'success');

        } else if (pendingDelete.type === 'machine') {
            const machineId = pendingDelete.id;
            machines = machines.filter(m => m.id !== machineId);
            alerts = alerts.filter(a => a.machineId !== machineId);
            predictions = predictions.filter(p => p.machineId !== machineId);

            saveMachines(machines);
            saveAlerts(alerts);
            savePredictions(predictions);

            // API call
            deleteMachineAPI(machineId).catch(() => {});

            logActivity('machine_deleted', `Deleted machine: ${machineId}`, currentAdmin?.email || 'Admin');
            showToast('Machine deleted successfully', 'success');
        }

        closeDeleteModal();
        loadAllData();
    } catch (e) {
        console.error('Error confirming delete:', e);
        showToast('Error deleting item', 'error');
    }
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.remove('active');
    document.body.style.overflow = '';
    pendingDelete = null;
}

// ============================================================
// 13. FORM SUBMISSIONS
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    // User form
    const userForm = document.getElementById('userForm');
    if (userForm) {
        userForm.addEventListener('submit', (e) => {
            e.preventDefault();
            try {
                const id = document.getElementById('editUserId').value;
                const name = document.getElementById('userName').value.trim();
                const email = document.getElementById('userEmail').value.trim();
                const plan = document.getElementById('userPlan').value;

                if (!name || !email) {
                    showToast('Name and email are required', 'error');
                    return;
                }

                if (id) {
                    // Update existing user
                    const index = users.findIndex(u => u.id === id);
                    if (index !== -1) {
                        users[index] = { 
                            ...users[index], 
                            name, 
                            email, 
                            plan,
                            updatedAt: new Date().toISOString()
                        };
                        logActivity('user_updated', `Updated user: ${email}`, currentAdmin?.email || 'Admin');
                        showToast('User updated successfully', 'success');
                    }
                } else {
                    // Create new user
                    if (users.some(u => u.email === email)) {
                        showToast('Email already exists', 'error');
                        return;
                    }
                    const newUser = {
                        id: 'user_' + Date.now() + '_' + Math.random().toString(36).substring(2, 6),
                        name,
                        email,
                        plan: plan || ADMIN_CONFIG.DEFAULT_PLAN,
                        role: 'user',
                        createdAt: new Date().toISOString(),
                        verified: true,
                        mfa_enabled: false
                    };
                    users.push(newUser);
                    logActivity('user_created', `Created user: ${email}`, currentAdmin?.email || 'Admin');
                    showToast('User created successfully', 'success');
                }

                saveUsers(users);
                closeUserModal();
                loadAllData();

                // Also try to save to backend
                fetchAdminUsers().catch(() => {});

            } catch (e) {
                console.error('Error saving user:', e);
                showToast('Error saving user', 'error');
            }
        });
    }

    // Machine form
    const machineForm = document.getElementById('machineForm');
    if (machineForm) {
        machineForm.addEventListener('submit', (e) => {
            e.preventDefault();
            try {
                const id = document.getElementById('editMachineId').value;
                const name = document.getElementById('machineName').value.trim();
                const userId = document.getElementById('machineOwner').value;
                const location = document.getElementById('machineLocation').value.trim();

                if (!name || !userId) {
                    showToast('Machine name and owner are required', 'error');
                    return;
                }

                if (id) {
                    // Update existing machine
                    const index = machines.findIndex(m => m.id === id);
                    if (index !== -1) {
                        machines[index] = { 
                            ...machines[index], 
                            name, 
                            userId, 
                            location,
                            updatedAt: new Date().toISOString()
                        };
                        logActivity('machine_updated', `Updated machine: ${name}`, currentAdmin?.email || 'Admin');
                        showToast('Machine updated successfully', 'success');
                    }
                } else {
                    // Create new machine
                    const newMachine = {
                        id: 'mac_' + Date.now() + '_' + Math.random().toString(36).substring(2, 6),
                        name,
                        userId,
                        location: location || '',
                        status: 'good',
                        health: 85,
                        temperature: 65,
                        vibration: 2.5,
                        pressure: 85,
                        createdAt: new Date().toISOString(),
                        lastSeen: new Date().toISOString()
                    };
                    machines.push(newMachine);
                    logActivity('machine_created', `Created machine: ${name}`, currentAdmin?.email || 'Admin');
                    showToast('Machine created successfully', 'success');
                }

                saveMachines(machines);
                closeMachineModal();
                loadAllData();

            } catch (e) {
                console.error('Error saving machine:', e);
                showToast('Error saving machine', 'error');
            }
        });
    }

    // Confirm delete
    const confirmBtn = document.getElementById('confirmDeleteBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', confirmDelete);
    }

    // System status toggle
    const statusToggle = document.getElementById('systemStatusToggle');
    if (statusToggle) {
        statusToggle.addEventListener('click', toggleSystemStatus);
    }

    // Refresh button
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshDashboard);
    }

    // Logout buttons
    document.querySelectorAll('[data-logout]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            adminLogout();
        });
    });

    // Modal close on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', function() {
            const modal = this.closest('.modal');
            if (modal) {
                modal.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });
});

// ============================================================
// 14. SETTINGS FUNCTIONS
// ============================================================

function saveSettings() {
    try {
        const settings = {
            systemName: document.getElementById('systemName')?.value || 'SynapsePM',
            contactEmail: document.getElementById('contactEmail')?.value || 'admin@synapsepm.com',
            maintenanceMode: document.getElementById('maintenanceMode')?.checked || false,
            updatedAt: new Date().toISOString()
        };
        localStorage.setItem('synapse_settings', JSON.stringify(settings));
        logActivity('settings_updated', 'Updated general settings', currentAdmin?.email || 'Admin');
        showToast('Settings saved successfully', 'success');

        // Update system name in header
        const titleEl = document.querySelector('.system-title');
        if (titleEl) titleEl.textContent = settings.systemName;

    } catch (e) {
        console.error('Error saving settings:', e);
        showToast('Error saving settings', 'error');
    }
}

function saveThresholds() {
    try {
        const thresholds = {
            tempWarning: parseFloat(document.getElementById('tempWarning')?.value) || 75,
            tempCritical: parseFloat(document.getElementById('tempCritical')?.value) || 85,
            vibWarning: parseFloat(document.getElementById('vibWarning')?.value) || 3.5,
            vibCritical: parseFloat(document.getElementById('vibCritical')?.value) || 5.0,
            pressureWarning: parseFloat(document.getElementById('pressureWarning')?.value) || 80,
            pressureCritical: parseFloat(document.getElementById('pressureCritical')?.value) || 70,
            updatedAt: new Date().toISOString()
        };
        localStorage.setItem('synapse_thresholds', JSON.stringify(thresholds));
        logActivity('thresholds_updated', 'Updated alert thresholds', currentAdmin?.email || 'Admin');
        showToast('Thresholds saved successfully', 'success');
    } catch (e) {
        console.error('Error saving thresholds:', e);
        showToast('Error saving thresholds', 'error');
    }
}

function loadSettings() {
    try {
        const settings = JSON.parse(localStorage.getItem('synapse_settings'));
        if (settings) {
            const nameField = document.getElementById('systemName');
            const emailField = document.getElementById('contactEmail');
            const maintenanceField = document.getElementById('maintenanceMode');
            if (nameField) nameField.value = settings.systemName || 'SynapsePM';
            if (emailField) emailField.value = settings.contactEmail || 'admin@synapsepm.com';
            if (maintenanceField) maintenanceField.checked = settings.maintenanceMode || false;
        }

        const thresholds = JSON.parse(localStorage.getItem('synapse_thresholds'));
        if (thresholds) {
            const fields = ['tempWarning', 'tempCritical', 'vibWarning', 'vibCritical', 'pressureWarning', 'pressureCritical'];
            fields.forEach(id => {
                const el = document.getElementById(id);
                if (el && thresholds[id] !== undefined) el.value = thresholds[id];
            });
        }
    } catch (e) {
        console.error('Error loading settings:', e);
    }
}

// ============================================================
// 15. UTILITIES
// ============================================================

function showToast(message, type = 'success') {
    try {
        const existing = document.querySelector('.toast-container');
        let container = existing;
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            container.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 8px;
                max-width: 400px;
                width: 100%;
            `;
            document.body.appendChild(container);
        }

        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };

        const colors = {
            success: '#10b981',
            error: '#ef4444',
            warning: '#f59e0b',
            info: '#3b82f6'
        };

        const toast = document.createElement('div');
        toast.style.cssText = `
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 16px;
            border-radius: 12px;
            background: white;
            color: #0f2b3d;
            font-family: 'Inter', sans-serif;
            font-size: 14px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            animation: slideUp 0.3s ease;
            border-left: 4px solid ${colors[type] || colors.info};
        `;

        toast.innerHTML = `
            <span style="font-size: 18px;">${icons[type] || 'ℹ️'}</span>
            <span style="flex: 1;">${escapeHtml(message)}</span>
            <button onclick="this.parentElement.remove()" style="
                background: none;
                border: none;
                font-size: 18px;
                cursor: pointer;
                color: #94a3b8;
            ">✕</button>
        `;

        container.appendChild(toast);
        setTimeout(() => {
            if (toast.parentNode) toast.remove();
        }, 4000);
    } catch (e) {
        console.error('Error showing toast:', e);
        alert(message);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTimeAgo(timestamp) {
    if (!timestamp) return 'Just now';
    try {
        const diff = Math.floor((new Date() - new Date(timestamp)) / 1000);
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
        return new Date(timestamp).toLocaleDateString();
    } catch (e) {
        return 'Invalid date';
    }
}

function formatDate(date) {
    if (!date) return 'N/A';
    try {
        const d = new Date(date);
        return d.toLocaleDateString('en-US', { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
        });
    } catch {
        return 'Invalid date';
    }
}

function showSection(section) {
    try {
        const sections = {
            dashboard: 'dashboardSection',
            users: 'usersSection',
            machines: 'machinesSection',
            alerts: 'alertsSection',
            activities: 'activitiesSection',
            settings: 'settingsSection'
        };

        // Hide all sections
        Object.values(sections).forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });

        // Show target section
        const targetId = sections[section];
        if (targetId) {
            const target = document.getElementById(targetId);
            if (target) target.style.display = 'block';
        }

        currentSection = section;

        // Update page title
        const titleEl = document.getElementById('pageTitle');
        if (titleEl) {
            const titles = {
                dashboard: 'Dashboard',
                users: 'Users',
                machines: 'Machines',
                alerts: 'Alerts',
                activities: 'Activities',
                settings: 'Settings'
            };
            titleEl.textContent = titles[section] || section.charAt(0).toUpperCase() + section.slice(1);
        }

        // Update sidebar links
        document.querySelectorAll('.sidebar-link').forEach(link => {
            link.classList.remove('active');
            link.classList.add('text-slate-600');
        });

        const activeLink = document.querySelector(`.sidebar-link[onclick*="${section}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
            activeLink.classList.remove('text-slate-600');
        }

        // If section is settings, load settings
        if (section === 'settings') {
            loadSettings();
        }

        // If section is activities, refresh
        if (section === 'activities') {
            renderActivitiesTable();
        }

    } catch (e) {
        console.error('Error showing section:', e);
    }
}

function refreshDashboard() {
    try {
        loadAllData();
        showToast('Dashboard refreshed', 'success');
        logActivity('dashboard_refresh', 'Manual dashboard refresh', currentAdmin?.email || 'Admin');
    } catch (e) {
        console.error('Error refreshing dashboard:', e);
        showToast('Error refreshing data', 'error');
    }
}

function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }

    if (!isSystemOnline) return;

    autoRefreshInterval = setInterval(() => {
        if (currentAdmin && isSystemOnline) {
            // Silently refresh data
            fetchAdminData().catch(() => {});
            updateCharts();
        }
    }, ADMIN_CONFIG.AUTO_REFRESH_INTERVAL);
}

function exportData(type) {
    try {
        let data = [];
        let filename = '';
        let headers = [];

        switch(type) {
            case 'users':
                data = users.filter(u => !ADMIN_CONFIG.ALLOWED_ROLES.includes(u.role));
                headers = ['Name', 'Email', 'Plan', 'Machines', 'Joined'];
                filename = 'users_export.csv';
                break;
            case 'machines':
                data = machines;
                headers = ['Name', 'Owner', 'Status', 'Health', 'Location'];
                filename = 'machines_export.csv';
                break;
            case 'alerts':
                data = alerts;
                headers = ['Title', 'User', 'Machine', 'Severity', 'Status', 'Timestamp'];
                filename = 'alerts_export.csv';
                break;
            default:
                showToast('Invalid export type', 'error');
                return;
        }

        // Create CSV
        let csv = headers.join(',') + '\n';
        data.forEach(item => {
            const row = headers.map(h => {
                switch(h) {
                    case 'Name': return item.name || '';
                    case 'Email': return item.email || '';
                    case 'Plan': return item.plan || 'free';
                    case 'Machines': return machines.filter(m => m.userId === item.id).length;
                    case 'Joined': return item.createdAt ? formatDate(item.createdAt) : '';
                    case 'Owner': {
                        const owner = users.find(u => u.id === item.userId);
                        return owner ? owner.name || owner.email : 'Unknown';
                    }
                    case 'Status': return item.status || 'good';
                    case 'Health': return item.health || 85;
                    case 'Location': return item.location || '';
                    case 'Title': return item.title || '';
                    case 'User': {
                        const owner = users.find(u => u.id === item.userId);
                        return owner ? owner.name || owner.email : 'Unknown';
                    }
                    case 'Machine': {
                        const machine = machines.find(m => m.id === item.machineId);
                        return machine ? machine.name : 'Unknown';
                    }
                    case 'Severity': return item.severity || 'info';
                    case 'Timestamp': return item.timestamp ? formatDate(item.timestamp) : '';
                    default: return '';
                }
            });
            csv += row.join(',') + '\n';
        });

        // Download
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);

        logActivity('export_data', `Exported ${type} data`, currentAdmin?.email || 'Admin');
        showToast(`${type.charAt(0).toUpperCase() + type.slice(1)} exported successfully`, 'success');

    } catch (e) {
        console.error('Error exporting data:', e);
        showToast('Error exporting data', 'error');
    }
}

// ============================================================
// 16. EVENT LISTENERS & INIT
// ============================================================

function initEventListeners() {
    try {
        // Refresh button
        document.getElementById('refreshBtn')?.addEventListener('click', refreshDashboard);

        // Logout buttons
        document.getElementById('logoutBtn')?.addEventListener('click', adminLogout);
        document.getElementById('mobileLogoutBtn')?.addEventListener('click', adminLogout);

        // Mobile sidebar toggle
        const mobileToggle = document.getElementById('mobileMenuToggle');
        const mobileSidebar = document.getElementById('mobileSidebar');
        const mobileOverlay = document.getElementById('mobileSidebarOverlay');
        const closeSidebar = document.getElementById('closeMobileSidebar');

        if (mobileToggle && mobileSidebar) {
            mobileToggle.addEventListener('click', () => {
                mobileSidebar.classList.remove('-translate-x-full');
                if (mobileOverlay) mobileOverlay.style.display = 'block';
                document.body.style.overflow = 'hidden';
            });
        }

        window.closeMobileSidebar = function() {
            if (mobileSidebar) mobileSidebar.classList.add('-translate-x-full');
            if (mobileOverlay) mobileOverlay.style.display = 'none';
            document.body.style.overflow = '';
        };

        if (closeSidebar) {
            closeSidebar.addEventListener('click', window.closeMobileSidebar);
        }
        if (mobileOverlay) {
            mobileOverlay.addEventListener('click', window.closeMobileSidebar);
        }

        // Window resize handler
        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                if (window.innerWidth >= 768) {
                    window.closeMobileSidebar();
                }
            }, 200);
        });

    } catch (e) {
        console.error('Error initializing event listeners:', e);
    }
}

// ============================================================
// 17. EXPOSE FUNCTIONS TO GLOBAL SCOPE
// ============================================================
window.showSection = showSection;
window.openUserModal = openUserModal;
window.closeUserModal = closeUserModal;
window.editUser = editUser;
window.deleteUser = deleteUser;
window.openMachineModal = openMachineModal;
window.closeMachineModal = closeMachineModal;
window.editMachine = editMachine;
window.deleteMachine = deleteMachine;
window.closeDeleteModal = closeDeleteModal;
window.saveSettings = saveSettings;
window.saveThresholds = saveThresholds;
window.refreshDashboard = refreshDashboard;
window.toggleSystemStatus = toggleSystemStatus;
window.adminLogout = adminLogout;
window.exportData = exportData;
window.closeMobileSidebar = window.closeMobileSidebar || function(){};
window.confirmDelete = confirmDelete;

// ============================================================
// 18. INITIALIZATION
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    try {
        // Initialize charts
        initCharts();

        // Initialize event listeners
        initEventListeners();

        // Check admin authentication
        const authenticated = checkAdminAuth();

        if (!authenticated) {
            showToast('Please log in to access the admin dashboard', 'warning');
        } else {
            updateAdminInfo();
            showToast('Welcome to SynapsePM Admin Dashboard 👋', 'success');
        }

        // Set initial section
        showSection('dashboard');

    } catch (e) {
        console.error('Error initializing admin dashboard:', e);
        showToast('Error initializing dashboard', 'error');
    }
});

// Handle page visibility change - refresh when tab becomes visible
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && currentAdmin && isSystemOnline) {
        refreshDashboard();
    }
});

console.log('✅ SynapsePM Admin module initialized');
console.log(`👤 Admin: ${currentAdmin?.email || 'Not logged in'}`);
console.log(`🔑 Role: ${currentAdmin?.role || 'None'}`);
console.log(`🔄 Auto-refresh: ${ADMIN_CONFIG.AUTO_REFRESH_INTERVAL / 1000}s`);
console.log(`📊 Users: ${users.length}, Machines: ${machines.length}, Alerts: ${alerts.length}`);