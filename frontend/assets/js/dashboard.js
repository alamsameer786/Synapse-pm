// ============================================
// SYNAPSEPM DASHBOARD
// Dashboard Specific Functionality
// ============================================

const Dashboard = (() => {
    'use strict';
    
    // State
    let charts = {};
    let refreshInterval;
    
    // ============================================
    // INITIALIZATION
    // ============================================
    
    const init = () => {
        if (!AuthService.isAuthenticated()) return;
        
        loadDashboardData();
        initCharts();
        startAutoRefresh();
    };
    
    const startAutoRefresh = () => {
        if (refreshInterval) clearInterval(refreshInterval);
        refreshInterval = setInterval(loadDashboardData, CONFIG.FEATURES.AUTO_REFRESH_INTERVAL);
    };
    
    // ============================================
    // DATA LOADING
    // ============================================
    
    const loadDashboardData = async () => {
        try {
            // Load stats
            const statsResponse = await ApiService.get('/dashboard/stats');
            if (statsResponse.success) {
                updateStats(statsResponse.data);
            }
            
            // Load machines
            const machinesResponse = await ApiService.get('/machines', { limit: 6 });
            if (machinesResponse.success) {
                renderMachines(machinesResponse.data);
            }
            
            // Load alerts
            const alertsResponse = await ApiService.get('/alerts', { status: 'active', limit: 5 });
            if (alertsResponse.success) {
                updateAlertsBadge(alertsResponse.data);
            }
            
            // Load activity
            const activityResponse = await ApiService.get('/activity', { limit: 5 });
            if (activityResponse.success) {
                renderActivity(activityResponse.data);
            }
            
        } catch (error) {
            Utils.ui.showToast('Failed to load dashboard data', 'error');
        }
    };
    
    const updateStats = (stats) => {
        const elements = {
            totalMachines: document.getElementById('totalMachines'),
            activeAlerts: document.getElementById('activeAlerts'),
            avgConfidence: document.getElementById('avgConfidence'),
            predictionsToday: document.getElementById('predictionsToday'),
            healthScore: document.getElementById('healthScore'),
            uptime: document.getElementById('uptime'),
        };
        
        Object.entries(elements).forEach(([key, el]) => {
            if (el && stats[key] !== undefined) {
                el.textContent = stats[key];
            }
        });
    };
    
    const renderMachines = (machines) => {
        const grid = document.getElementById('machinesGrid');
        if (!grid) return;
        
        if (!machines || machines.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-industry"></i>
                    <h3>No machines yet</h3>
                    <p>Add your first machine to start monitoring</p>
                    <a href="/machines.html?action=add" class="btn btn-primary">Add Machine</a>
                </div>
            `;
            return;
        }
        
        grid.innerHTML = machines.slice(0, 4).map(machine => `
            <div class="machine-card" onclick="Dashboard.viewMachine('${machine.id}')">
                <div class="machine-header">
                    <div class="machine-icon">
                        <i class="fas fa-${getMachineIcon(machine.type)}"></i>
                    </div>
                    <div class="machine-info">
                        <div class="machine-name">${machine.name}</div>
                        <div class="machine-location">${machine.location || 'No location'}</div>
                    </div>
                    <span class="machine-status status-${machine.status}">${machine.status}</span>
                </div>
                <div class="machine-stats">
                    <div class="machine-stat">
                        <div class="label">Health</div>
                        <div class="value">${machine.health || '--'}%</div>
                    </div>
                    <div class="machine-stat">
                        <div class="label">Temp</div>
                        <div class="value">${machine.temperature || '--'}°C</div>
                    </div>
                    <div class="machine-stat">
                        <div class="label">Vibration</div>
                        <div class="value">${machine.vibration || '--'}mm/s</div>
                    </div>
                </div>
            </div>
        `).join('');
    };
    
    const getMachineIcon = (type) => {
        const icons = {
            turbine: 'fan',
            pump: 'water',
            compressor: 'wind',
            motor: 'bolt',
            generator: 'bolt',
            default: 'industry'
        };
        return icons[type] || icons.default;
    };
    
    const updateAlertsBadge = (alerts) => {
        const badge = document.getElementById('alertsBadge');
        if (badge) {
            const criticalCount = alerts.filter(a => a.severity === 'critical').length;
            badge.textContent = criticalCount;
            badge.style.display = criticalCount > 0 ? 'inline-block' : 'none';
        }
    };
    
    const renderActivity = (activities) => {
        const list = document.getElementById('activityList');
        if (!list) return;
        
        if (!activities || activities.length === 0) {
            list.innerHTML = '<p class="text-muted text-center">No recent activity</p>';
            return;
        }
        
        list.innerHTML = activities.map(activity => `
            <div class="activity-item">
                <div class="activity-icon">
                    <i class="fas fa-${getActivityIcon(activity.type)}"></i>
                </div>
                <div class="activity-content">
                    <div class="activity-title">${activity.title}</div>
                    <div class="activity-time">${Utils.date.timeAgo(activity.createdAt)}</div>
                </div>
                <div class="activity-meta">${activity.machine || ''}</div>
            </div>
        `).join('');
    };
    
    const getActivityIcon = (type) => {
        const icons = {
            prediction: 'brain',
            alert: 'bell',
            machine: 'industry',
            default: 'circle'
        };
        return icons[type] || icons.default;
    };
    
    // ============================================
    // CHARTS
    // ============================================
    
    const initCharts = () => {
        initTrendChart();
        initHealthChart();
    };
    
    const initTrendChart = () => {
        const ctx = document.getElementById('trendChart')?.getContext('2d');
        if (!ctx) return;
        
        charts.trend = new Chart(ctx, {
            type: 'line',
            data: {
                labels: getLast30Days(),
                datasets: [{
                    label: 'Predictions',
                    data: generateTrendData(30),
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
    };
    
    const initHealthChart = () => {
        const ctx = document.getElementById('healthChart')?.getContext('2d');
        if (!ctx) return;
        
        charts.health = new Chart(ctx, {
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
    };
    
    const getLast30Days = () => {
        const days = [];
        for (let i = 29; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            days.push(date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
        }
        return days;
    };
    
    const generateTrendData = (days) => {
        return Array.from({ length: days }, () => Math.floor(Math.random() * 30) + 10);
    };
    
    const updateHealthChart = (healthy, warning, critical) => {
        if (charts.health) {
            charts.health.data.datasets[0].data = [healthy, warning, critical];
            charts.health.update();
        }
    };
    
    // ============================================
    // ACTIONS
    // ============================================
    
    const viewMachine = (id) => {
        window.location.href = `/machines.html?id=${id}`;
    };
    
    const runBatchPrediction = async () => {
        if (!confirm('Run predictions for all active machines?')) return;
        
        try {
            await ApiService.post('/predictions/batch');
            Utils.ui.showToast('Batch prediction started', 'success');
        } catch (error) {
            Utils.ui.showToast('Failed to start batch prediction', 'error');
        }
    };
    
    const refresh = () => {
        loadDashboardData();
    };
    
    // ============================================
    // CLEANUP
    // ============================================
    
    const cleanup = () => {
        if (refreshInterval) {
            clearInterval(refreshInterval);
        }
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        init,
        viewMachine,
        runBatchPrediction,
        refresh,
        cleanup,
    };
})();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('dashboard-page')) {
        Dashboard.init();
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    Dashboard.cleanup();
});

window.Dashboard = Dashboard;