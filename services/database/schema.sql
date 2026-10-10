-- ============================================================
-- SYNAPSEPM - ENTERPRISE PRODUCTION DATABASE SCHEMA v6.0
-- COMPLETE - ALL FEATURES FIXED & ENHANCED
-- PostgreSQL 15+ Enterprise Edition
-- ============================================================

-- ============================================================
-- PART 1: EXTENSIONS
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "timescaledb";
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "hstore";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- PART 2: ENUMS
-- ============================================================

-- User Management Enums
CREATE TYPE user_role AS ENUM ('super_admin', 'org_admin', 'manager', 'engineer', 'viewer', 'api_only', 'system');
CREATE TYPE user_status AS ENUM ('active', 'inactive', 'locked', 'suspended', 'pending_verification', 'pending_password_reset', 'pending_approval', 'deleted');
CREATE TYPE user_plan AS ENUM ('free', 'basic', 'starter', 'professional', 'enterprise', 'custom');

-- Organization Enums
CREATE TYPE organization_status AS ENUM ('active', 'suspended', 'archived', 'pending', 'trial', 'expired');
CREATE TYPE organization_plan AS ENUM ('FREE', 'BASIC', 'STARTER', 'PROFESSIONAL', 'ENTERPRISE', 'CUSTOM');

-- Subscription Enums
CREATE TYPE subscription_status AS ENUM ('trial', 'active', 'past_due', 'cancelled', 'expired', 'paused', 'grace_period', 'incomplete');
CREATE TYPE billing_cycle AS ENUM ('monthly', 'yearly', 'quarterly', 'custom');

-- Machine Enums
CREATE TYPE machine_status AS ENUM ('online', 'offline', 'maintenance', 'degraded', 'error', 'unknown', 'decommissioned', 'starting', 'stopping', 'updating');
CREATE TYPE health_status AS ENUM ('healthy', 'warning', 'critical', 'failure_imminent', 'unknown', 'degraded', 'recovering');
CREATE TYPE machine_type AS ENUM ('pump', 'motor', 'compressor', 'conveyor', 'generator', 'turbine', 'mixer', 'separator', 'crusher', 'dryer', 'fan', 'blower');

-- Alert Enums
CREATE TYPE alert_severity AS ENUM ('debug', 'info', 'low', 'medium', 'high', 'critical');
CREATE TYPE alert_status AS ENUM ('active', 'acknowledged', 'resolved', 'suppressed', 'escalated', 'ignored', 'reopened', 'closed');

-- Prediction Enums
CREATE TYPE prediction_status AS ENUM ('pending', 'queued', 'processing', 'completed', 'failed', 'validating', 'cancelled');
CREATE TYPE prediction_model_type AS ENUM ('lstm', 'xgboost', 'random_forest', 'gradient_boosting', 'svm', 'neural_network', 'decision_tree', 'ensemble', 'transformer', 'custom');

-- Payment Enums
CREATE TYPE payment_status AS ENUM ('pending', 'processing', 'success', 'failed', 'refunded', 'partial_refund', 'chargeback', 'cancelled', 'on_hold');
CREATE TYPE payment_provider AS ENUM ('stripe', 'razorpay', 'paypal', 'paddle', 'esewa', 'ime_pay', 'khalti', 'nmb_bank', 'custom');

-- Invoice Enums
CREATE TYPE invoice_status AS ENUM ('draft', 'sent', 'paid', 'overdue', 'cancelled', 'refunded', 'partially_paid', 'void');

-- Maintenance Enums
CREATE TYPE maintenance_type AS ENUM ('preventive', 'corrective', 'predictive', 'emergency', 'inspection', 'overhaul', 'calibration', 'repair');
CREATE TYPE maintenance_status AS ENUM ('scheduled', 'approved', 'in_progress', 'completed', 'cancelled', 'delayed', 'on_hold', 'rejected');

-- Work Order Enums
CREATE TYPE work_order_status AS ENUM ('draft', 'pending', 'approved', 'in_progress', 'completed', 'cancelled', 'on_hold', 'rejected', 'review');
CREATE TYPE work_order_priority AS ENUM ('low', 'medium', 'high', 'critical', 'emergency');

-- Download Enums
CREATE TYPE download_status AS ENUM ('pending', 'started', 'completed', 'failed', 'cancelled', 'paused', 'retrying');
CREATE TYPE download_platform AS ENUM ('windows', 'macos', 'linux', 'docker', 'source', 'models', 'android', 'ios', 'web', 'api');

-- Notification Enums
CREATE TYPE notification_type AS ENUM ('system', 'announcement', 'update', 'reminder', 'invitation', 'alert', 'warning', 'maintenance', 'prediction', 'payment', 'subscription');
CREATE TYPE notification_channel AS ENUM ('email', 'sms', 'push', 'webhook', 'slack', 'teams', 'whatsapp');

-- Audit Enums
CREATE TYPE audit_action AS ENUM ('create', 'update', 'delete', 'soft_delete', 'restore', 'login', 'logout', 'export', 'import', 'view', 'approve', 'reject', 'suspend', 'activate', 'reset_password', 'change_permissions', 'api_access', 'mfa_enable', 'mfa_disable', 'password_change', 'permission_change');
CREATE TYPE audit_severity AS ENUM ('low', 'medium', 'high', 'critical');

-- Security Enums
CREATE TYPE data_sensitivity AS ENUM ('public', 'internal', 'confidential', 'restricted', 'critical');
CREATE TYPE key_rotation_status AS ENUM ('active', 'expired', 'revoked', 'compromised');

-- Feature Flags
CREATE TYPE feature_flag_type AS ENUM ('boolean', 'percentage', 'user_segment', 'environment', 'beta');

-- ============================================================
-- PART 3: UTILITY FUNCTIONS
-- ============================================================

-- Update timestamp function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Prevent audit update function
CREATE OR REPLACE FUNCTION prevent_audit_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit logs are immutable and cannot be updated';
END;
$$ LANGUAGE plpgsql;

-- Encryption functions
CREATE OR REPLACE FUNCTION encrypt_data(
    data TEXT,
    key_id VARCHAR(100)
) RETURNS BYTEA AS $$
DECLARE
    key BYTEA;
    iv BYTEA;
    encrypted BYTEA;
BEGIN
    SELECT key_encrypted INTO key 
    FROM encryption_keys 
    WHERE key_id = $2 AND is_active = TRUE 
    ORDER BY key_version DESC LIMIT 1;
    
    IF key IS NULL THEN
        RAISE EXCEPTION 'Encryption key not found: %', $2;
    END IF;
    
    iv := gen_random_bytes(16);
    encrypted := encrypt($1::BYTEA, key, 'aes-gcm', iv);
    RETURN iv || encrypted;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION decrypt_data(
    encrypted_data BYTEA,
    key_id VARCHAR(100)
) RETURNS TEXT AS $$
DECLARE
    key BYTEA;
    iv BYTEA;
    ciphertext BYTEA;
    decrypted BYTEA;
BEGIN
    SELECT key_encrypted INTO key 
    FROM encryption_keys 
    WHERE key_id = $2 AND is_active = TRUE 
    ORDER BY key_version DESC LIMIT 1;
    
    IF key IS NULL THEN
        RAISE EXCEPTION 'Decryption key not found: %', $2;
    END IF;
    
    iv := SUBSTRING(encrypted_data, 1, 16);
    ciphertext := SUBSTRING(encrypted_data, 17);
    decrypted := decrypt(ciphertext, key, 'aes-gcm', iv);
    RETURN decrypted::TEXT;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- PART 4: ENCRYPTION KEYS TABLE
-- ============================================================

CREATE TABLE encryption_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key_id VARCHAR(100) NOT NULL UNIQUE,
    key_version INTEGER NOT NULL DEFAULT 1,
    key_algorithm VARCHAR(50) NOT NULL DEFAULT 'AES-256-GCM',
    key_encrypted BYTEA NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    key_status key_rotation_status NOT NULL DEFAULT 'active',
    key_created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    key_activated_at TIMESTAMPTZ,
    key_expires_at TIMESTAMPTZ,
    key_retired_at TIMESTAMPTZ,
    rotation_schedule VARCHAR(50),
    kms_provider VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    is_primary BOOLEAN DEFAULT FALSE,
    created_by UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_encryption_keys_active ON encryption_keys(is_active);
