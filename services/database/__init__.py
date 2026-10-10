"""
SYNAPPM - DATABASE MODELS INIT
Export all models and repositories
"""

from models.base import (
    Base, BaseModel, BaseRepository, encryption_service,
    UserRole, UserStatus, OrganizationStatus, MachineStatus,
    HealthStatus, AlertSeverity, AlertStatus, PaymentStatus,
    SubscriptionStatus, InvoiceStatus, PredictionStatus,
    DownloadPlatform, DownloadStatus, AuditAction
)

from models.models import (
    Organization, User, APIKey, Machine, MachineData,
    Prediction, Alert, SoftwareDownload, Payment,
    Subscription, Invoice, SecurityEvent, AuditLog,
    UserRepository, MachineRepository, DownloadRepository
)

__all__ = [
    # Base
    'Base', 'BaseModel', 'BaseRepository', 'encryption_service',
    
    # Enums
    'UserRole', 'UserStatus', 'OrganizationStatus', 'MachineStatus',
    'HealthStatus', 'AlertSeverity', 'AlertStatus', 'PaymentStatus',
    'SubscriptionStatus', 'InvoiceStatus', 'PredictionStatus',
    'DownloadPlatform', 'DownloadStatus', 'AuditAction',
    
    # Models
    'Organization', 'User', 'APIKey', 'Machine', 'MachineData',
    'Prediction', 'Alert', 'SoftwareDownload', 'Payment',
    'Subscription', 'Invoice', 'SecurityEvent', 'AuditLog',
    
    # Repositories
    'UserRepository', 'MachineRepository', 'DownloadRepository'
]

__version__ = '5.2.1'