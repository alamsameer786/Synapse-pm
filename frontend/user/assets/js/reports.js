// ============================================
// SYNAPSEPM REPORTS PAGE
// Reports Management Functionality
// ============================================

const Reports = (() => {
    'use strict';
    
    // State
    let reports = [];
    let schedules = [];
    let machines = [];
    
    // Report templates
    const templates = {
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
    
    // ============================================
    // INITIALIZATION
    // ============================================
    
    const init = () => {
        if (!AuthService.isAuthenticated()) return;
        
        loadMachines();
        loadReports();
        loadSchedules();
        initEventListeners();
    };
    
    const initEventListeners = () => {
        const form = document.getElementById('reportForm');
        if (form) {
            form.addEventListener('submit', handleGenerateReport);
        }
        
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadReports);
        }
    };
    
    // ============================================
    // DATA LOADING
    // ============================================
    
    const loadMachines = async () => {
        try {
            const response = await ApiService.get('/machines');
            if (response.success) {
                machines = response.data || [];
                renderMachineSelect();
            }
        } catch (error) {
            console.error('Failed to load machines:', error);
        }
    };
    
    const loadReports = async () => {
        try {
            const response = await ApiService.get('/reports');
            if (response.success) {
                reports = response.data || [];
                renderReports();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to load reports', 'error');
        }
    };
    
    const loadSchedules = async () => {
        try {
            const response = await ApiService.get('/reports/schedules');
            if (response.success) {
                schedules = response.data || [];
                renderSchedules();
            }
        } catch (error) {
            console.error('Failed to load schedules:', error);
        }
    };
    
    // ============================================
    // RENDERING
    // ============================================
    
    const renderMachineSelect = () => {
        const select = document.getElementById('machines');
        if (!select) return;
        
        select.innerHTML = '<option value="all">All Machines</option>' + 
            machines.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
    };
    
    const renderReports = () => {
        const grid = document.getElementById('reportsGrid');
        if (!grid) return;
        
        if (reports.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-file-alt"></i>
                    <h3>No Reports Yet</h3>
                    <p>Generate your first report using the form above.</p>
                </div>
            `;
            return;
        }
        
        grid.innerHTML = reports.map(report => {
            const date = new Date(report.createdAt);
            
            return `
                <div class="report-card">
                    <div class="report-header">
                        <div class="report-icon">
                            <i class="fas fa-${getReportIcon(report.type)}"></i>
                        </div>
                        <div class="report-info">
                            <div class="report-title">${report.name}</div>
                            <div class="report-meta">
                                <span><i class="fas fa-calendar"></i> ${Utils.date.formatDate(date)}</span>
                                <span><i class="fas fa-file-${report.format}"></i> ${report.format.toUpperCase()}</span>
                            </div>
                        </div>
                        <span class="report-status status-${report.status}">${report.status}</span>
                    </div>
                    <div class="report-body">
                        <div class="report-preview">${report.preview}</div>
                        <div class="report-stats">
                            <div class="report-stat">
                                <div class="label">Machines</div>
                                <div class="value">${report.machineCount}</div>
                            </div>
                            <div class="report-stat">
                                <div class="label">Size</div>
                                <div class="value">${report.size}</div>
                            </div>
                            <div class="report-stat">
                                <div class="label">Pages</div>
                                <div class="value">${report.pages}</div>
                            </div>
                            <div class="report-stat">
                                <div class="label">Range</div>
                                <div class="value">${report.dateRange} days</div>
                            </div>
                        </div>
                    </div>
                    <div class="report-footer">
                        <button class="btn btn-primary btn-sm" onclick="Reports.download('${report.id}')">
                            <i class="fas fa-download"></i> Download
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="Reports.view('${report.id}')">
                            <i class="fas fa-eye"></i> View
                        </button>
                        <button class="btn btn-text btn-sm" onclick="Reports.share('${report.id}')">
                            <i class="fas fa-share"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    };
    
    const getReportIcon = (type) => {
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
    };
    
    const renderSchedules = () => {
        const list = document.getElementById('scheduleList');
        if (!list) return;
        
        if (schedules.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-clock"></i>
                    <h3>No Scheduled Reports</h3>
                    <p>Schedule recurring reports to automate your workflow.</p>
                </div>
            `;
            return;
        }
        
        list.innerHTML = schedules.map(schedule => {
            const nextRun = new Date(schedule.nextRun);
            
            return `
                <div class="schedule-item">
                    <div class="schedule-info">
                        <h4>${schedule.name}</h4>
                        <p>
                            <span><i class="fas fa-calendar"></i> ${schedule.frequency} on ${schedule.day}</span>
                            <span><i class="fas fa-clock"></i> ${schedule.time}</span>
                            <span class="schedule-badge">${schedule.format.toUpperCase()}</span>
                            <span><i class="fas fa-envelope"></i> ${schedule.recipients.length} recipient(s)</span>
                        </p>
                    </div>
                    <div class="schedule-actions">
                        <button class="btn-icon" onclick="Reports.editSchedule('${schedule.id}')" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn-icon" onclick="Reports.pauseSchedule('${schedule.id}')" title="Pause">
                            <i class="fas fa-pause"></i>
                        </button>
                        <button class="btn-icon" onclick="Reports.deleteSchedule('${schedule.id}')" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    };
    
    // ============================================
    // REPORT GENERATION
    // ============================================
    
    const handleGenerateReport = async (e) => {
        e.preventDefault();
        
        const type = document.getElementById('reportType')?.value;
        const dateRange = document.getElementById('dateRange')?.value;
        const format = document.getElementById('reportFormat')?.value;
        const machineId = document.getElementById('machines')?.value;
        
        if (!type) {
            Utils.ui.showToast('Please select a report type', 'error');
            return;
        }
        
        const btn = e.target.querySelector('button[type="submit"]');
        const originalText = btn?.innerHTML;
        
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
        }
        
        try {
            const response = await ApiService.post('/reports/generate', {
                type,
                dateRange,
                format,
                machineId,
                includeCharts: document.getElementById('includeCharts')?.checked,
                includeRecommendations: document.getElementById('includeRecommendations')?.checked,
                includeRawData: document.getElementById('includeRawData')?.checked
            });
            
            if (response.success) {
                Utils.ui.showToast('Report generated successfully', 'success');
                loadReports(); // Refresh list
            }
            
        } catch (error) {
            Utils.ui.showToast('Failed to generate report', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    };
    
    // ============================================
    // REPORT ACTIONS
    // ============================================
    
    const download = (id) => {
        window.open(`${CONFIG.API.BASE_URL}/reports/${id}/download`, '_blank');
        Utils.ui.showToast('Downloading report...', 'success');
    };
    
    const view = (id) => {
        window.open(`/report-viewer.html?id=${id}`, '_blank');
    };
    
    const share = (id) => {
        // Open sharing modal
        Utils.ui.showToast('Sharing options coming soon', 'info');
    };
    
    // ============================================
    // SCHEDULE ACTIONS
    // ============================================
    
    const editSchedule = (id) => {
        Utils.ui.showToast('Edit schedule', 'info');
    };
    
    const pauseSchedule = async (id) => {
        try {
            const response = await ApiService.post(`/reports/schedules/${id}/pause`);
            if (response.success) {
                Utils.ui.showToast('Schedule paused', 'success');
                loadSchedules();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to pause schedule', 'error');
        }
    };
    
    const deleteSchedule = async (id) => {
        if (!confirm('Are you sure you want to delete this scheduled report?')) return;
        
        try {
            const response = await ApiService.delete(`/reports/schedules/${id}`);
            if (response.success) {
                Utils.ui.showToast('Schedule deleted', 'success');
                loadSchedules();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to delete schedule', 'error');
        }
    };
    
    // ============================================
    // PREVIEW
    // ============================================
    
    const preview = () => {
        const type = document.getElementById('reportType')?.value;
        if (!type) {
            Utils.ui.showToast('Please select a report type', 'error');
            return;
        }
        
        Utils.ui.showToast(`Preview for ${templates[type]?.name}`, 'info');
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        init,
        download,
        view,
        share,
        editSchedule,
        pauseSchedule,
        deleteSchedule,
        preview,
    };
})();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('reports-page')) {
        Reports.init();
    }
});

window.Reports = Reports;