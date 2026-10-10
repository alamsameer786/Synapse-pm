// ============================================
// SYNAPSEPM MACHINES PAGE
// Machines Management Functionality
// ============================================

const Machines = (() => {
    'use strict';
    
    // State
    let machines = [];
    let filteredMachines = [];
    let refreshInterval;
    
    // ============================================
    // INITIALIZATION
    // ============================================
    
    const init = () => {
        if (!AuthService.isAuthenticated()) return;
        
        loadMachines();
        initEventListeners();
        startAutoRefresh();
    };
    
    const startAutoRefresh = () => {
        if (refreshInterval) clearInterval(refreshInterval);
        refreshInterval = setInterval(loadMachines, CONFIG.FEATURES.AUTO_REFRESH_INTERVAL);
    };
    
    const initEventListeners = () => {
        const searchInput = document.getElementById('searchInput');
        const statusFilter = document.getElementById('statusFilter');
        const typeFilter = document.getElementById('typeFilter');
        const refreshBtn = document.getElementById('refreshBtn');
        
        if (searchInput) {
            searchInput.addEventListener('input', Utils.ui.debounce(applyFilters, 300));
        }
        
        if (statusFilter) {
            statusFilter.addEventListener('change', applyFilters);
        }
        
        if (typeFilter) {
            typeFilter.addEventListener('change', applyFilters);
        }
        
        if (refreshBtn) {
            refreshBtn.addEventListener('click', loadMachines);
        }
        
        // Add machine form
        const form = document.getElementById('addMachineForm');
        if (form) {
            form.addEventListener('submit', handleAddMachine);
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
                filteredMachines = [...machines];
                renderMachines();
                updateStats();
            }
            
        } catch (error) {
            Utils.ui.showToast('Failed to load machines', 'error');
            showErrorState();
        }
    };
    
    const updateStats = () => {
        const total = machines.length;
        const online = machines.filter(m => m.status === 'online').length;
        const warning = machines.filter(m => m.status === 'warning').length;
        const critical = machines.filter(m => m.status === 'critical').length;
        
        document.getElementById('totalMachines')?.textContent = total;
        document.getElementById('onlineMachines')?.textContent = online;
        document.getElementById('warningMachines')?.textContent = warning;
        document.getElementById('criticalMachines')?.textContent = critical;
        
        document.getElementById('machinesBadge')?.textContent = total;
        document.getElementById('alertsBadge')?.textContent = critical;
    };
    
    // ============================================
    // RENDERING
    // ============================================
    
    const renderMachines = () => {
        const grid = document.getElementById('machinesGrid');
        if (!grid) return;
        
        if (filteredMachines.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-industry"></i>
                    <h3>No Machines Found</h3>
                    <p>No machines match your current filters.</p>
                    <button class="btn btn-secondary" onclick="Machines.clearFilters()">
                        <i class="fas fa-times"></i> Clear Filters
                    </button>
                </div>
            `;
            return;
        }
        
        grid.innerHTML = filteredMachines.map(machine => `
            <div class="machine-card" onclick="Machines.viewDetails('${machine.id}')">
                <div class="machine-header">
                    <div class="machine-icon">
                        <i class="fas fa-${getMachineIcon(machine.type)}"></i>
                    </div>
                    <div class="machine-info">
                        <div class="machine-name">${machine.name}</div>
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
                        <button class="btn-icon" onclick="Machines.viewDetails('${machine.id}')" title="View Details">
                            <i class="fas fa-chart-line"></i>
                        </button>
                        <button class="btn-icon" onclick="Machines.runPrediction('${machine.id}')" title="Run Prediction">
                            <i class="fas fa-brain"></i>
                        </button>
                        <button class="btn-icon" onclick="Machines.edit('${machine.id}')" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
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
    
    const showErrorState = () => {
        const grid = document.getElementById('machinesGrid');
        if (grid) {
            grid.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <h3>Error Loading Machines</h3>
                    <p>Unable to connect to the server. Please try again.</p>
                    <button class="btn btn-primary" onclick="Machines.loadMachines()">
                        <i class="fas fa-sync-alt"></i> Try Again
                    </button>
                </div>
            `;
        }
    };
    
    // ============================================
    // FILTERING
    // ============================================
    
    const applyFilters = () => {
        const searchTerm = document.getElementById('searchInput')?.value.toLowerCase() || '';
        const status = document.getElementById('statusFilter')?.value || '';
        const type = document.getElementById('typeFilter')?.value || '';
        
        filteredMachines = machines.filter(machine => {
            const matchesSearch = searchTerm === '' || 
                machine.name?.toLowerCase().includes(searchTerm) ||
                machine.location?.toLowerCase().includes(searchTerm) ||
                machine.manufacturer?.toLowerCase().includes(searchTerm);
            
            const matchesStatus = status === '' || machine.status === status;
            const matchesType = type === '' || machine.type === type;
            
            return matchesSearch && matchesStatus && matchesType;
        });
        
        renderMachines();
    };
    
    const clearFilters = () => {
        document.getElementById('searchInput').value = '';
        document.getElementById('statusFilter').value = '';
        document.getElementById('typeFilter').value = '';
        filteredMachines = [...machines];
        renderMachines();
    };
    
    // ============================================
    // MACHINE ACTIONS
    // ============================================
    
    const viewDetails = (id) => {
        window.location.href = `/machine-details.html?id=${id}`;
    };
    
    const runPrediction = (id) => {
        window.location.href = `/predictions.html?machine=${id}`;
    };
    
    const edit = (id) => {
        const machine = machines.find(m => m.id === id);
        if (machine) {
            openEditModal(machine);
        }
    };
    
    const del = async (id) => {
        if (!confirm('Are you sure you want to delete this machine?')) return;
        
        try {
            const response = await ApiService.delete(`/machines/${id}`);
            if (response.success) {
                Utils.ui.showToast('Machine deleted successfully', 'success');
                loadMachines();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to delete machine', 'error');
        }
    };
    
    // ============================================
    // ADD MACHINE
    // ============================================
    
    const handleAddMachine = async (e) => {
        e.preventDefault();
        
        const formData = {
            name: document.getElementById('machineName')?.value,
            type: document.getElementById('machineType')?.value,
            manufacturer: document.getElementById('machineManufacturer')?.value,
            model: document.getElementById('machineModel')?.value,
            location: document.getElementById('machineLocation')?.value,
            serialNumber: document.getElementById('machineSerial')?.value,
        };
        
        if (!formData.name || !formData.type) {
            Utils.ui.showToast('Please fill in required fields', 'error');
            return;
        }
        
        try {
            const response = await ApiService.post('/machines', formData);
            if (response.success) {
                Utils.ui.showToast('Machine added successfully', 'success');
                closeAddModal();
                loadMachines();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to add machine', 'error');
        }
    };
    
    const openAddModal = () => {
        const modal = document.getElementById('addMachineModal');
        if (modal) {
            modal.classList.add('show');
            document.body.style.overflow = 'hidden';
        }
    };
    
    const closeAddModal = () => {
        const modal = document.getElementById('addMachineModal');
        if (modal) {
            modal.classList.remove('show');
            document.body.style.overflow = '';
            document.getElementById('addMachineForm')?.reset();
        }
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
        loadMachines,
        applyFilters,
        clearFilters,
        viewDetails,
        runPrediction,
        edit,
        delete: del,
        openAddModal,
        closeAddModal,
        cleanup,
    };
})();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('machines-page')) {
        Machines.init();
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    Machines.cleanup();
});

window.Machines = Machines;