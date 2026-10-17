// ============================================
// SYNAPSEPM MAIN APPLICATION
// Production Ready Application Entry
// ============================================

const App = (() => {
    'use strict';
    
    // ============================================
    // INITIALIZATION
    // ============================================
    
    const init = () => {
        console.log('SynapsePM Application Starting...');
        
        // Initialize features
        initTheme();
        initMobileMenu();
        initNavbarScroll();
        initNetworkListeners();
        initPerformanceMonitoring();
        
        // Check authentication
        checkAuth();
        
        // Load user data if authenticated
        if (AuthService.isAuthenticated()) {
            loadUserData();
        }
        
        // Add global event listeners
        addGlobalEventListeners();
        
        console.log('SynapsePM Application Started');
    };
    
    // ============================================
    // THEME MANAGEMENT
    // ============================================
    
    const initTheme = () => {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        
        const toggle = document.getElementById('themeToggle');
        if (toggle) {
            const icon = toggle.querySelector('i');
            icon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
            
            toggle.addEventListener('click', () => {
                const currentTheme = document.documentElement.getAttribute('data-theme');
                const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                
                document.documentElement.setAttribute('data-theme', newTheme);
                localStorage.setItem('theme', newTheme);
                
                const icon = toggle.querySelector('i');
                icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
            });
        }
    };
    
    // ============================================
    // MOBILE MENU
    // ============================================
    
    const initMobileMenu = () => {
        const toggle = document.getElementById('mobileToggle');
        const close = document.getElementById('mobileClose');
        const menu = document.getElementById('mobileMenu');
        
        if (!toggle || !menu) return;
        
        toggle.addEventListener('click', () => {
            menu.classList.add('active');
            document.body.style.overflow = 'hidden';
        });
        
        if (close) {
            close.addEventListener('click', () => {
                menu.classList.remove('active');
                document.body.style.overflow = '';
            });
        }
        
        // Close on click outside
        document.addEventListener('click', (e) => {
            if (menu.classList.contains('active') && 
                !menu.contains(e.target) && 
                !toggle.contains(e.target)) {
                menu.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
        
        // Close on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && menu.classList.contains('active')) {
                menu.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    };
    
    // ============================================
    // NAVBAR SCROLL EFFECT
    // ============================================
    
    const initNavbarScroll = () => {
        const navbar = document.querySelector('.navbar');
        if (!navbar) return;
        
        let lastScroll = 0;
        
        window.addEventListener('scroll', Utils.browser.throttle(() => {
            const currentScroll = window.pageYOffset;
            
            if (currentScroll > 50) {
                navbar.style.boxShadow = 'var(--shadow-md)';
                navbar.style.background = 'var(--color-surface)';
            } else {
                navbar.style.boxShadow = 'var(--shadow-sm)';
            }
            
            lastScroll = currentScroll;
        }, 100));
    };
    
    // ============================================
    // NETWORK LISTENERS
    // ============================================
    
    const initNetworkListeners = () => {
        Utils.browser.addNetworkListeners(
            () => {
                Utils.ui.showToast('Back online!', 'success');
            },
            () => {
                Utils.ui.showToast('No internet connection', 'error');
            }
        );
    };
    
    // ============================================
    // PERFORMANCE MONITORING
    // ============================================
    
    const initPerformanceMonitoring = () => {
        if (!CONFIG.MONITORING.ENABLED) return;
        
        // Monitor page load performance
        window.addEventListener('load', () => {
            const timing = performance.getEntriesByType('navigation')[0];
            if (timing) {
                const metrics = {
                    dns: timing.domainLookupEnd - timing.domainLookupStart,
                    connect: timing.connectEnd - timing.connectStart,
                    ttfb: timing.responseStart - timing.requestStart,
                    domLoad: timing.domContentLoadedEventEnd - timing.navigationStart,
                    windowLoad: timing.loadEventEnd - timing.navigationStart,
                };
                
                // Send to analytics (sample only)
                if (Math.random() < CONFIG.MONITORING.SAMPLE_RATE) {
                    fetch(`${CONFIG.API.BASE_URL}/monitoring/performance`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(metrics),
                        keepalive: true,
                    }).catch(() => {});
                }
            }
        });
        
        // Monitor JavaScript errors
        window.addEventListener('error', (event) => {
            if (CONFIG.MONITORING.ERROR_TRACKING) {
                const errorData = {
                    message: event.message,
                    filename: event.filename,
                    lineno: event.lineno,
                    colno: event.colno,
                    stack: event.error?.stack,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    timestamp: new Date().toISOString(),
                };
                
                fetch(`${CONFIG.API.BASE_URL}/monitoring/errors`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(errorData),
                    keepalive: true,
                }).catch(() => {});
            }
        });
        
        // Monitor unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            if (CONFIG.MONITORING.ERROR_TRACKING) {
                const errorData = {
                    message: event.reason?.message || 'Unhandled Promise Rejection',
                    stack: event.reason?.stack,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    timestamp: new Date().toISOString(),
                };
                
                fetch(`${CONFIG.API.BASE_URL}/monitoring/errors`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(errorData),
                    keepalive: true,
                }).catch(() => {});
            }
        });
    };
    
    // ============================================
    // AUTHENTICATION CHECK
    // ============================================
    
    const checkAuth = () => {
        const publicPages = [
            '/index.html',
            '/login.html',
            '/signup.html',
            '/explore.html',
            '/about.html',
            '/contact.html',
            '/demo.html',
            '/docs.html',
            '/blog.html',
            '/careers.html',
            '/privacy.html',
            '/terms.html',
            '/security.html',
            '/404.html',
        ];
        
        const currentPath = window.location.pathname;
        const isPublicPage = publicPages.some(page => currentPath.endsWith(page));
        
        if (!isPublicPage && !AuthService.isAuthenticated()) {
            // Show login prompt
            const modal = document.getElementById('loginPromptModal');
            if (modal) {
                modal.classList.add('show');
                document.body.style.overflow = 'hidden';
            } else {
                // Fallback redirect
                window.location.href = '/login.html';
            }
        }
    };
    
    // ============================================
    // LOAD USER DATA
    // ============================================
    
    const loadUserData = () => {
        const user = AuthService.getUser();
        if (!user) return;
        
        // Update user elements
        document.querySelectorAll('.user-name').forEach(el => {
            el.textContent = user.name || user.email;
        });
        
        document.querySelectorAll('.user-email').forEach(el => {
            el.textContent = user.email || '';
        });
        
        document.querySelectorAll('.user-avatar').forEach(el => {
            const initials = (user.name || user.email || 'U')
                .split(' ')
                .map(n => n[0])
                .join('')
                .substring(0, 2)
                .toUpperCase();
            el.textContent = initials;
        });
        
        document.querySelectorAll('.user-plan').forEach(el => {
            el.textContent = user.plan || 'Free';
        });
    };
    
    // ============================================
    // GLOBAL EVENT LISTENERS
    // ============================================
    
    const addGlobalEventListeners = () => {
        // Handle logout buttons
        document.querySelectorAll('.logout-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                if (confirm('Are you sure you want to logout?')) {
                    await AuthService.logout();
                }
            });
        });
        
        // Handle modal close buttons
        document.querySelectorAll('.modal-close, [data-dismiss="modal"]').forEach(btn => {
            btn.addEventListener('click', () => {
                const modal = btn.closest('.modal');
                if (modal) {
                    modal.classList.remove('show');
                    document.body.style.overflow = '';
                }
            });
        });
        
        // Handle dropdown menus
        document.querySelectorAll('.dropdown-toggle').forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                const menu = toggle.nextElementSibling;
                if (menu) {
                    menu.classList.toggle('show');
                }
            });
        });
        
        // Close dropdowns on click outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.dropdown')) {
                document.querySelectorAll('.dropdown-menu.show').forEach(menu => {
                    menu.classList.remove('show');
                });
            }
        });
    };
    
    // ============================================
    // PUBLIC API
    // ============================================
    
    return {
        init,
        loadUserData,
    };
})();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// Make available globally
window.App = App;