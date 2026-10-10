"""
SynapsePM - Routes Package
Export all route blueprints
"""

from . import auth_routes
from . import user_routes
from . import machine_routes
from . import prediction_routes
from . import alert_routes
from . import admin_routes
from . import webhook_routes

__all__ = [
    'auth_routes',
    'user_routes',
    'machine_routes',
    'prediction_routes',
    'alert_routes',
    'admin_routes',
    'webhook_routes'
]