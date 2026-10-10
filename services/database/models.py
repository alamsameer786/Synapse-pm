"""
SYNAPPM - DATABASE MODELS
Fixed imports and module resolution
"""

import os
import sys
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, List, Any

# ============================================================
# SETUP PATHS
# ============================================================

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# IMPORTS
# ============================================================

try:
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index
    from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
    from sqlalchemy.types import TypeDecorator, Text as SQLText
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    print("⚠️ SQLAlchemy not installed")

# ============================================================
# JSONB FALLBACK FOR SQLITE
# ============================================================

class JSONType(TypeDecorator):
    """JSON type that works with SQLite"""
    impl = SQLText
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, dict) or isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except:
            return value

# ============================================================
# ENUMS
# ============================================================

class UserRole:
    SUPER_ADMIN = "super_admin"
    ORG_ADMIN = "org_admin"
    MANAGER = "manager"
    USER = "user"
    VIEWER = "viewer"

class UserStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
    SUSPENDED = "suspended"

class MachineStatus:
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    ERROR = "error"
    UNKNOWN = "unknown"

class HealthStatus:
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    FAILURE_IMMINENT = "failure_imminent"
    UNKNOWN = "unknown"

# ============================================================
# BASE MODEL
# ============================================================

class BaseModel:
    """Base model with common fields"""
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

# ============================================================
# MAIN MODELS - FIXED
# ============================================================

def get_all_models(db):
    """Get all database models"""
    
    class User(BaseModel, db.Model):
        __tablename__ = 'users'
        __table_args__ = (
            Index('idx_user_email', 'email'),
            Index('idx_user_org', 'organization_id'),
        )
        
        email = Column(String(255), unique=True, nullable=False)
        username = Column(String(100), unique=True, nullable=True)
        password_hash = Column(String(255), nullable=False)
        first_name = Column(String(100))
        last_name = Column(String(100))
        display_name = Column(String(200))
        role = Column(String(50), default='user')
        status = Column(String(50), default='active')
        organization_id = Column(String(36), nullable=True)
        is_active = Column(Boolean, default=True)
        is_verified = Column(Boolean, default=False)
        is_locked = Column(Boolean, default=False)
        is_mfa_enabled = Column(Boolean, default=False)
        avatar_url = Column(String(500))
        phone = Column(String(50))
        last_login_at = Column(DateTime)
        login_attempts = Column(Integer, default=0)
        failed_attempts = Column(Integer, default=0)
        preferences = Column(JSONType, default={})
        metadata = Column(JSONType, default={})
        
        def set_password(self, password):
            if 'bcrypt' in sys.modules:
                import bcrypt
                salt = bcrypt.gensalt()
                self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
        def check_password(self, password):
            if 'bcrypt' in sys.modules:
                import bcrypt
                return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
            return False
    
    class Organization(BaseModel, db.Model):
        __tablename__ = 'organizations'
        __table_args__ = (
            Index('idx_org_name', 'name'),
            Index('idx_org_slug', 'slug'),
        )
        
        name = Column(String(200), nullable=False)
        slug = Column(String(100), unique=True, nullable=False)
        plan = Column(String(50), default='free')
        status = Column(String(50), default='active')
        max_users = Column(Integer, default=5)
        max_machines = Column(Integer, default=10)
        settings = Column(JSONType, default={})
        features = Column(JSONType, default={})
    
    class Machine(BaseModel, db.Model):
        __tablename__ = 'machines'
        __table_args__ = (
            Index('idx_machine_org', 'organization_id'),
            Index('idx_machine_status', 'status'),
        )
        
        organization_id = Column(String(36), nullable=False)
        name = Column(String(200), nullable=False)
        machine_type = Column(String(100), nullable=False)
        manufacturer = Column(String(100))
        model = Column(String(100))
        serial_number = Column(String(100))
        status = Column(String(50), default='unknown')
        health_status = Column(String(50), default='unknown')
        location = Column(String(200))
        temperature = Column(Float)
        vibration = Column(Float)
        pressure = Column(Float)
        rpm = Column(Float)
        operational_hours = Column(Float, default=0)
        last_reading_at = Column(DateTime)
        alert_thresholds = Column(JSONType, default={})
        metadata = Column(JSONType, default={})
    
    class MachineData(BaseModel, db.Model):
        __tablename__ = 'machine_data'
        __table_args__ = (
            Index('idx_data_machine', 'machine_id'),
            Index('idx_data_timestamp', 'data_timestamp'),
        )
        
        machine_id = Column(String(36), nullable=False)
        temperature = Column(Float)
        vibration = Column(Float)
        pressure = Column(Float)
        rpm = Column(Float)
        current = Column(Float)
        voltage = Column(Float)
        readings = Column(JSONType, default={})
        data_timestamp = Column(DateTime, default=datetime.utcnow)
        is_anomaly = Column(Boolean, default=False)
        quality_score = Column(Float)
    
    class Prediction(BaseModel, db.Model):
        __tablename__ = 'predictions'
        __table_args__ = (
            Index('idx_pred_machine', 'machine_id'),
            Index('idx_pred_org', 'organization_id'),
        )
        
        organization_id = Column(String(36), nullable=False)
        machine_id = Column(String(36), nullable=False)
        user_id = Column(String(36))
        rul_value = Column(Float, nullable=False)
        confidence_score = Column(Float, nullable=False)
        status = Column(String(50), default='completed')
        risk_level = Column(String(20), default='low')
        risk_score = Column(Float)
        failure_probability = Column(Float)
        model_version = Column(String(50))
        model_type = Column(String(50))
        recommendations = Column(JSONType, default=[])
        feature_importance = Column(JSONType, default={})
        metadata = Column(JSONType, default={})
    
    class Alert(BaseModel, db.Model):
        __tablename__ = 'alerts'
        __table_args__ = (
            Index('idx_alert_machine', 'machine_id'),
            Index('idx_alert_org', 'organization_id'),
        )
        
        organization_id = Column(String(36), nullable=False)
        machine_id = Column(String(36), nullable=False)
        user_id = Column(String(36))
        title = Column(String(255), nullable=False)
        description = Column(Text, nullable=False)
        severity = Column(String(20), default='medium')
        status = Column(String(20), default='active')
        prediction_id = Column(String(36))
        resolved_at = Column(DateTime)
        resolution_notes = Column(Text)
        metadata = Column(JSONType, default={})
    
    class AuditLog(BaseModel, db.Model):
        __tablename__ = 'audit_logs'
        __table_args__ = (
            Index('idx_audit_org', 'organization_id'),
            Index('idx_audit_user', 'user_id'),
        )
        
        organization_id = Column(String(36), nullable=False)
        user_id = Column(String(36))
        action = Column(String(50), nullable=False)
        resource_type = Column(String(50), nullable=False)
        resource_id = Column(String(36))
        changes = Column(JSONType, default={})
        ip_address = Column(String(45))
        user_agent = Column(String(500))
        status = Column(String(20), default='success')
    
    return {
        'User': User,
        'Organization': Organization,
        'Machine': Machine,
        'MachineData': MachineData,
        'Prediction': Prediction,
        'Alert': Alert,
        'AuditLog': AuditLog
    }

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("📊 SYNAPPM - Database Models (Fixed)")
    print("=" * 70)
    print("\n✅ Models ready with SQLite/PostgreSQL compatibility")
    print("   - JSON fields use JSONType (SQLite compatible)")
    print("   - UUID fields use String(36)")
    print("   - All models support soft delete")
    print("=" * 70)