// ============================================
// SYNAPSEPM PREDICTIONS PAGE
// Predictions Management Functionality
// ============================================

const Predictions = (() => {
    'use strict';
    
    // State
    let machines = [];
    let selectedMachine = null;
    let selectedModel = 'lstm';
    let predictions = [];
    let charts = {};
    
    // Models configuration
    const models = [
        {
            id: 'lstm',
            name: 'LSTM',
            description: 'Long Short-Term Memory',
            icon: '🧠',
            accuracy: 94,
            speed: '500ms',
        },
        {
            id: 'transformer',
            name: 'Transformer',
            description: 'Attention-based model',
            icon: '⚡',
            accuracy: 93,
            speed: '800ms',
        },
        {
            id: 'xgboost',
            name: 'XGBoost',
            description: 'Gradient boosting',
            icon: '🚀',
            accuracy: 91,
            speed: '50ms',
        },
        {
            id: 'ensemble',
            name: 'Ensemble',
            description: 'Combined models',
            icon: '🔄',
            accuracy: 96,
            speed: '1.2s',
        }
    ];
    
    // ============================================
    // INITIALIZATION
    // ============================================
    
    const init = () => {
        if (!AuthService.isAuthenticated()) return;
        
        loadMachines();
        renderModels();
        initEventListeners();
        loadHistory();
    };
    
    const initEventListeners = () => {
        const runBtn = document.getElementById('runPredictionBtn');
        const form = document.getElementById('predictionForm');
        
        if (form) {
            form.addEventListener('submit', handleRunPrediction);
        }
        
        if (runBtn) {
            runBtn.addEventListener('click', handleRunPrediction);
        }
        
        // Check for machine ID in URL
        const urlParams = Utils.browser.getUrlParams();
        if (urlParams.machine) {
            selectMachine(urlParams.machine);
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
                renderMachineSelector();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to load machines', 'error');
        }
    };
    
    const loadHistory = async () => {
        try {
            const response = await ApiService.get('/predictions/history', { limit: 10 });
            if (response.success) {
                predictions = response.data || [];
                renderHistory();
            }
        } catch (error) {
            Utils.ui.showToast('Failed to load prediction history', 'error');
        }
    };
    
    // ============================================
    // RENDERING
    // ============================================
    
    const renderMachineSelector = () => {
        const selector = document.getElementById('machineSelector');
        if (!selector) return;
        
        if (!machines || machines.length === 0) {
            selector.innerHTML = `
                <div class="empty-state">
                    <p>No machines available. <a href="/machines.html?action=add">Add a machine</a> first.</p>
                </div>
            `;
            return;
        }
        
        selector.innerHTML = machines.map(machine => `
            <div class="machine-select-card ${selectedMachine === machine.id ? 'selected' : ''}" 
                 onclick="Predictions.selectMachine('${machine.id}')">
                <div class="machine-select-icon">
                    <i class="fas fa-${getMachineIcon(machine.type)}"></i>
                </div>
                <div class="machine-select-info">
                    <div class="machine-select-name">${machine.name}</div>
                    <div class="machine-select-status status-${machine.status}">
                        ${machine.status}
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
    
    const renderModels = () => {
        const selector = document.getElementById('modelSelector');
        if (!selector) return;
        
        selector.innerHTML = models.map(model => `
            <div class="model-card ${model.id === selectedModel ? 'selected' : ''}" 
                 onclick="Predictions.selectModel('${model.id}')">
                <div class="model-icon">${model.icon}</div>
                <h3>${model.name}</h3>
                <div class="model-description">${model.description}</div>
                <div class="model-stats">
                    <div class="model-stat">
                        <div class="model-stat-label">Accuracy</div>
                        <div class="model-stat-value">${model.accuracy}%</div>
                    </div>
                    <div class="model-stat">
                        <div class="model-stat-label">Speed</div>
                        <div class="model-stat-value">${model.speed}</div>
                    </div>
                </div>
            </div>
        `).join('');
    };
    
    const renderHistory = () => {
        const table = document.getElementById('historyTable');
        if (!table) return;
        
        if (!predictions || predictions.length === 0) {
            table.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center">No predictions yet. Run your first prediction above.</td>
                </tr>
            `;
            return;
        }
        
        table.innerHTML = predictions.map(pred => {
            const date = new Date(pred.timestamp);
            return `
                <tr>
                    <td>${pred.machineName}</td>
                    <td>${pred.model}</td>
                    <td><strong>${pred.rul.toLocaleString()}</strong> hrs</td>
                    <td>${pred.confidence}%</td>
                    <td>
                        <span class="status-badge health-${pred.status}">${pred.status}</span>
                    </td>
                    <td>${Utils.date.formatDate(date, 'MMM DD, YYYY HH:mm')}</td>
                    <td>
                        <button class="btn-icon" onclick="Predictions.viewPrediction('${pred.id}')">
                            <i class="fas fa-eye"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    };
    
    // ============================================
    // SELECTION
    // ============================================
    
    const selectMachine = (id) => {
        selectedMachine = id;
        renderMachineSelector();
    };
    
    const selectModel = (id) => {
        selectedModel = id;
        renderModels();
    };
    
    // ============================================
    // RUN PREDICTION
    // ============================================
    
    const handleRunPrediction = async (e) => {
        e.preventDefault();
        
        if (!selectedMachine) {
            Utils.ui.showToast('Please select a machine', 'error');
            return;
        }
        
        const btn = e.target.closest('button');
        const originalText = btn?.innerHTML;
        
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';
        }
        
        try {
            const horizon = document.getElementById('predictionHorizon')?.value || 30;
            const threshold = document.getElementById('confidenceThreshold')?.value || 0.8;
            
            const response = await ApiService.post('/predictions/run', {
                machineId: selectedMachine,
                model: selectedModel,
                horizon: parseInt(horizon),
                confidenceThreshold: parseFloat(threshold)
            });
            
            if (response.success) {
                displayResults(response.data);
                Utils.ui.showToast('Prediction completed successfully', 'success');
                loadHistory(); // Refresh history
            }
            
        } catch (error) {
            Utils.ui.showToast('Failed to run prediction', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    };
    
    const displayResults = (data) => {
        const resultsSection = document.getElementById('resultsSection');
        if (!resultsSection) return;
        
        resultsSection.classList.add('show');
        
        // Update RUL
        document.getElementById('rulValue').textContent = data.rul.toLocaleString();
        
        // Update confidence
        document.getElementById('confidenceValue').textContent = data.confidence + '%';
        document.getElementById('confidenceFill').style.width = data.confidence + '%';
        
        // Update machine info
        document.getElementById('predictionMachine').textContent = data.machineName;
        document.getElementById('modelUsed').textContent = data.model;
        document.getElementById('predictionTime').textContent = Utils.date.formatDate(new Date(), 'MMM DD, YYYY HH:mm');
        document.getElementById('dataPoints').textContent = data.dataPoints.toLocaleString();
        document.getElementById('failureProbability').textContent = (100 - data.confidence) + '%';
        
        // Update health badge
        const healthBadge = document.getElementById('healthBadge');
        healthBadge.className = `health-badge health-${data.status}`;
        healthBadge.textContent = Utils.string.capitalize(data.status);
        
        // Update recommendations
        const list = document.getElementById('recommendationsList');
        list.innerHTML = data.recommendations.map(rec => `<li>${rec}</li>`).join('');
        
        // Update maintenance plan
        document.getElementById('nextInspection').textContent = data.nextInspection;
        document.getElementById('partsNeeded').textContent = data.partsNeeded || 'None';
        document.getElementById('estimatedCost').textContent = data.estimatedCost;
        
        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    };
    
    // ============================================
    // ACTIONS
    // ============================================
    
    const viewPrediction = (id) => {
        window.location.href = `/prediction-details.html?id=${id}`;
    };
    
    const refreshHistory = () => {
        loadHistory();
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        init,
        selectMachine,
        selectModel,
        viewPrediction,
        refreshHistory,
    };
})();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('predictions-page')) {
        Predictions.init();
    }
});

window.Predictions = Predictions;