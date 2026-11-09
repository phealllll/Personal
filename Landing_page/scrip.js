
const API_URL = "http://127.0.0.1:8000/api";
const SESSION_TIMEOUT = 5 * 60 * 1000; // 5 minutes
let activeSession = null;
let currentChart = null;

window.onload = () => {
    checkSession();
};

document.addEventListener('mousemove', keepSessionAlive);
document.addEventListener('keydown', keepSessionAlive);

function saveSession(username, role) {
    const sessionData = { username, role, lastActive: Date.now() };
    localStorage.setItem('nova_session', JSON.stringify(sessionData));
}

function clearSession() {
    localStorage.removeItem('nova_session');
    activeSession = null;
}

function checkSession() {
    const stored = localStorage.getItem('nova_session');
    if (!stored) return false;

    const sessionData = JSON.parse(stored);
    
    if (Date.now() - sessionData.lastActive < SESSION_TIMEOUT) {
        activeSession = { username: sessionData.username, role: sessionData.role };
        saveSession(activeSession.username, activeSession.role);
        
        toggleAppVisibility(true);
        loadDepartmentData('telemetry', document.querySelector('.dept-btn'));
        return true;
    } else {
        clearSession();
        return false;
    }
}

function keepSessionAlive() {
    if (activeSession) {
        saveSession(activeSession.username, activeSession.role);
    }
}

// ==========================================
// AUTHENTICATION LOGIC
// ==========================================
function toggleAuthMode() {
    document.getElementById('login-form').classList.toggle('hidden');
    document.getElementById('register-form').classList.toggle('hidden');
    hideAlert();
}

function showAlert(msg, isError = true) {
    const alert = document.getElementById('auth-alert');
    alert.className = `alert-box ${isError ? 'alert-error' : 'alert-success'}`;
    alert.innerText = msg;
}

function hideAlert() {
    document.getElementById('auth-alert').className = 'alert-box hidden';
}

function toggleAppVisibility(isLoggedIn) {
    if (isLoggedIn) {
        document.getElementById('auth-overlay').classList.add('hidden');
        document.getElementById('main-app').classList.remove('hidden');
        document.getElementById('display-user').innerText = activeSession.username;
        document.getElementById('display-role').innerText = activeSession.role;
    } else {
        document.getElementById('main-app').classList.add('hidden');
        document.getElementById('auth-overlay').classList.remove('hidden');
        document.getElementById('login-user').value = '';
        document.getElementById('login-pass').value = '';
        hideAlert();
    }
}

