// ============================================
// SYNAPSEPM API SERVICE
// Production Ready API Service
// ============================================

const ApiService = (() => {
    'use strict';
    
    // Configuration
    const BASE_URL = CONFIG.API.BASE_URL;
    const TIMEOUT = CONFIG.API.TIMEOUT;
    const RETRY_ATTEMPTS = CONFIG.API.RETRY_ATTEMPTS;
    const RETRY_DELAY = CONFIG.API.RETRY_DELAY;
    
    // Request queue for rate limiting
    const requestQueue = [];
    let isProcessing = false;
    
    // ============================================
    // CORE REQUEST FUNCTION
    // ============================================
    
    const request = async (endpoint, options = {}, retryCount = 0) => {
        const url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`;
        
        // Default headers
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-Request-ID': generateRequestId(),
            ...options.headers,
        };
        
        // Add auth token if available
        const token = localStorage.getItem(CONFIG.AUTH.TOKEN_KEY);
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        // Add CSRF token for mutations
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method)) {
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
            if (csrfToken) {
                headers['X-CSRF-Token'] = csrfToken;
            }
        }
        
        const config = {
            ...options,
            headers,
            credentials: 'include',
            mode: 'cors',
        };
        
        // Add timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), TIMEOUT);
        config.signal = controller.signal;
        
        try {
            const response = await fetch(url, config);
            clearTimeout(timeoutId);
            
            // Handle rate limiting
            if (response.status === 429) {
                const retryAfter = response.headers.get('Retry-After') || 60;
                await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
                return request(endpoint, options, retryCount);
            }
            
            // Handle unauthorized
            if (response.status === 401) {
                if (retryCount < RETRY_ATTEMPTS) {
                    // Try to refresh token
                    const refreshed = await AuthService.refreshToken();
                    if (refreshed) {
                        return request(endpoint, options, retryCount + 1);
                    }
                }
                // Redirect to login
                window.location.href = '/login.html';
                throw new Error('Authentication failed');
            }
            
            // Handle forbidden
            if (response.status === 403) {
                throw new Error('You do not have permission to perform this action');
            }
            
            // Handle not found
            if (response.status === 404) {
                throw new Error('Resource not found');
            }
            
            // Handle server errors
            if (response.status >= 500) {
                if (retryCount < RETRY_ATTEMPTS) {
                    await new Promise(resolve => setTimeout(resolve, RETRY_DELAY * Math.pow(2, retryCount)));
                    return request(endpoint, options, retryCount + 1);
                }
                throw new Error('Server error. Please try again later.');
            }
            
            // Parse response
            const contentType = response.headers.get('content-type');
            let data;
            
            if (contentType?.includes('application/json')) {
                data = await response.json();
            } else if (contentType?.includes('text/')) {
                data = await response.text();
            } else {
                data = await response.blob();
            }
            
            // Return response with metadata
            return {
                success: response.ok,
                status: response.status,
                statusText: response.statusText,
                headers: response.headers,
                data,
                timestamp: new Date().toISOString(),
                requestId: headers['X-Request-ID'],
            };
            
        } catch (error) {
            clearTimeout(timeoutId);
            
            if (error.name === 'AbortError') {
                throw new Error('Request timeout. Please try again.');
            }
            
            if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
                if (!navigator.onLine) {
                    throw new Error('No internet connection. Please check your network.');
                }
                throw new Error('Unable to connect to server. Please try again.');
            }
            
            throw error;
        }
    };
    
    // ============================================
    // HELPER FUNCTIONS
    // ============================================
    
    const generateRequestId = () => {
        return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    };
    
    const processQueue = async () => {
        if (isProcessing || requestQueue.length === 0) return;
        
        isProcessing = true;
        const { endpoint, options, resolve, reject } = requestQueue.shift();
        
        try {
            const result = await request(endpoint, options);
            resolve(result);
        } catch (error) {
            reject(error);
        } finally {
            isProcessing = false;
            processQueue();
        }
    };
    
    // ============================================
    // HTTP METHODS
    // ============================================
    
    const get = async (endpoint, params = {}, options = {}) => {
        const url = new URL(endpoint, BASE_URL);
        
        // Add query parameters
        Object.keys(params).forEach(key => {
            if (params[key] !== undefined && params[key] !== null) {
                url.searchParams.append(key, params[key]);
            }
        });
        
        return request(url.toString(), {
            method: 'GET',
            ...options,
        });
    };
    
    const post = async (endpoint, data = {}, options = {}) => {
        return request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
            ...options,
        });
    };
    
    const put = async (endpoint, data = {}, options = {}) => {
        return request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data),
            ...options,
        });
    };
    
    const patch = async (endpoint, data = {}, options = {}) => {
        return request(endpoint, {
            method: 'PATCH',
            body: JSON.stringify(data),
            ...options,
        });
    };
    
    const del = async (endpoint, options = {}) => {
        return request(endpoint, {
            method: 'DELETE',
            ...options,
        });
    };
    
    // ============================================
    // FILE UPLOAD
    // ============================================
    
    const upload = async (endpoint, file, onProgress = null) => {
        const formData = new FormData();
        formData.append('file', file);
        
        // Validate file
        if (file.size > CONFIG.UPLOAD.MAX_FILE_SIZE) {
            throw new Error(`File too large. Max size: ${CONFIG.UPLOAD.MAX_FILE_SIZE / 1024 / 1024}MB`);
        }
        
        if (!CONFIG.UPLOAD.ALLOWED_TYPES.includes(file.type)) {
            throw new Error('File type not allowed');
        }
        
        const xhr = new XMLHttpRequest();
        
        return new Promise((resolve, reject) => {
            xhr.upload.addEventListener('progress', (e) => {
                if (onProgress && e.lengthComputable) {
                    const percent = (e.loaded / e.total) * 100;
                    onProgress(percent);
                }
            });
            
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch {
                        resolve(xhr.responseText);
                    }
                } else {
                    reject(new Error(`Upload failed: ${xhr.statusText}`));
                }
            });
            
            xhr.addEventListener('error', () => reject(new Error('Upload failed')));
            xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));
            
            xhr.open('POST', `${BASE_URL}${endpoint}`);
            
            // Add auth token
            const token = localStorage.getItem(CONFIG.AUTH.TOKEN_KEY);
            if (token) {
                xhr.setRequestHeader('Authorization', `Bearer ${token}`);
            }
            
            xhr.send(formData);
        });
    };
    
    // ============================================
    // BATCH REQUESTS
    // ============================================
    
    const batch = async (requests) => {
        return Promise.all(requests.map(req => {
            const { method, endpoint, data } = req;
            switch (method.toUpperCase()) {
                case 'GET': return get(endpoint);
                case 'POST': return post(endpoint, data);
                case 'PUT': return put(endpoint, data);
                case 'PATCH': return patch(endpoint, data);
                case 'DELETE': return del(endpoint);
                default: throw new Error(`Unknown method: ${method}`);
            }
        }));
    };
    
    // ============================================
    // CACHE MANAGEMENT
    // ============================================
    
    const cache = new Map();
    
    const getCached = async (key, fetcher, ttl = 300000) => { // 5 minutes default
        const cached = cache.get(key);
        if (cached && Date.now() - cached.timestamp < ttl) {
            return cached.data;
        }
        
        const data = await fetcher();
        cache.set(key, {
            data,
            timestamp: Date.now(),
        });
        return data;
    };
    
    const invalidateCache = (key) => {
        cache.delete(key);
    };
    
    const clearCache = () => {
        cache.clear();
    };
    
    // ============================================
    // EXPORT
    // ============================================
    
    return {
        get,
        post,
        put,
        patch,
        delete: del,
        upload,
        batch,
        getCached,
        invalidateCache,
        clearCache,
    };
})();

// Make available globally
window.ApiService = ApiService;


