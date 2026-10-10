"""
SynapsePM - Queries Package
Export all query modules
"""

from .analytics_queries import *
from .reporting_queries import *

__all__ = [
    # Analytics
    'get_machine_health_trend',
    'get_prediction_accuracy_trend',
    'get_organization_growth',
    'get_sensor_data_analysis',
    'get_alert_patterns',
    
    # Reporting
    'generate_daily_report',
    'generate_weekly_report',
    'generate_monthly_report',
    'export_machine_data',
    'get_compliance_report'
]

"""
SynapsePM - Database Queries Package
Export all query functions for easy importing
"""

from .analytics_queries import (
    get_machine_health_trend,
    get_prediction_accuracy_trend,
    get_organization_growth,
    get_sensor_data_analysis,
    get_alert_patterns,
    get_dashboard_summary,
    get_organization_statistics,
    get_machine_performance_metrics,
    get_alert_trends,
    get_user_activity_summary
)

__all__ = [
    'get_machine_health_trend',
    'get_prediction_accuracy_trend',
    'get_organization_growth',
    'get_sensor_data_analysis',
    'get_alert_patterns',
    'get_dashboard_summary',
    'get_organization_statistics',
    'get_machine_performance_metrics',
    'get_alert_trends',
    'get_user_activity_summary'
]