CREATE INDEX idx_encryption_keys_primary ON encryption_keys(is_primary);
CREATE INDEX idx_encryption_keys_created ON encryption_keys(key_created_at);
CREATE INDEX idx_encryption_keys_status ON encryption_keys(key_status);

-- ============================================================
-- PART 5: ORGANIZATIONS TABLE
-- ============================================================

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    name VARCHAR(200) NOT NULL,
    subdomain CITEXT UNIQUE,
    industry VARCHAR(100),
    company_size VARCHAR(50),
    region VARCHAR(50) NOT NULL DEFAULT 'us-east-1',
    data_residency VARCHAR(50) NOT NULL DEFAULT 'us',
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    
    -- Contact Information
    primary_email CITEXT NOT NULL,
    _primary_phone BYTEA,
    _address BYTEA,
    _tax_id BYTEA,
    website VARCHAR(500),
    
    -- Plan & Subscription
    plan organization_plan NOT NULL DEFAULT 'FREE',
    plan_started_at TIMESTAMPTZ,
    plan_expires_at TIMESTAMPTZ,
    billing_cycle billing_cycle NOT NULL DEFAULT 'monthly',
    _stripe_customer_id BYTEA,
    _stripe_subscription_id BYTEA,
    _razorpay_customer_id BYTEA,
    _paypal_customer_id BYTEA,
    _paddle_customer_id BYTEA,
    
    -- Status
    status organization_status NOT NULL DEFAULT 'active',
    status_changed_at TIMESTAMPTZ,
    status_changed_by UUID,
    
    -- Limits
    max_users INTEGER NOT NULL DEFAULT 5 CHECK (max_users >= 1),
    max_machines INTEGER NOT NULL DEFAULT 5 CHECK (max_machines >= 1),
    max_predictions_per_month INTEGER NOT NULL DEFAULT 100,
    max_storage_gb DECIMAL(10, 2) NOT NULL DEFAULT 1.0,
    max_api_requests_per_day INTEGER NOT NULL DEFAULT 10000,
    max_team_members INTEGER NOT NULL DEFAULT 5,
    max_projects INTEGER NOT NULL DEFAULT 5,
    
    -- Current Usage
    current_users INTEGER DEFAULT 0,
    current_machines INTEGER DEFAULT 0,
    predictions_this_month INTEGER DEFAULT 0,
    storage_used_gb DECIMAL(10, 2) DEFAULT 0.0,
    api_requests_today INTEGER DEFAULT 0,
    
    -- Trial
    is_trial BOOLEAN DEFAULT FALSE,
    trial_ends_at TIMESTAMPTZ,
    
    -- Status Flags
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_suspended BOOLEAN NOT NULL DEFAULT FALSE,
    suspension_reason TEXT,
    suspension_expires_at TIMESTAMPTZ,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Features & Settings
    features JSONB DEFAULT '{}',
    settings JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    
    -- Compliance
    compliance_tags TEXT[] DEFAULT '{}',
    retention_policy_days INTEGER DEFAULT 365,
    legal_hold BOOLEAN DEFAULT FALSE,
    legal_hold_reason TEXT,
    legal_hold_until TIMESTAMPTZ,
    data_sensitivity data_sensitivity DEFAULT 'internal',
    
    -- Audit
    last_audit_at TIMESTAMPTZ,
    last_active_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_org_name ON organizations(name) WHERE deleted_at IS NULL;