async function registerUser() {
    const username = document.getElementById('reg-user').value.trim();
    const password = document.getElementById('reg-pass').value;
    const role = document.getElementById('reg-role').value;
    
    if (!username || !password) return showAlert("Username and Password are required.");

    try {
        const response = await fetch(`${API_URL}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showAlert(data.message, false);
            setTimeout(toggleAuthMode, 1500);
        } else {
            showAlert(data.detail);
        }
    } catch (error) {
        showAlert("API Server Offline. Ensure Uvicorn is running.");
    }
}

async function authenticate() {
    const username = document.getElementById('login-user').value.trim();
    const password = document.getElementById('login-pass').value;
    
    if (!username || !password) return showAlert("Credentials required.");

    try {
        const response = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            activeSession = { username: data.username, role: data.role };
            saveSession(data.username, data.role);
            toggleAppVisibility(true);
            loadDepartmentData('telemetry', document.querySelector('.dept-btn'));
        } else {
            showAlert("Invalid credentials.");
        }
    } catch (error) {
        showAlert("API Server Offline. Ensure Uvicorn is running.");
    }
}

function logout() {
    clearSession();
    toggleAppVisibility(false);
    if (currentChart) currentChart.destroy();
}

// ==========================================
// NAVIGATION & UI STATE
// ==========================================
function switchMainTab(tabId, btnElement) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.getElementById(tabId).classList.remove('hidden');
    
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    if (btnElement) btnElement.classList.add('active');
}

// ==========================================
// DATA FETCHING & RENDERING
// ==========================================
async function loadDepartmentData(department, btnElement) {
    if (!activeSession) return;

    // Update active department button
    document.querySelectorAll('.vault-card').forEach(btn => btn.classList.remove('active'));
    if (btnElement) btnElement.classList.add('active');

    document.getElementById('vault-grid').classList.add('data-loaded');

    // DOM Elements
    const loading = document.getElementById('loading-state');
    const content = document.getElementById('dashboard-content');
    const errBlock = document.getElementById('rbac-error-content');
    
    // Reset Views
    loading.classList.remove('hidden');
    loading.innerText = 'Establishing secure connection...';
    content.classList.add('hidden');
    errBlock.classList.add('hidden');

    try {
        const response = await fetch(`${API_URL}/data/${department}?role=${activeSession.role}`);
        const data = await response.json();

        if (response.status === 403) {
            loading.classList.add('hidden');
            errBlock.classList.remove('hidden');
            document.getElementById('rbac-error-message').innerText = data.detail;
            return;
        }

        if (response.status === 404 || !data.length) {
            loading.innerText = data.detail || `⚠️ No data found for ${department.toUpperCase()}.`;
            return;
        }

        loading.classList.add('hidden');
        content.classList.remove('hidden');
        
        renderTable(data);
        renderChart(department, data);

    } catch (err) {
        loading.innerText = '❌ Connection Refused. Ensure API is online.';
    }
}

function renderTable(data) {
    const tableContainer = document.getElementById('table-container');
    let html = '<table><thead><tr>';
    
    Object.keys(data[0]).forEach(key => {
        html += `<th>${key.replace(/_/g, ' ').toUpperCase()}</th>`;
    });
    
    html += '</tr></thead><tbody>';
    
    data.forEach(row => {
        html += '<tr>';
        Object.values(row).forEach(val => {
            let displayVal = String(val);
            if (displayVal.length > 25) displayVal = displayVal.substring(0, 22) + '...';
            html += `<td>${displayVal}</td>`;
        });
        html += '</tr>';
    });
    
    html += '</tbody></table>';
    tableContainer.innerHTML = html;
}

function renderChart(department, data) {
    const ctx = document.getElementById('novaChart').getContext('2d');
    const chartTitle = document.getElementById('chart-title');
    
    if (currentChart) currentChart.destroy();
    
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.05)';

    let config = { 
        options: { responsive: true, maintainAspectRatio: false } 
    };

    switch (department) {
        case 'telemetry':
            chartTitle.innerText = "Asset Temperature Trends";
            config.type = 'line';
            config.data = {
                labels: data.map(d => new Date(d.timestamp).toLocaleTimeString()),
                datasets: [{ 
                    label: 'Temp (°C)', 
                    data: data.map(d => d.temperature_c), 
                    borderColor: '#00f3ff', 
                    backgroundColor: 'rgba(0, 243, 255, 0.1)', 
                    borderWidth: 2, 
                    fill: true, 
                    tension: 0.4 
                }]
            };
            break;

        case 'accounting':
            chartTitle.innerText = "Expenses by Cost Center";
            const expenses = data.reduce((acc, curr) => { 
                acc[curr.cost_center] = (acc[curr.cost_center] || 0) + parseFloat(curr.amount); 
                return acc; 
            }, {});
            
            config.type = 'bar';
            config.data = { 
                labels: Object.keys(expenses), 
                datasets: [{ 
                    label: 'Total Spend', 
                    data: Object.values(expenses), 
                    backgroundColor: '#00f3ff', 
                    borderRadius: 4 
                }] 
            };
            break;

        case 'human-resources':
            chartTitle.innerText = "Facility Access Distribution";
            const actions = data.reduce((acc, curr) => { 
                acc[curr.action] = (acc[curr.action] || 0) + 1; 
                return acc; 
            }, {});
            
            config.type = 'doughnut';
            config.data = { 
                labels: Object.keys(actions), 
                datasets: [{ 
                    data: Object.values(actions), 
                    backgroundColor: ['#00f3ff', '#3b82f6', '#8b5cf6', '#ec4899'], 
                    borderWidth: 0 
                }] 
            };
            break;

        default:
            chartTitle.innerText = "System Event Frequency";
            const keyColumn = department === 'security' ? 'login_status' : 'status';
            const counts = data.reduce((acc, curr) => { 
                const val = curr[keyColumn] || 'Unknown'; 
                acc[val] = (acc[val] || 0) + 1; 
                return acc; 
            }, {});
            
            config.type = 'bar';
            config.data = { 
                labels: Object.keys(counts), 
                datasets: [{ 
                    label: 'Event Count', 
                    data: Object.values(counts), 
                    backgroundColor: '#8b5cf6', 
                    borderRadius: 4 
                }] 
            };
            break;
    }
    
    currentChart = new Chart(ctx, config);
}