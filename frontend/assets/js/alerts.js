// ============================================
// SYNAPSEPM ALERTS PAGE
// Alerts Management Functionality
// ============================================

const Alerts = (() => {
    'use strict';
    
    // State
    let alerts = [];
    let filteredAlerts = [];
    let settings = {};
    
    // ============================================
    // INITIALIZATION
    // ============================================
    
    const init = () => {
        if (!AuthService.isAuthenticated()) return;
        
        loadAlerts();
        loadSettings();
        initEventListeners();
    };
    
    const initEventListeners = () => {
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadAlerts);
        }
        
        // Filter listeners
        ['severityFilter', 'statusFilter', 'machineFilter'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', applyFilters);
            }
        });
        
        // Search input
        const searchInput = document.getElementById('searchFilter');
        if (searchInput) {
            searchInput.addEventListener('input', Utils.ui.debounce(applyFilters, 300));
        }
        
        // Settings form
        const settingsForm = document.getElementById('alertSettingsForm');
        if (settingsForm) {
            settingsForm.addEventListener('submit', saveSettings);
        }
    };
    
    // ============================================
    // DATA LOADING
    // ============================================
    
    const loadAlerts = async () => {
        try {
            const response = await ApiService.get('/alerts');
            if (response.success) {
                alerts = response.data || [];
                filteredAlerts = [...alerts];
                renderAlerts();
                updateStats();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to load alerts', 'error');
        }
    };
    
    const loadSettings = async () => {
        try {
            const response = await ApiService.get('/alerts/settings');
            if (response.success) {
                settings = response.data || {};
                renderSettings();
            }
        } catch (error) {
            console.error('Failed to load alert settings:', error);
        }
    };
    
    const updateStats = () => {
        const critical = alerts.filter(a => a.severity === 'critical' && a.status !== 'resolved').length;
        const warning = alerts.filter(a => a.severity === 'warning' && a.status !== 'resolved').length;
        const info = alerts.filter(a => a.severity === 'info' && a.status !== 'resolved').length;
        const resolved = alerts.filter(a => a.status === 'resolved').length;
        
        document.getElementById('criticalCount')?.textContent = critical;
        document.getElementById('warningCount')?.textContent = warning;
        document.getElementById('infoCount')?.textContent = info;
        document.getElementById('resolvedCount')?.textContent = resolved;
    };
    
    // ============================================
    // RENDERING
    // ============================================
    
    const renderAlerts = () => {
        const container = document.getElementById('alertsContainer');
        if (!container) return;
        
        if (filteredAlerts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-bell-slash"></i>
                    <h3>No Alerts Found</h3>
                    <p>No alerts match your current filters.</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = filteredAlerts.map(alert => {
            const date = new Date(alert.timestamp);
            
            return `
                <div class="alert-item ${alert.severity}" data-id="${alert.id}">
                    <div class="alert-header">
                        <div class="alert-title">
                            <div class="alert-icon ${alert.severity}">
                                <i class="fas fa-${getAlertIcon(alert.severity)}"></i>
                            </div>
                            <div>
                                <h4>${alert.title}</h4>
                                <div class="alert-meta">
                                    <span><i class="fas fa-microchip"></i> ${alert.machineName}</span>
                                    <span><i class="fas fa-clock"></i> ${Utils.date.timeAgo(date)}</span>
                                </div>
                            </div>
                        </div>
                        <span class="badge badge-${alert.severity}">${alert.severity.toUpperCase()}</span>
                    </div>
                    
                    <p class="alert-message">${alert.message}</p>
                    
                    <div class="alert-details">
                        <div class="detail-item">
                            <span class="detail-label">Current Value</span>
                            <span class="detail-value">${alert.value || 'N/A'} ${alert.unit || ''}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Threshold</span>
                            <span class="detail-value">${alert.threshold || 'N/A'} ${alert.unit || ''}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Deviation</span>
                            <span class="detail-value">${alert.deviation || 0}%</span>
                        </div>
                    </div>
                    
                    <div class="alert-actions">
                        ${alert.status !== 'resolved' ? `
                            <button class="alert-btn acknowledge" onclick="Alerts.acknowledge('${alert.id}')">
                                <i class="fas fa-check"></i> Acknowledge
                            </button>
                            <button class="alert-btn resolve" onclick="Alerts.resolve('${alert.id}')">
                                <i class="fas fa-check-double"></i> Resolve
                            </button>
                        ` : `
                            <span class="resolved-badge">
                                <i class="fas fa-check-circle"></i> Resolved
                            </span>
                        `}
                    </div>
                </div>
            `;
        }).join('');
    };
    
    const getAlertIcon = (severity) => {
        const icons = {
            critical: 'exclamation-triangle',
            warning: 'exclamation-circle',
            info: 'info-circle',
            default: 'bell'
        };
        return icons[severity] || icons.default;
    };
    
    const renderSettings = () => {
        // Render thresholds
        if (settings.thresholds) {
            Object.entries(settings.thresholds).forEach(([key, value]) => {
                const input = document.getElementById(`${key}Threshold`);
                if (input) input.value = value;
            });
        }
        
        // Render notification channels
        if (settings.channels) {
            settings.channels.forEach(channel => {
                const checkbox = document.getElementById(`${channel}Channel`);
                if (checkbox) checkbox.checked = true;
            });
        }
        
        // Render quiet hours
        if (settings.quietHours) {
            document.getElementById('quietHoursToggle').checked = settings.quietHours.enabled;
            document.getElementById('quietStart').value = settings.quietHours.start || '22:00';
            document.getElementById('quietEnd').value = settings.quietHours.end || '07:00';
        }
    };
    
    // ============================================
    // FILTERING
    // ============================================
    
    const applyFilters = () => {
        const severity = document.getElementById('severityFilter')?.value || '';
        const status = document.getElementById('statusFilter')?.value || '';
        const machine = document.getElementById('machineFilter')?.value || '';
        const search = document.getElementById('searchFilter')?.value.toLowerCase() || '';
        
        filteredAlerts = alerts.filter(alert => {
            const matchesSeverity = severity === '' || alert.severity === severity;
            const matchesStatus = status === '' || alert.status === status;
            const matchesMachine = machine === '' || alert.machineId === machine;
            const matchesSearch = search === '' || 
                alert.title.toLowerCase().includes(search) ||
                alert.message.toLowerCase().includes(search);
            
            return matchesSeverity && matchesStatus && matchesMachine && matchesSearch;
        });
        
        renderAlerts();
    };
    
    // ============================================
    // ALERT ACTIONS
    // ============================================
    
    const acknowledge = async (id) => {
        try {
            const response = await ApiService.post(`/alerts/${id}/acknowledge`);
            if (response.success) {
                Utils.ui.showToast('Alert acknowledged', 'success');
                loadAlerts();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to acknowledge alert', 'error');
        }
    };
    
    const resolve = async (id) => {
        try {
            const response = await ApiService.post(`/alerts/${id}/resolve`);
            if (response.success) {
                Utils.ui.showToast('Alert resolved', 'success');
                loadAlerts();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to resolve alert', 'error');
        }
    };
    
    // ============================================
    // SETTINGS
    // ============================================
    
    const saveSettings = async (e) => {
        e.preventDefault();
        
        const settings = {
            thresholds: {
                temperature: document.getElementById('tempThreshold')?.value,
                vibration: document.getElementById('vibrationThreshold')?.value,
                pressure: document.getElementById('pressureThreshold')?.value,
                rul: document.getElementById('rulThreshold')?.value,
            },
            channels: {
                email: document.getElementById('emailChannel')?.checked,
                sms: document.getElementById('smsChannel')?.checked,
                slack: document.getElementById('slackChannel')?.checked,
                webhook: document.getElementById('webhookChannel')?.checked,
            },
            quietHours: {
                enabled: document.getElementById('quietHoursToggle')?.checked,
                start: document.getElementById('quietStart')?.value,
                end: document.getElementById('quietEnd')?.value,
            },
        };
        
        try {
            const response = await ApiService.put('/alerts/settings', settings);
            if (response.success) {
                Utils.ui.showToast('Alert settings saved', 'success');
            }
        } catch (error) {
            Utils.ui.showToast('Failed to save settings', 'error');
        }
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        init,
        acknowledge,
        resolve,
        saveSettings,
    };
})();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('alerts-page')) {
        Alerts.init();
    }
});

window.Alerts = Alerts;