CREATE INDEX idx_org_subdomain ON organizations(subdomain) WHERE deleted_at IS NULL;
CREATE INDEX idx_org_status ON organizations(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_org_plan ON organizations(plan) WHERE deleted_at IS NULL;
CREATE INDEX idx_org_region ON organizations(region) WHERE deleted_at IS NULL;
CREATE INDEX idx_org_active ON organizations(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_org_created ON organizations(created_at DESC);

-- ============================================================
-- PART 6: USERS TABLE
-- ============================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    -- Authentication
    username CITEXT NOT NULL,
    email CITEXT NOT NULL,
    _password_hash VARCHAR(256) NOT NULL,
    _password_salt VARCHAR(64),
    _mfa_secret BYTEA,
    password_changed_at TIMESTAMPTZ,
    password_expires_at TIMESTAMPTZ,
    
    -- SSO
    sso_id VARCHAR(255) UNIQUE,
    sso_provider VARCHAR(50),
    sso_metadata JSONB DEFAULT '{}',
    is_sso_user BOOLEAN DEFAULT FALSE,
    
    -- Personal Info
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200),
    job_title VARCHAR(100),
    department VARCHAR(100),
    _phone BYTEA,
    avatar_url VARCHAR(500),
    
    -- Role & Permissions
    role user_role NOT NULL DEFAULT 'viewer',
    permissions JSONB DEFAULT '{}',
    role_assignments JSONB DEFAULT '[]',
    
    -- Plan & Subscription
    plan user_plan NOT NULL DEFAULT 'free',
    subscription_id VARCHAR(100),
    subscription_end TIMESTAMPTZ,
    subscription_trial_end TIMESTAMPTZ,
    _paddle_customer_id BYTEA,
    _paddle_subscription_id BYTEA,
    
    -- Status
    status user_status NOT NULL DEFAULT 'active',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    is_api_user BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_methods JSONB DEFAULT '[]',
    _mfa_backup_codes BYTEA,
    
    -- Security
    login_attempts INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    last_login_ip INET,
    last_login_user_agent VARCHAR(500),
    last_activity_at TIMESTAMPTZ,
    last_login_location JSONB,
    
    -- Session
    session_token VARCHAR(255),
    session_expires_at TIMESTAMPTZ,
    device_fingerprints JSONB DEFAULT '[]',
    
    -- Preferences
    language VARCHAR(10) DEFAULT 'en',
    timezone VARCHAR(50) DEFAULT 'UTC',
    date_format VARCHAR(20) DEFAULT 'YYYY-MM-DD',
    time_format VARCHAR(20) DEFAULT 'HH:MM:SS',
    notification_preferences JSONB DEFAULT '{}',
    ui_preferences JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    
    -- Deactivation
    deactivated_at TIMESTAMPTZ,
    deactivation_reason TEXT,
    
    -- Consent
    consent_given_at TIMESTAMPTZ,
    consent_version VARCHAR(20),
    data_retention_consent BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_org ON users(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role ON users(role) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_status ON users(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_sso ON users(sso_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_department ON users(department) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_plan ON users(plan) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_username ON users(username) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_org_username ON users(organization_id, username) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_org_email ON users(organization_id, email) WHERE deleted_at IS NULL;

-- User update trigger
CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 7: USER PASSWORD HISTORY TABLE
-- ============================================================

CREATE TABLE user_password_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    password_hash VARCHAR(256) NOT NULL,
    password_salt VARCHAR(64),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    ip_address INET,
    user_agent VARCHAR(500)
);

CREATE INDEX idx_password_history_user ON user_password_history(user_id);
CREATE INDEX idx_password_history_changed ON user_password_history(changed_at DESC);

-- ============================================================
-- PART 8: USER SESSIONS TABLE
-- ============================================================

CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    refresh_token VARCHAR(255) UNIQUE,
    ip_address INET,
    user_agent VARCHAR(500),
    device_type VARCHAR(50),
    browser VARCHAR(50),
    os VARCHAR(50),
    device_fingerprint VARCHAR(255),
    location JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_session_user ON user_sessions(user_id);
CREATE INDEX idx_session_token ON user_sessions(session_token);
CREATE INDEX idx_session_refresh ON user_sessions(refresh_token);
CREATE INDEX idx_session_active ON user_sessions(is_active);

-- Session update trigger
CREATE TRIGGER trg_sessions_updated
    BEFORE UPDATE ON user_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 9: OAUTH ACCOUNTS TABLE
-- ============================================================

CREATE TABLE oauth_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    provider_user_id VARCHAR(255) NOT NULL,
    provider_email VARCHAR(255),
    provider_name VARCHAR(255),
    provider_avatar VARCHAR(500),
    provider_username VARCHAR(255),
    access_token TEXT,
    refresh_token TEXT,
    token_type VARCHAR(50),
    scope TEXT,
    token_expires_at TIMESTAMPTZ,
    refresh_token_expires_at TIMESTAMPTZ,
    provider_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, provider_user_id)
);

CREATE INDEX idx_oauth_user ON oauth_accounts(user_id);
CREATE INDEX idx_oauth_provider ON oauth_accounts(provider);

-- OAuth update trigger
CREATE TRIGGER trg_oauth_updated
    BEFORE UPDATE ON oauth_accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 10: PASSWORD RESET TOKENS TABLE
-- ============================================================

CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reset_token ON password_reset_tokens(token_hash);
CREATE INDEX idx_reset_user ON password_reset_tokens(user_id);

-- ============================================================
-- PART 11: EMAIL VERIFICATION TOKENS TABLE
-- ============================================================

CREATE TABLE email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    email CITEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_verification_token ON email_verification_tokens(token_hash);
CREATE INDEX idx_verification_user ON email_verification_tokens(user_id);

-- ============================================================
-- PART 12: INVITATIONS TABLE
-- ============================================================

CREATE TABLE invitations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    invited_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    email CITEXT NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_invitation_token ON invitations(token_hash);
CREATE INDEX idx_invitation_email ON invitations(email);
CREATE INDEX idx_invitation_org ON invitations(organization_id);

-- ============================================================
-- PART 13: SECURITY EVENTS TABLE
-- ============================================================

CREATE TABLE security_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    severity audit_severity NOT NULL DEFAULT 'medium',
    description TEXT NOT NULL,
    ip_address INET,
    user_agent VARCHAR(500),
    session_id VARCHAR(255),
    additional_data JSONB DEFAULT '{}',
    is_flagged BOOLEAN DEFAULT FALSE,
    flag_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_security_user ON security_events(user_id);
CREATE INDEX idx_security_org ON security_events(organization_id);
CREATE INDEX idx_security_type ON security_events(event_type);
CREATE INDEX idx_security_timestamp ON security_events(event_timestamp DESC);

-- ============================================================
-- PART 14: API KEYS TABLE
-- ============================================================

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    api_key_hash VARCHAR(128) NOT NULL UNIQUE,
    key_prefix VARCHAR(10) NOT NULL,
    permissions JSONB DEFAULT '{"read": true, "write": false, "admin": false}',
    rate_limit INTEGER DEFAULT 1000,
    rate_limit_period VARCHAR(20) DEFAULT 'day',
    status VARCHAR(20) DEFAULT 'active',
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_apikey_user ON api_keys(user_id);
CREATE INDEX idx_apikey_org ON api_keys(organization_id);
CREATE INDEX idx_apikey_hash ON api_keys(api_key_hash);
CREATE INDEX idx_apikey_name ON api_keys(name);

-- API Key update trigger
CREATE TRIGGER trg_apikey_updated
    BEFORE UPDATE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 15: MACHINES TABLE
-- ============================================================

CREATE TABLE machines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Basic Information
    name VARCHAR(200) NOT NULL,
    machine_type machine_type NOT NULL,
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    serial_number VARCHAR(100),
    asset_tag VARCHAR(100),
    year_manufactured INTEGER,
    
    -- Asset Management
    asset_id VARCHAR(100),
    purchase_date TIMESTAMPTZ,
    purchase_cost DECIMAL(18, 4),
    depreciation_rate DECIMAL(5, 4),
    salvage_value DECIMAL(18, 4),
    expected_lifetime_hours DECIMAL(10, 2),
    end_of_life_date TIMESTAMPTZ,
    current_value DECIMAL(18, 4),
    
    -- Location
    location VARCHAR(200),
    site VARCHAR(100),
    building VARCHAR(100),
    floor VARCHAR(50),
    room VARCHAR(50),
    area VARCHAR(100),
    coordinates GEOGRAPHY(POINT, 4326),
    
    -- Description & Documentation
    description TEXT,
    specifications JSONB,
    documentation_url VARCHAR(500),
    
    -- Connection Configuration
    connection_type VARCHAR(50) DEFAULT 'manual',
    _api_endpoint BYTEA,
    _api_key BYTEA,
    mqtt_broker VARCHAR(200),
    mqtt_port INTEGER DEFAULT 1883,
    mqtt_topic VARCHAR(200),
    mqtt_username VARCHAR(100),
    _mqtt_password BYTEA,
    mqtt_qos INTEGER DEFAULT 1,
    opcua_endpoint VARCHAR(500),
    opcua_namespace VARCHAR(200),
    modbus_host VARCHAR(200),
    modbus_port INTEGER DEFAULT 502,
    modbus_unit_id INTEGER,
    connection_config JSONB,
    
    -- Status
    status machine_status NOT NULL DEFAULT 'unknown',
    health_status health_status NOT NULL DEFAULT 'unknown',
    is_critical BOOLEAN DEFAULT FALSE,
    
    -- Sensor Readings (with CHECK constraints)
    temperature DECIMAL(8, 2) CHECK (temperature >= -100 AND temperature <= 500),
    temperature_unit VARCHAR(10) DEFAULT 'C',
    vibration DECIMAL(8, 2) CHECK (vibration >= 0),
    vibration_unit VARCHAR(20) DEFAULT 'mm/s',
    rpm DECIMAL(10, 2) CHECK (rpm >= 0),
    current DECIMAL(8, 2) CHECK (current >= 0),
    current_unit VARCHAR(10) DEFAULT 'A',
    pressure DECIMAL(8, 2) CHECK (pressure >= 0),
    pressure_unit VARCHAR(20) DEFAULT 'PSI',
    voltage DECIMAL(8, 2) CHECK (voltage >= 0),
    voltage_unit VARCHAR(10) DEFAULT 'V',
    power DECIMAL(10, 2) CHECK (power >= 0),
    power_unit VARCHAR(10) DEFAULT 'kW',
    efficiency DECIMAL(5, 2) CHECK (efficiency >= 0 AND efficiency <= 100),
    load DECIMAL(5, 2) CHECK (load >= 0 AND load <= 100),
    flow DECIMAL(10, 2) CHECK (flow >= 0),
    level DECIMAL(8, 2) CHECK (level >= 0),
    humidity DECIMAL(5, 2) CHECK (humidity >= 0 AND humidity <= 100),
    noise DECIMAL(8, 2) CHECK (noise >= 0),
    torque DECIMAL(10, 2) CHECK (torque >= 0),
    
    -- AI Embeddings
    machine_embedding VECTOR(768),
    
    -- Operating Statistics
    operational_hours DECIMAL(10, 2) DEFAULT 0,
    total_cycles BIGINT DEFAULT 0,
    last_reading_at TIMESTAMPTZ,
    
    -- Maintenance
    maintenance_interval_hours INTEGER DEFAULT 720,
    last_maintenance_at TIMESTAMPTZ,
    next_maintenance_at TIMESTAMPTZ,
    maintenance_notes TEXT,
    warranty_expires_at TIMESTAMPTZ,
    
    -- Calibration
    last_calibration_at TIMESTAMPTZ,
    calibration_due_at TIMESTAMPTZ,
    calibration_interval_days INTEGER DEFAULT 365,
    
    -- Alerts
    alert_thresholds JSONB,
    alert_enabled BOOLEAN DEFAULT TRUE,
    
    -- Performance
    performance_score DECIMAL(5, 2),
    reliability_score DECIMAL(5, 2),
    availability_score DECIMAL(5, 2),
    
    -- MTTR & MTBF
    mttr_hours DECIMAL(10, 2),
    mtbf_hours DECIMAL(10, 2),
    
    -- Tags & Metadata
    tags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_machines_org ON machines(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_status ON machines(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_health ON machines(health_status) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_serial ON machines(serial_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_next_maintenance ON machines(next_maintenance_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_type ON machines(machine_type) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_asset ON machines(asset_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_created ON machines(created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_critical ON machines(is_critical) WHERE deleted_at IS NULL;
CREATE INDEX idx_machines_embedding ON machines USING ivfflat (machine_embedding vector_cosine_ops);
CREATE UNIQUE INDEX uq_org_serial ON machines(organization_id, serial_number) WHERE deleted_at IS NULL;

-- Machine update trigger
CREATE TRIGGER trg_machines_updated
    BEFORE UPDATE ON machines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 16: MACHINE DATA TABLE (TimescaleDB)
-- ============================================================

CREATE TABLE machine_data (
    id UUID DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Sensor Readings
    temperature DECIMAL(8, 2),
    vibration DECIMAL(8, 2),
    rpm DECIMAL(10, 2),
    current DECIMAL(8, 2),
    pressure DECIMAL(8, 2),
    voltage DECIMAL(8, 2),
    power DECIMAL(10, 2),
    efficiency DECIMAL(5, 2),
    load DECIMAL(5, 2),
    flow DECIMAL(10, 2),
    level DECIMAL(8, 2),
    humidity DECIMAL(5, 2),
    noise DECIMAL(8, 2),
    torque DECIMAL(10, 2),
    
    -- Additional Sensors
    additional_sensors JSONB,
    
    -- Data Quality
    data_quality_score DECIMAL(3, 2),
    is_anomaly BOOLEAN DEFAULT FALSE,
    anomaly_score DECIMAL(5, 4),
    anomaly_reason TEXT,
    
    -- Ingestion Metadata
    ingested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ingestion_source VARCHAR(50),
    ingestion_batch_id UUID,
    is_duplicate BOOLEAN DEFAULT FALSE,
    
    PRIMARY KEY (id, timestamp)
);

-- Convert to TimescaleDB hypertable
SELECT create_hypertable('machine_data', 'timestamp', 
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Compression policy
ALTER TABLE machine_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'machine_id',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('machine_data', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('machine_data', INTERVAL '365 days', if_not_exists => TRUE);

-- Indexes
CREATE INDEX idx_machine_data_machine_time ON machine_data (machine_id, timestamp DESC);
CREATE INDEX idx_machine_data_timestamp ON machine_data (timestamp DESC);
CREATE INDEX idx_machine_data_anomaly ON machine_data (machine_id, is_anomaly) WHERE is_anomaly = TRUE;
CREATE INDEX idx_machine_data_org ON machine_data (organization_id);

-- ============================================================
-- PART 17: MACHINE DATA DAILY STATS
-- ============================================================

CREATE MATERIALIZED VIEW machine_data_daily_stats
WITH (timescaledb.continuous) AS
SELECT 
    machine_id,
    organization_id,
    time_bucket(INTERVAL '1 day', timestamp) AS day,
    AVG(temperature) AS avg_temperature,
    MAX(temperature) AS max_temperature,
    MIN(temperature) AS min_temperature,
    AVG(vibration) AS avg_vibration,
    MAX(vibration) AS max_vibration,
    AVG(pressure) AS avg_pressure,
    MAX(pressure) AS max_pressure,
    AVG(power) AS avg_power,
    MAX(power) AS max_power,
    AVG(efficiency) AS avg_efficiency,
    AVG(load) AS avg_load,
    COUNT(*) AS reading_count,
    SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) AS anomaly_count
FROM machine_data
GROUP BY machine_id, organization_id, day;

SELECT add_continuous_aggregate_policy('machine_data_daily_stats',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- ============================================================
-- PART 18: PREDICTIONS TABLE
-- ============================================================

CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Request Tracking
    request_id VARCHAR(100) NOT NULL,
    
    -- Prediction Results
    rul_value DECIMAL(10, 2) NOT NULL CHECK (rul_value >= 0),
    rul_unit VARCHAR(20) NOT NULL DEFAULT 'hours',
    confidence_score DECIMAL(5, 4) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
    prediction_status prediction_status NOT NULL DEFAULT 'pending',
    
    -- Confidence Intervals
    confidence_lower DECIMAL(10, 2),
    confidence_upper DECIMAL(10, 2),
    
    -- Risk Assessment
    risk_level VARCHAR(20) NOT NULL,
    risk_score DECIMAL(5, 4) CHECK (risk_score >= 0 AND risk_score <= 1),
    failure_probability DECIMAL(5, 4) CHECK (failure_probability >= 0 AND failure_probability <= 1),
    failure_mode VARCHAR(100),
    
    -- Model Information
    model_version VARCHAR(50) NOT NULL,
    model_type prediction_model_type NOT NULL,
    model_run_id VARCHAR(100),
    algorithm_details JSONB,
    
    -- AI Embeddings
    prediction_embedding VECTOR(768),
    
    -- Performance
    prediction_accuracy DECIMAL(5, 4),
    processing_time_ms INTEGER,
    inference_latency_ms DECIMAL(10, 2),
    
    -- Input Features
    input_data_hash VARCHAR(64),
    input_features JSONB,
    feature_importance JSONB,
    shap_values JSONB,
    explanation_text TEXT,
    drift_score DECIMAL(5, 4),
    
    -- Recommendations
    recommendations JSONB,
    recommended_actions TEXT,
    maintenance_priority VARCHAR(20),
    
    -- Alert
    alert_generated BOOLEAN DEFAULT FALSE,
    alert_id UUID,
    
    -- Anomaly Detection
    anomaly_detected BOOLEAN DEFAULT FALSE,
    anomaly_score DECIMAL(5, 4),
    anomaly_details JSONB,
    
    -- Validation
    is_validated BOOLEAN DEFAULT FALSE,
    validated_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    validated_at TIMESTAMPTZ,
    validation_notes TEXT,
    
    -- Feedback Loop
    actual_rul DECIMAL(10, 2),
    actual_failure_date TIMESTAMPTZ,
    prediction_error DECIMAL(10, 2),
    user_rating INTEGER CHECK (user_rating >= 1 AND user_rating <= 5),
    user_feedback TEXT,
    
    -- Color & Status
    color VARCHAR(20) DEFAULT '#28a745',
    severity VARCHAR(20) DEFAULT 'low',
    
    -- Horizon
    horizon INTEGER DEFAULT 30,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_predictions_machine ON predictions(machine_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_org ON predictions(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_status ON predictions(prediction_status) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_risk ON predictions(risk_level) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_created ON predictions(created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_model ON predictions(model_version) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_request ON predictions(request_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_severity ON predictions(severity) WHERE deleted_at IS NULL;
CREATE INDEX idx_predictions_embedding ON predictions USING ivfflat (prediction_embedding vector_cosine_ops);

-- Prediction update trigger
CREATE TRIGGER trg_predictions_updated
    BEFORE UPDATE ON predictions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 19: MODEL REGISTRY TABLE
-- ============================================================

CREATE TABLE model_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    model_id VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    model_type prediction_model_type NOT NULL,
    
    -- Model Artifacts
    model_path VARCHAR(500),
    model_checksum VARCHAR(64),
    model_signature VARCHAR(256),
    model_metadata JSONB DEFAULT '{}',
    
    -- AI Embeddings
    model_embedding VECTOR(768),
    
    -- Performance Metrics
    metrics JSONB DEFAULT '{}',
    validation_score DECIMAL(5, 4),
    test_score DECIMAL(5, 4),
    training_data_version VARCHAR(50),
    feature_version VARCHAR(50),
    
    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'staging',
    is_production BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Deployment
    deployed_at TIMESTAMPTZ,
    deployed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    deployment_strategy VARCHAR(50),
    canary_percentage INTEGER DEFAULT 0,
    
    -- Experiment Tracking
    experiment_id VARCHAR(100),
    run_id VARCHAR(100),
    
    -- Approval
    approved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    approval_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_model_registry_org ON model_registry(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_model_registry_status ON model_registry(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_model_registry_production ON model_registry(is_production) WHERE deleted_at IS NULL;
CREATE INDEX idx_model_registry_embedding ON model_registry USING ivfflat (model_embedding vector_cosine_ops);
CREATE UNIQUE INDEX uq_model_version ON model_registry(model_id, model_version) WHERE deleted_at IS NULL;

-- Model Registry update trigger
CREATE TRIGGER trg_model_registry_updated
    BEFORE UPDATE ON model_registry
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 20: DRIFT METRICS TABLE
-- ============================================================

CREATE TABLE drift_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    model_id UUID REFERENCES model_registry(id) ON DELETE CASCADE,
    machine_id UUID REFERENCES machines(id) ON DELETE CASCADE,
    
    drift_type VARCHAR(50) NOT NULL,
    drift_score DECIMAL(5, 4) NOT NULL,
    drift_threshold DECIMAL(5, 4),
    drift_detected BOOLEAN DEFAULT FALSE,
    severity VARCHAR(20),
    
    feature_drift JSONB DEFAULT '{}',
    affected_features TEXT[],
    
    detection_method VARCHAR(50),
    detection_window INTEGER,
    
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_drift_metrics_model ON drift_metrics(model_id);
CREATE INDEX idx_drift_metrics_machine ON drift_metrics(machine_id);
CREATE INDEX idx_drift_metrics_timestamp ON drift_metrics(timestamp DESC);

-- ============================================================
-- PART 21: FEATURE STORE TABLE
-- ============================================================

CREATE TABLE feature_store (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    feature_name VARCHAR(100) NOT NULL,
    feature_type VARCHAR(50) NOT NULL,
    feature_version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    feature_value JSONB NOT NULL,
    entity_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feature_name ON feature_store(feature_name);
CREATE INDEX idx_feature_entity ON feature_store(entity_id, entity_type);
CREATE INDEX idx_feature_timestamp ON feature_store(timestamp DESC);

-- ============================================================
-- PART 22: DATASET REGISTRY TABLE
-- ============================================================

CREATE TABLE dataset_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dataset_name VARCHAR(200) NOT NULL,
    dataset_version VARCHAR(50) NOT NULL,
    dataset_type VARCHAR(50) NOT NULL,
    dataset_path VARCHAR(500),
    dataset_checksum VARCHAR(64),
    dataset_size BIGINT,
    row_count BIGINT,
    column_count INTEGER,
    schema JSONB,
    metadata JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'active',
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dataset_name ON dataset_registry(dataset_name);
CREATE INDEX idx_dataset_version ON dataset_registry(dataset_version);
CREATE UNIQUE INDEX uq_dataset_version ON dataset_registry(dataset_name, dataset_version);

-- ============================================================
-- PART 23: TRAINING RUNS TABLE
-- ============================================================

CREATE TABLE training_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    model_id UUID REFERENCES model_registry(id) ON DELETE SET NULL,
    dataset_id UUID REFERENCES dataset_registry(id) ON DELETE SET NULL,
    run_name VARCHAR(200),
    run_id VARCHAR(100) NOT NULL UNIQUE,
    experiment_id VARCHAR(100),
    status VARCHAR(50) DEFAULT 'queued',
    
    hyperparameters JSONB,
    metrics JSONB,
    artifacts JSONB,
    logs JSONB,
    
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_training_model ON training_runs(model_id);
CREATE INDEX idx_training_dataset ON training_runs(dataset_id);
CREATE INDEX idx_training_status ON training_runs(status);

-- ============================================================
-- PART 24: ALERTS TABLE
-- ============================================================

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    machine_id UUID REFERENCES machines(id) ON DELETE CASCADE,
    prediction_id UUID REFERENCES predictions(id) ON DELETE SET NULL,
    
    -- Alert Details
    alert_type VARCHAR(50) NOT NULL,
    severity alert_severity NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    description TEXT,
    
    -- Deduplication
    dedup_key VARCHAR(255),
    dedup_count INTEGER DEFAULT 1,
    dedup_window_minutes INTEGER DEFAULT 60,
    
    -- Status
    alert_status alert_status NOT NULL DEFAULT 'active',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    is_suppressed BOOLEAN NOT NULL DEFAULT FALSE,
    suppress_reason TEXT,
    
    -- Acknowledgment
    acknowledged_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    acknowledged_at TIMESTAMPTZ,
    acknowledgment_notes TEXT,
    
    -- Resolution
    resolved_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    resolution_time_minutes INTEGER,
    
    -- Escalation
    is_escalated BOOLEAN DEFAULT FALSE,
    escalated_to_id UUID REFERENCES users(id) ON DELETE SET NULL,
    escalated_at TIMESTAMPTZ,
    escalation_level INTEGER DEFAULT 0,
    escalation_chain JSONB DEFAULT '[]',
    
    -- Incident
    incident_id VARCHAR(100),
    incident_link VARCHAR(500),
    
    -- Notification
    notification_channels JSONB DEFAULT '{}',
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_sent_at TIMESTAMPTZ,
    notification_failed BOOLEAN DEFAULT FALSE,
    notification_error TEXT,
    notification_retry_count INTEGER DEFAULT 0,
    
    -- Context
    context_data JSONB,
    threshold_config JSONB,
    sensor_values JSONB,
    cost_impact VARCHAR(50),
    action VARCHAR(500),
    recommendations JSONB DEFAULT '[]',
    
    -- SLA & Performance
    priority INTEGER DEFAULT 0,
    first_response_time INTEGER,
    resolution_duration INTEGER,
    sla_response_minutes INTEGER,
    sla_resolution_minutes INTEGER,
    sla_breached BOOLEAN DEFAULT FALSE,
    sla_breached_at TIMESTAMPTZ,
    
    -- Recurrence
    is_recurring BOOLEAN DEFAULT FALSE,
    recurrence_count INTEGER DEFAULT 1,
    first_occurred_at TIMESTAMPTZ,
    last_occurred_at TIMESTAMPTZ,
    
    -- MTTR & MTBF
    mttr_minutes INTEGER,
    mtbf_hours DECIMAL(10, 2),
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_alerts_org ON alerts(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_user ON alerts(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_machine ON alerts(machine_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_severity ON alerts(severity) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_status ON alerts(alert_status) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_read ON alerts(is_read) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_created ON alerts(created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_alerts_dedup ON alerts(dedup_key) WHERE deleted_at IS NULL;

-- Alert update trigger
CREATE TRIGGER trg_alerts_updated
    BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 25: AUDIT LOGS TABLE (Immutable + Partitions)
-- ============================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Action Details
    action audit_action NOT NULL,
    action_status VARCHAR(20) NOT NULL,
    action_description TEXT,
    
    -- Resource Details
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID,
    resource_name VARCHAR(200),
    resource_version INTEGER,
    
    -- Changes
    old_values JSONB,
    new_values JSONB,
    changed_fields JSONB,
    
    -- Request Context
    ip_address INET,
    user_agent TEXT,
    request_method VARCHAR(10),
    request_path VARCHAR(500),
    request_id UUID,
    correlation_id UUID,
    
    -- Response
    response_status INTEGER,
    error_message TEXT,
    error_stack TEXT,
    
    -- Security
    severity audit_severity NOT NULL DEFAULT 'medium',
    requires_review BOOLEAN DEFAULT FALSE,
    reviewed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,
    
    -- Cryptographic Signatures (Immutability)
    audit_hash VARCHAR(128) NOT NULL,
    previous_hash VARCHAR(128),
    signature VARCHAR(256),
    signed_by UUID,
    signed_at TIMESTAMPTZ,
    
    -- Compliance
    compliance_tags TEXT[] DEFAULT '{}',
    retention_until TIMESTAMPTZ,
    legal_hold BOOLEAN DEFAULT FALSE,
    evidence_id VARCHAR(100),
    
    -- Extra Data
    extra_data JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (created_at);

-- Audit partition trigger
CREATE TRIGGER trg_audit_update_protect
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_update();

-- Create audit partitions
CREATE TABLE audit_logs_2026
    PARTITION OF audit_logs
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE audit_logs_2027
    PARTITION OF audit_logs
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

CREATE TABLE audit_logs_2028
    PARTITION OF audit_logs
    FOR VALUES FROM ('2028-01-01') TO ('2029-01-01');

-- Indexes on audit_logs
CREATE INDEX idx_audit_org ON audit_logs(organization_id);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_hash ON audit_logs(audit_hash);

-- ============================================================
-- PART 26: MAINTENANCE RECORDS TABLE
-- ============================================================

CREATE TABLE maintenance_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    performed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    maintenance_type maintenance_type NOT NULL,
    maintenance_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL,
    
    cost DECIMAL(18, 2),
    duration_hours DECIMAL(10, 2),
    parts_replaced JSONB DEFAULT '[]',
    notes TEXT,
    
    was_scheduled BOOLEAN DEFAULT FALSE,
    next_maintenance_date TIMESTAMPTZ,
    status maintenance_status DEFAULT 'completed',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_maintenance_machine ON maintenance_records(machine_id);
CREATE INDEX idx_maintenance_type ON maintenance_records(maintenance_type);
CREATE INDEX idx_maintenance_date ON maintenance_records(maintenance_date);

-- Maintenance update trigger
CREATE TRIGGER trg_maintenance_updated
    BEFORE UPDATE ON maintenance_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 27: WORK ORDERS TABLE
-- ============================================================

CREATE TABLE work_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    machine_id UUID NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    assigned_to_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    priority work_order_priority NOT NULL DEFAULT 'medium',
    status work_order_status NOT NULL DEFAULT 'pending',
    work_order_number VARCHAR(50) NOT NULL UNIQUE,
    
    scheduled_start TIMESTAMPTZ,
    scheduled_end TIMESTAMPTZ,
    actual_start TIMESTAMPTZ,
    actual_end TIMESTAMPTZ,
    
    estimated_hours DECIMAL(10, 2),
    actual_hours DECIMAL(10, 2),
    parts_used JSONB DEFAULT '[]',
    
    cost_estimate DECIMAL(18, 2),
    cost_actual DECIMAL(18, 2),
    
    approval_status VARCHAR(20) DEFAULT 'pending',
    approved_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    
    completed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    completed_at TIMESTAMPTZ,
    completion_notes TEXT,
    
    attachments JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_work_order_org ON work_orders(organization_id);
CREATE INDEX idx_work_order_machine ON work_orders(machine_id);
CREATE INDEX idx_work_order_status ON work_orders(status);
CREATE INDEX idx_work_order_number ON work_orders(work_order_number);

-- Work Order update trigger
CREATE TRIGGER trg_work_orders_updated
    BEFORE UPDATE ON work_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 28: VENDORS TABLE
-- ============================================================

CREATE TABLE vendors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    name VARCHAR(200) NOT NULL,
    vendor_type VARCHAR(50),
    contact_name VARCHAR(200),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    address TEXT,
    tax_id VARCHAR(100),
    payment_terms VARCHAR(50),
    
    preferred_vendor BOOLEAN DEFAULT FALSE,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    notes TEXT,
    website VARCHAR(500),
    active BOOLEAN DEFAULT TRUE,
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vendor_org ON vendors(organization_id);
CREATE INDEX idx_vendor_name ON vendors(name);

-- Vendor update trigger
CREATE TRIGGER trg_vendors_updated
    BEFORE UPDATE ON vendors
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 29: SPARE PARTS TABLE
-- ============================================================

CREATE TABLE spare_parts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    vendor_id UUID REFERENCES vendors(id) ON DELETE SET NULL,
    
    part_number VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    manufacturer VARCHAR(100),
    compatible_machines TEXT[],
    
    quantity_in_stock INTEGER DEFAULT 0,
    reorder_level INTEGER DEFAULT 10,
    unit_cost DECIMAL(18, 2),
    selling_price DECIMAL(18, 2),
    location VARCHAR(200),
    
    last_ordered_at TIMESTAMPTZ,
    lead_time_days INTEGER DEFAULT 7,
    minimum_order_quantity INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_spare_part_org ON spare_parts(organization_id);
CREATE INDEX idx_spare_part_number ON spare_parts(part_number);
CREATE INDEX idx_spare_part_name ON spare_parts(name);

-- Spare Parts update trigger
CREATE TRIGGER trg_spare_parts_updated
    BEFORE UPDATE ON spare_parts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 30: PAYMENTS TABLE
-- ============================================================

CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    invoice_id UUID,
    
    amount DECIMAL(18, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status payment_status NOT NULL DEFAULT 'pending',
    payment_method VARCHAR(50),
    provider payment_provider,
    period VARCHAR(20) DEFAULT 'monthly',
    
    _provider_payment_id BYTEA,
    _provider_customer_id BYTEA,
    _provider_subscription_id BYTEA,
    provider_event_id VARCHAR(255),
    webhook_verified BOOLEAN DEFAULT FALSE,
    webhook_payload JSONB,
    signature VARCHAR(255),
    
    paid_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    refund_amount DECIMAL(18, 2),
    
    failure_reason TEXT,
    failure_code VARCHAR(50),
    
    idempotency_key VARCHAR(255) UNIQUE,
    receipt_url VARCHAR(500),
    
    extra_data JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_payment_org ON payments(organization_id);
CREATE INDEX idx_payment_user ON payments(user_id);
CREATE INDEX idx_payment_status ON payments(status);
CREATE INDEX idx_payment_invoice ON payments(invoice_id);
CREATE INDEX idx_payment_provider ON payments(provider);
CREATE UNIQUE INDEX uq_payment_provider_id ON payments(_provider_payment_id);

-- Payment update trigger
CREATE TRIGGER trg_payments_updated
    BEFORE UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 31: INVOICES TABLE
-- ============================================================

CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
    
    invoice_number VARCHAR(50) NOT NULL UNIQUE,
    status invoice_status NOT NULL DEFAULT 'draft',
    
    amount DECIMAL(18, 2) NOT NULL,
    tax DECIMAL(18, 2) NOT NULL DEFAULT 0.0,
    tax_rate DECIMAL(5, 2) NOT NULL DEFAULT 0.0,
    discount DECIMAL(18, 2) NOT NULL DEFAULT 0.0,
    total DECIMAL(18, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    
    issued_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    
    billing_address JSONB,
    shipping_address JSONB,
    items JSONB DEFAULT '[]',
    
    payment_id UUID,
    payment_method VARCHAR(50),
    
    notes TEXT,
    terms TEXT,
    
    extra_data JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_inv_org ON invoices(organization_id);
CREATE INDEX idx_inv_status ON invoices(status);
CREATE INDEX idx_inv_number ON invoices(invoice_number);
CREATE INDEX idx_inv_date ON invoices(issued_at);

-- Invoice update trigger
CREATE TRIGGER trg_invoices_updated
    BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 32: SUBSCRIPTIONS TABLE
-- ============================================================

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    plan_id VARCHAR(100) NOT NULL,
    plan_name VARCHAR(100) NOT NULL,
    status subscription_status NOT NULL DEFAULT 'trial',
    
    _provider_subscription_id BYTEA,
    _provider_customer_id BYTEA,
    
    trial_started_at TIMESTAMPTZ,
    trial_ends_at TIMESTAMPTZ,
    current_period_started_at TIMESTAMPTZ,
    current_period_ends_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    
    billing_cycle billing_cycle NOT NULL DEFAULT 'monthly',
    amount DECIMAL(18, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    
    auto_renew BOOLEAN DEFAULT TRUE,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    grace_period_end TIMESTAMPTZ,
    
    features JSONB DEFAULT '{}',
    limits JSONB DEFAULT '{}',
    extra_data JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_sub_org ON subscriptions(organization_id);
CREATE INDEX idx_sub_user ON subscriptions(user_id);
CREATE INDEX idx_sub_status ON subscriptions(status);
CREATE INDEX idx_sub_plan ON subscriptions(plan_id);
CREATE INDEX idx_sub_expiry ON subscriptions(current_period_ends_at);
CREATE UNIQUE INDEX uq_sub_provider_id ON subscriptions(_provider_subscription_id);

-- Subscription update trigger
CREATE TRIGGER trg_subscriptions_updated
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 33: USAGE METERING TABLE
-- ============================================================

CREATE TABLE usage_metering (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
    
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(18, 6) NOT NULL,
    unit VARCHAR(50),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usage_org ON usage_metering(organization_id);
CREATE INDEX idx_usage_subscription ON usage_metering(subscription_id);
CREATE INDEX idx_usage_metric ON usage_metering(metric_name);
CREATE INDEX idx_usage_timestamp ON usage_metering(timestamp DESC);

-- ============================================================
-- PART 34: COUPONS TABLE
-- ============================================================

CREATE TABLE coupons (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    coupon_code VARCHAR(50) NOT NULL UNIQUE,
    discount_type VARCHAR(20) NOT NULL,
    discount_value DECIMAL(18, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    max_uses_per_user INTEGER DEFAULT 1,
    
    applies_to JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_coupon_code ON coupons(coupon_code);
CREATE INDEX idx_coupon_valid ON coupons(valid_from, valid_until);

-- ============================================================
-- PART 35: CREDITS TABLE
-- ============================================================

CREATE TABLE credits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    credit_type VARCHAR(50) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    used_amount DECIMAL(18, 2) DEFAULT 0,
    
    expires_at TIMESTAMPTZ,
    source VARCHAR(100),
    source_id UUID,
    
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_credits_org ON credits(organization_id);
CREATE INDEX idx_credits_user ON credits(user_id);
CREATE INDEX idx_credits_expires ON credits(expires_at);

-- ============================================================
-- PART 36: SOFTWARE DOWNLOADS TABLE
-- ============================================================

CREATE TABLE software_downloads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uuid VARCHAR(36) UNIQUE NOT NULL DEFAULT uuid_generate_v4()::TEXT,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    platform download_platform NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '7.0.0',
    file_name VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    file_checksum VARCHAR(64),
    file_hash_type VARCHAR(20),
    
    status download_status NOT NULL DEFAULT 'pending',
    download_url VARCHAR(500),
    
    -- Network
    ip_address INET,
    user_agent VARCHAR(500),
    referer VARCHAR(500),
    session_id VARCHAR(100),
    connection_speed DECIMAL(10, 2),
    network_type VARCHAR(50),
    
    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ,
    resumed_at TIMESTAMPTZ,
    
    -- Failure Handling
    failure_reason TEXT,
    failure_code VARCHAR(50),
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    max_retries INTEGER DEFAULT 3,
    
    -- Analytics
    download_count INTEGER DEFAULT 1,
    download_duration_ms INTEGER,
    download_speed_mbps FLOAT,
    download_progress FLOAT,
    bandwidth_usage FLOAT,
    
    -- Geography
    geo_location JSONB,
    timezone VARCHAR(50),
    country VARCHAR(2),
    region VARCHAR(100),
    city VARCHAR(100),
    
    -- Device
    device_info JSONB,
    app_version VARCHAR(50),
    os_version VARCHAR(50),
    device_model VARCHAR(100),
    screen_size VARCHAR(50),
    
    -- Marketing
    campaign_id VARCHAR(100),
    source VARCHAR(100),
    medium VARCHAR(100),
    
    -- Additional
    extra_data JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_download_user ON software_downloads(user_id);
CREATE INDEX idx_download_org ON software_downloads(organization_id);
CREATE INDEX idx_download_platform ON software_downloads(platform);
CREATE INDEX idx_download_status ON software_downloads(status);
CREATE INDEX idx_download_timestamp ON software_downloads(created_at);
CREATE INDEX idx_download_ip ON software_downloads(ip_address);

-- Download update trigger
CREATE TRIGGER trg_downloads_updated
    BEFORE UPDATE ON software_downloads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 37: NOTIFICATIONS TABLE
-- ============================================================

CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    type notification_type NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    
    priority INTEGER DEFAULT 0,
    link VARCHAR(500),
    
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notification_user ON notifications(user_id);
CREATE INDEX idx_notification_read ON notifications(is_read);
CREATE INDEX idx_notification_created ON notifications(created_at DESC);

-- Notification update trigger
CREATE TRIGGER trg_notifications_updated
    BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 38: BACKGROUND JOBS TABLE
-- ============================================================

CREATE TABLE background_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    job_type VARCHAR(50) NOT NULL,
    job_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    
    queue_name VARCHAR(50) DEFAULT 'default',
    worker_name VARCHAR(100),
    heartbeat TIMESTAMPTZ,
    lease_timeout INTEGER DEFAULT 300,
    
    payload JSONB NOT NULL,
    result JSONB,
    error TEXT,
    
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    scheduled_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_job_status ON background_jobs(job_status);
CREATE INDEX idx_job_type ON background_jobs(job_type);
CREATE INDEX idx_job_scheduled ON background_jobs(scheduled_at);
CREATE INDEX idx_job_queue ON background_jobs(queue_name);

-- Background Job update trigger
CREATE TRIGGER trg_background_jobs_updated
    BEFORE UPDATE ON background_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 39: FEATURE FLAGS TABLE
-- ============================================================

CREATE TABLE feature_flags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    
    flag_name VARCHAR(100) NOT NULL,
    flag_type feature_flag_type DEFAULT 'boolean',
    flag_value BOOLEAN DEFAULT FALSE,
    flag_metadata JSONB DEFAULT '{}',
    
    enabled_for_all BOOLEAN DEFAULT FALSE,
    percentage_enabled INTEGER DEFAULT 0,
    user_segments TEXT[],
    environments TEXT[] DEFAULT '{"production"}',
    
    rollout_strategy VARCHAR(50),
    sticky_session BOOLEAN DEFAULT FALSE,
    target_groups TEXT[],
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feature_flag_name ON feature_flags(flag_name);
CREATE UNIQUE INDEX uq_feature_flag_org ON feature_flags(organization_id, flag_name);

-- Feature Flag update trigger
CREATE TRIGGER trg_feature_flags_updated
    BEFORE UPDATE ON feature_flags
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 40: SYSTEM CONFIG TABLE
-- ============================================================

CREATE TABLE system_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    data_type VARCHAR(20) NOT NULL DEFAULT 'string',
    description TEXT,
    category VARCHAR(50),
    is_sensitive BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- System Config update trigger
CREATE TRIGGER trg_system_configs_updated
    BEFORE UPDATE ON system_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- PART 41: WEBHOOKS TABLE
-- ============================================================

CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    webhook_url VARCHAR(500) NOT NULL,
    webhook_secret VARCHAR(255),
    event_types TEXT[] NOT NULL,
    
    is_active BOOLEAN DEFAULT TRUE,
    retry_count INTEGER DEFAULT 3,
    timeout_seconds INTEGER DEFAULT 10,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_webhook_org ON webhooks(organization_id);

-- ============================================================
-- PART 42: WEBHOOK EVENTS TABLE
-- ============================================================

CREATE TABLE webhook_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    webhook_id UUID REFERENCES webhooks(id) ON DELETE CASCADE,
    
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    delivered BOOLEAN DEFAULT FALSE,
    delivered_at TIMESTAMPTZ,
    delivery_count INTEGER DEFAULT 0,
    
    response_status INTEGER,
    response_body TEXT,
    error_message TEXT,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_webhook_events_org ON webhook_events(organization_id);
CREATE INDEX idx_webhook_events_webhook ON webhook_events(webhook_id);
CREATE INDEX idx_webhook_events_delivered ON webhook_events(delivered);

-- ============================================================
-- PART 43: AI CHAT SESSIONS TABLE
-- ============================================================

CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    title VARCHAR(200),
    context JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_chat_session_user ON chat_sessions(user_id);
CREATE INDEX idx_chat_session_org ON chat_sessions(organization_id);

-- ============================================================
-- PART 44: AI CHAT MESSAGES TABLE
-- ============================================================

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768),
    tokens INTEGER,
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_message_session ON chat_messages(session_id);
CREATE INDEX idx_chat_message_created ON chat_messages(created_at);
CREATE INDEX idx_chat_message_embedding ON chat_messages USING ivfflat (embedding vector_cosine_ops);

-- ============================================================
-- PART 45: KNOWLEDGE BASE TABLE
-- ============================================================

CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(100),
    tags TEXT[],
    
    embedding VECTOR(768),
    metadata JSONB DEFAULT '{}',
    
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_knowledge_org ON knowledge_base(organization_id);
CREATE INDEX idx_knowledge_category ON knowledge_base(category);
CREATE INDEX idx_knowledge_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops);

-- ============================================================
-- PART 46: RAG DOCUMENTS TABLE
-- ============================================================

CREATE TABLE rag_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    
    document_name VARCHAR(500) NOT NULL,
    document_type VARCHAR(50),
    content TEXT NOT NULL,
    chunk_index INTEGER,
    chunk_text TEXT,
    
    embedding VECTOR(768),
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rag_org ON rag_documents(organization_id);
CREATE INDEX idx_rag_document ON rag_documents(document_name);
CREATE INDEX idx_rag_embedding ON rag_documents USING ivfflat (embedding vector_cosine_ops);

-- ============================================================
-- PART 47: SCHEMA VERSION TABLE
-- ============================================================

CREATE TABLE schema_version (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version VARCHAR(20) NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_by VARCHAR(100),
    description TEXT,
    scripts_applied TEXT[],
    checksum VARCHAR(64),
    status VARCHAR(50) DEFAULT 'success'
);

INSERT INTO schema_version (version, description, applied_by, checksum)
VALUES ('6.0.0', 'Complete Enterprise Release - All Features Included', 'system', 
    encode(digest('schema_v6.0.0', 'sha256'), 'hex'));

-- ============================================================
-- PART 48: ADD FOREIGN KEY CONSTRAINTS (Post-Invoice)
-- ============================================================

-- Add payment-invoice foreign key
ALTER TABLE payments
ADD CONSTRAINT fk_payment_invoice
FOREIGN KEY (invoice_id)
REFERENCES invoices(id)
ON DELETE SET NULL;

ALTER TABLE invoices
ADD CONSTRAINT fk_invoice_payment
FOREIGN KEY (payment_id)
REFERENCES payments(id)
ON DELETE SET NULL;

-- ============================================================
-- PART 49: ROW LEVEL SECURITY POLICIES
-- ============================================================

-- Enable RLS on all tenant tables
DO $$ 
DECLARE 
    table_name text;
BEGIN
    FOR table_name IN 
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename IN (
            'organizations', 'users', 'user_sessions', 'oauth_accounts',
            'api_keys', 'security_events', 'machines', 'machine_data',
            'predictions', 'model_registry', 'drift_metrics', 'alerts',
            'audit_logs', 'maintenance_records', 'work_orders', 'vendors',
            'spare_parts', 'software_downloads', 'payments', 'subscriptions',
            'invoices', 'notifications', 'background_jobs', 'feature_flags',
            'webhooks', 'webhook_events', 'chat_sessions', 'chat_messages',
            'knowledge_base', 'rag_documents', 'coupons', 'credits',
            'usage_metering', 'feature_store', 'dataset_registry', 'training_runs'
        )
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    END LOOP;
END $$;

-- Organization policies
CREATE POLICY org_tenant_policy ON organizations
    USING (id::TEXT = current_setting('app.organization_id', TRUE));

CREATE POLICY org_admin_policy ON organizations
    USING (current_setting('app.user_role', TRUE) = 'super_admin');

-- User policies
CREATE POLICY users_org_policy ON users
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

CREATE POLICY users_admin_policy ON users
    USING (current_setting('app.user_role', TRUE) IN ('super_admin', 'org_admin'));

-- Machine policies
CREATE POLICY machines_org_policy ON machines
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Machine Data policies
CREATE POLICY machine_data_org_policy ON machine_data
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Prediction policies
CREATE POLICY predictions_org_policy ON predictions
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Alert policies
CREATE POLICY alerts_org_policy ON alerts
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Payment policies
CREATE POLICY payments_org_policy ON payments
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Subscription policies
CREATE POLICY subscriptions_org_policy ON subscriptions
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Invoice policies
CREATE POLICY invoices_org_policy ON invoices
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Audit logs: Super admin can see all
CREATE POLICY audit_org_policy ON audit_logs
    USING (
        organization_id::TEXT = current_setting('app.organization_id', TRUE) 
        OR current_setting('app.user_role', TRUE) = 'super_admin'
    );

-- API Key policies
CREATE POLICY apikey_org_policy ON api_keys
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Work Order policies
CREATE POLICY workorder_org_policy ON work_orders
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Maintenance policies
CREATE POLICY maintenance_org_policy ON maintenance_records
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Vendor policies
CREATE POLICY vendor_org_policy ON vendors
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Spare Parts policies
CREATE POLICY spareparts_org_policy ON spare_parts
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Software Download policies
CREATE POLICY download_org_policy ON software_downloads
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Notification policies
CREATE POLICY notification_org_policy ON notifications
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Chat policies
CREATE POLICY chat_org_policy ON chat_sessions
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Knowledge Base policies
CREATE POLICY knowledge_org_policy ON knowledge_base
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- RAG Document policies
CREATE POLICY rag_org_policy ON rag_documents
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- Webhook policies
CREATE POLICY webhook_org_policy ON webhooks
    USING (organization_id::TEXT = current_setting('app.organization_id', TRUE));

-- ============================================================
-- PART 50: VALIDATION QUERIES
-- ============================================================

-- Check all tables exist
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- Check RLS is enabled
SELECT schemaname, tablename, policyname 
FROM pg_policies 
WHERE schemaname = 'public' 
ORDER BY tablename, policyname;

-- Check extensions
SELECT extname, extversion FROM pg_extension 
WHERE extname IN ('uuid-ossp', 'pgcrypto', 'timescaledb', 'postgis', 'pg_stat_statements', 'vector', 'citext');

-- Check partitions
SELECT schemaname, tablename, tableowner 
FROM pg_tables 
WHERE tablename LIKE 'audit_logs_%' 
ORDER BY tablename;

-- Check triggers
SELECT tgname, tgrelid::regclass, tgtype 
FROM pg_trigger 
WHERE tgname LIKE 'trg_%' 
ORDER BY tgname;

-- ============================================================
-- PART 51: DATABASE COMMENTS
-- ============================================================

COMMENT ON DATABASE synapsepm IS 'SynapsePM - Enterprise Predictive Maintenance Platform v6.0 - Complete Feature Set';

COMMENT ON TABLE organizations IS 'Multi-tenant organizations with enterprise security and compliance';
COMMENT ON TABLE users IS 'User accounts with MFA, SSO, RBAC, and comprehensive security features';
COMMENT ON TABLE user_password_history IS 'Immutable password history for security compliance';
COMMENT ON TABLE user_sessions IS 'User session management with refresh tokens and device tracking';
COMMENT ON TABLE oauth_accounts IS 'OAuth/Social login accounts (Google, GitHub, etc.)';
COMMENT ON TABLE password_reset_tokens IS 'Password reset tokens with secure hashing';
COMMENT ON TABLE email_verification_tokens IS 'Email verification tokens with secure hashing';
COMMENT ON TABLE invitations IS 'User invitations to organizations with role assignment';
COMMENT ON TABLE security_events IS 'Security event tracking for threat detection and compliance';
COMMENT ON TABLE api_keys IS 'API key management with secure hashing and RBAC';
COMMENT ON TABLE machines IS 'Industrial machines with sensor validation, calibration, and AI embeddings';
COMMENT ON TABLE machine_data IS 'Time-series sensor data with TimescaleDB compression and retention';
COMMENT ON TABLE machine_data_daily_stats IS 'Daily aggregated statistics for machine performance monitoring';
COMMENT ON TABLE predictions IS 'RUL predictions with ML lineage, explainability, and ensemble support';
COMMENT ON TABLE model_registry IS 'MLOps model registry with versioning, deployment, and experiment tracking';
COMMENT ON TABLE drift_metrics IS 'Data, concept, and feature drift monitoring for ML models';
COMMENT ON TABLE feature_store IS 'Feature store for ML model training and serving';
COMMENT ON TABLE dataset_registry IS 'Dataset versioning and management for ML workflows';
COMMENT ON TABLE training_runs IS 'ML training run tracking with hyperparameters and metrics';
COMMENT ON TABLE alerts IS 'Alert system with deduplication, escalation, SLA tracking, and notifications';
COMMENT ON TABLE audit_logs IS 'Immutable audit trail with cryptographic signatures and partitioning';
COMMENT ON TABLE maintenance_records IS 'Maintenance history tracking with parts and cost tracking';
COMMENT ON TABLE work_orders IS 'Work order management with approvals, scheduling, and cost tracking';
COMMENT ON TABLE vendors IS 'Vendor management for parts and services procurement';
COMMENT ON TABLE spare_parts IS 'Inventory management for spare parts with reorder tracking';
COMMENT ON TABLE software_downloads IS 'Complete software download tracking with analytics and geo-location';
COMMENT ON TABLE payments IS 'Payment processing with multi-provider support (Stripe, Razorpay, PayPal, Paddle, Nepal Banks)';
COMMENT ON TABLE subscriptions IS 'Subscription management with billing cycles, trial, and grace period';
COMMENT ON TABLE usage_metering IS 'Usage metering for consumption-based billing';
COMMENT ON TABLE coupons IS 'Discount coupons for subscriptions and payments';
COMMENT ON TABLE credits IS 'Credit management for customer accounts';
COMMENT ON TABLE invoices IS 'Invoice generation and billing with tax and discount support';
COMMENT ON TABLE webhooks IS 'Webhook configuration for event notifications';
COMMENT ON TABLE webhook_events IS 'Webhook event delivery tracking';
COMMENT ON TABLE notifications IS 'User notifications with read tracking and priority levels';
COMMENT ON TABLE background_jobs IS 'Background job queue for async processing with retry support';
COMMENT ON TABLE feature_flags IS 'Feature flags for progressive rollouts and A/B testing';
COMMENT ON TABLE system_configs IS 'System configuration with sensitive data encryption';
COMMENT ON TABLE chat_sessions IS 'AI chat sessions for conversational AI';
COMMENT ON TABLE chat_messages IS 'AI chat messages with embeddings for semantic search';
COMMENT ON TABLE knowledge_base IS 'Knowledge base for organizational documentation';
COMMENT ON TABLE rag_documents IS 'RAG (Retrieval-Augmented Generation) documents with embeddings';
COMMENT ON TABLE encryption_keys IS 'Encryption key management with rotation and KMS support';

-- ============================================================
-- SCHEMA COMPLETED
-- ============================================================

SELECT '✅ Schema v6.0 Complete - All Features Included Successfully!' AS status;
SELECT '📊 Total Tables: ' || COUNT(*) FROM pg_tables WHERE schemaname = 'public';
SELECT '🔒 RLS Enabled Tables: ' || COUNT(DISTINCT tablename) FROM pg_policies WHERE schemaname = 'public';
SELECT '📦 Total Views: ' || COUNT(*) FROM pg_views WHERE schemaname = 'public';
SELECT '⚡ Total Triggers: ' || COUNT(*) FROM pg_trigger WHERE tgname LIKE 'trg_%';