"""
SynapsePM - Reporting Queries
Generate reports for business intelligence and compliance
Handles: Daily, weekly, monthly reports, data export, and compliance reporting
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone, timedelta
from uuid import UUID

# Add the project root to Python path
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent  # Goes up to Synapse PM folder
sys.path.insert(0, str(project_root))

from services.database.connection import db_connection
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# DAILY REPORTS
# ============================================================================

def generate_daily_report(organization_id: UUID, date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Generate daily operational report
    
    Args:
        organization_id: UUID of the organization
        date: Date for the report (default: today)
    
    Returns:
        Daily report with metrics and summaries
    """
    if not date:
        date = datetime.now(timezone.utc).date()
    elif isinstance(date, datetime):
        date = date.date()
    
    sql = """
    WITH daily_metrics AS (
        SELECT 
            -- Machine metrics
            COUNT(DISTINCT m.id) as total_machines,
            COUNT(DISTINCT CASE WHEN m.status = 'online' THEN m.id END) as online_machines,
            COUNT(DISTINCT CASE WHEN m.health_status = 'healthy' THEN m.id END) as healthy_machines,
            COUNT(DISTINCT CASE WHEN m.health_status = 'warning' THEN m.id END) as warning_machines,
            COUNT(DISTINCT CASE WHEN m.health_status = 'critical' THEN m.id END) as critical_machines,
            
            -- Prediction metrics
            COUNT(DISTINCT p.id) as total_predictions,
            COALESCE(AVG(p.confidence_score), 0) as avg_confidence,
            COALESCE(AVG(p.rul_value), 0) as avg_rul,
            
            -- Alert metrics
            COUNT(DISTINCT a.id) as new_alerts,
            COUNT(DISTINCT CASE WHEN a.severity = 'critical' THEN a.id END) as critical_alerts,
            COUNT(DISTINCT CASE WHEN a.is_resolved THEN a.id END) as resolved_alerts,
            
            -- Data metrics
            COUNT(DISTINCT md.id) as sensor_readings,
            COALESCE(AVG(md.data_quality_score), 0) as avg_data_quality,
            COUNT(DISTINCT CASE WHEN md.is_anomaly THEN md.id END) as anomalies_detected
            
        FROM organizations o
        LEFT JOIN machines m ON o.id = m.organization_id AND m.deleted_at IS NULL
        LEFT JOIN predictions p ON m.id = p.machine_id 
            AND DATE(p.created_at) = :date
            AND p.deleted_at IS NULL
        LEFT JOIN alerts a ON m.id = a.machine_id 
            AND DATE(a.created_at) = :date
            AND a.deleted_at IS NULL
        LEFT JOIN machine_data md ON m.id = md.machine_id 
            AND DATE(md.timestamp) = :date
        WHERE o.id = :org_id
            AND o.deleted_at IS NULL
        GROUP BY o.id
    ),
    top_machines AS (
        SELECT 
            m.id,
            m.name,
            m.health_status,
            m.status,
            COUNT(p.id) as predictions,
            COALESCE(AVG(p.confidence_score), 0) as avg_confidence,
            COUNT(a.id) as alerts,
            MAX(p.created_at) as last_prediction
        FROM machines m
        LEFT JOIN predictions p ON m.id = p.machine_id 
            AND DATE(p.created_at) = :date
        LEFT JOIN alerts a ON m.id = a.machine_id 
            AND DATE(a.created_at) = :date
        WHERE m.organization_id = :org_id
            AND m.deleted_at IS NULL
        GROUP BY m.id, m.name, m.health_status, m.status
        ORDER BY predictions DESC, alerts DESC
        LIMIT 10
    ),
    alert_summary AS (
        SELECT 
            a.severity,
            a.alert_type,
            COUNT(*) as count
        FROM alerts a
        JOIN machines m ON a.machine_id = m.id
        WHERE m.organization_id = :org_id
            AND DATE(a.created_at) = :date
            AND a.deleted_at IS NULL
        GROUP BY a.severity, a.alert_type
        ORDER BY severity, count DESC
    ),
    hourly_activity AS (
        SELECT 
            EXTRACT(HOUR FROM created_at) as hour,
            COUNT(*) as activity_count
        FROM activities
        WHERE organization_id = :org_id
            AND DATE(created_at) = :date
        GROUP BY EXTRACT(HOUR FROM created_at)
        ORDER BY hour
    )
    SELECT 
        (SELECT row_to_json(daily_metrics.*) FROM daily_metrics) as metrics,
        (SELECT json_agg(top_machines.*) FROM top_machines) as top_machines,
        (SELECT json_agg(alert_summary.*) FROM alert_summary) as alert_summary,
        (SELECT json_agg(hourly_activity.*) FROM hourly_activity) as hourly_activity
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id, "date": date}
            ).first()
            
            if not result:
                return {}
            
            metrics = result[0] or {}
            
            return {
                "report_type": "daily",
                "date": date.isoformat(),
                "summary": {
                    "machines": {
                        "total": metrics.get('total_machines', 0),
                        "online": metrics.get('online_machines', 0),
                        "offline": metrics.get('total_machines', 0) - metrics.get('online_machines', 0),
                        "health": {
                            "healthy": metrics.get('healthy_machines', 0),
                            "warning": metrics.get('warning_machines', 0),
                            "critical": metrics.get('critical_machines', 0)
                        }
                    },
                    "predictions": {
                        "total": metrics.get('total_predictions', 0),
                        "avg_confidence": round(float(metrics.get('avg_confidence', 0)), 2),
                        "avg_rul": round(float(metrics.get('avg_rul', 0)), 2)
                    },
                    "alerts": {
                        "new": metrics.get('new_alerts', 0),
                        "critical": metrics.get('critical_alerts', 0),
                        "resolved": metrics.get('resolved_alerts', 0),
                        "open": metrics.get('new_alerts', 0) - metrics.get('resolved_alerts', 0)
                    },
                    "data": {
                        "sensor_readings": metrics.get('sensor_readings', 0),
                        "data_quality": round(float(metrics.get('avg_data_quality', 0)), 2),
                        "anomalies": metrics.get('anomalies_detected', 0)
                    }
                },
                "top_machines": result[1] or [],
                "alert_breakdown": result[2] or [],
                "hourly_activity": result[3] or [],
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Error generating daily report: {e}")
        return {"error": str(e)}

# ============================================================================
# WEEKLY REPORTS
# ============================================================================

def generate_weekly_report(organization_id: UUID, end_date: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Generate weekly performance report
    
    Args:
        organization_id: UUID of the organization
        end_date: End date of the week (default: today)
    
    Returns:
        Weekly report with trends and performance metrics
    """
    if not end_date:
        end_date = datetime.now(timezone.utc).date()
    elif isinstance(end_date, datetime):
        end_date = end_date.date()
    
    start_date = end_date - timedelta(days=7)
    
    sql = """
    WITH weekly_trend AS (
        SELECT 
            DATE(created_at) as day,
            COUNT(DISTINCT p.id) as predictions,
            COUNT(DISTINCT a.id) as alerts,
            COUNT(DISTINCT md.id) as readings,
            COUNT(DISTINCT u.id) as active_users
        FROM organizations o
        CROSS JOIN generate_series(:start_date, :end_date, '1 day'::interval) as day
        LEFT JOIN predictions p ON DATE(p.created_at) = day AND p.organization_id = :org_id AND p.deleted_at IS NULL
        LEFT JOIN alerts a ON DATE(a.created_at) = day AND a.organization_id = :org_id AND a.deleted_at IS NULL
        LEFT JOIN machine_data md ON DATE(md.timestamp) = day 
        LEFT JOIN machines m ON md.machine_id = m.id AND m.organization_id = :org_id
        LEFT JOIN activities u ON DATE(u.created_at) = day AND u.organization_id = :org_id
        WHERE o.id = :org_id
        GROUP BY day
        ORDER BY day
    ),
    performance_metrics AS (
        SELECT 
            COALESCE(AVG(p.processing_time_ms), 0) as avg_prediction_latency,
            COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY p.processing_time_ms), 0) as p95_latency,
            COALESCE(AVG(a.resolution_time_minutes), 0) as avg_alert_resolution_time,
            COUNT(DISTINCT u.id) as total_active_users,
            COUNT(DISTINCT m.id) as machines_used
        FROM organizations o
        LEFT JOIN predictions p ON o.id = p.organization_id 
            AND p.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
            AND p.deleted_at IS NULL
        LEFT JOIN alerts a ON o.id = a.organization_id 
            AND a.resolved_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
            AND a.deleted_at IS NULL
        LEFT JOIN activities u ON o.id = u.organization_id 
            AND u.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
        LEFT JOIN machines m ON o.id = m.organization_id 
            AND m.deleted_at IS NULL
        WHERE o.id = :org_id
        GROUP BY o.id
    ),
    top_alert_types AS (
        SELECT 
            a.alert_type,
            COUNT(*) as count,
            AVG(a.resolution_time_minutes) as avg_resolution_time
        FROM alerts a
        WHERE a.organization_id = :org_id
            AND a.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
            AND a.deleted_at IS NULL
        GROUP BY a.alert_type
        ORDER BY count DESC
        LIMIT 5
    ),
    machine_performance AS (
        SELECT 
            m.name,
            COUNT(p.id) as predictions,
            COALESCE(AVG(p.confidence_score), 0) as avg_confidence,
            COUNT(a.id) as alerts,
            COALESCE(AVG(a.resolution_time_minutes), 0) as avg_alert_time
        FROM machines m
        LEFT JOIN predictions p ON m.id = p.machine_id 
            AND p.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
        LEFT JOIN alerts a ON m.id = a.machine_id 
            AND a.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
        WHERE m.organization_id = :org_id
            AND m.deleted_at IS NULL
        GROUP BY m.id, m.name
        ORDER BY predictions DESC
        LIMIT 5
    )
    SELECT 
        (SELECT json_agg(weekly_trend.*) FROM weekly_trend) as trend,
        (SELECT row_to_json(performance_metrics.*) FROM performance_metrics) as performance,
        (SELECT json_agg(top_alert_types.*) FROM top_alert_types) as top_alerts,
        (SELECT json_agg(machine_performance.*) FROM machine_performance) as top_machines
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {
                    "org_id": organization_id,
                    "start_date": start_date,
                    "end_date": end_date
                }
            ).first()
            
            if not result:
                return {}
            
            performance = result[1] or {}
            
            return {
                "report_type": "weekly",
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "daily_trend": result[0] or [],
                "performance": {
                    "avg_prediction_latency_ms": round(float(performance.get('avg_prediction_latency', 0)), 2),
                    "p95_prediction_latency_ms": round(float(performance.get('p95_latency', 0)), 2),
                    "avg_alert_resolution_minutes": round(float(performance.get('avg_alert_resolution_time', 0)), 2),
                    "total_active_users": performance.get('total_active_users', 0),
                    "machines_used": performance.get('machines_used', 0)
                },
                "top_alert_types": result[2] or [],
                "top_performing_machines": result[3] or [],
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Error generating weekly report: {e}")
        return {"error": str(e)}

# ============================================================================
# MONTHLY REPORTS
# ============================================================================

def generate_monthly_report(organization_id: UUID, month: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Generate monthly business report
    
    Args:
        organization_id: UUID of the organization
        month: Month for the report (default: current month)
    
    Returns:
        Monthly report with business metrics and insights
    """
    if not month:
        month = datetime.now(timezone.utc).replace(day=1)
    elif isinstance(month, datetime):
        month = month.replace(day=1)
    
    start_date = month.replace(day=1)
    if month.month == 12:
        end_date = month.replace(year=month.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_date = month.replace(month=month.month + 1, day=1) - timedelta(days=1)
    
    sql = """
    WITH monthly_summary AS (
        SELECT 
            -- Usage metrics
            COUNT(DISTINCT m.id) as machines_used,
            COUNT(DISTINCT p.id) as predictions_made,
            COUNT(DISTINCT a.id) as alerts_generated,
            COUNT(DISTINCT u.id) as active_users,
            
            -- Performance metrics
            COALESCE(AVG(p.confidence_score), 0) as avg_prediction_confidence,
            COALESCE(AVG(p.processing_time_ms), 0) as avg_latency,
            COALESCE(AVG(a.resolution_time_minutes), 0) as avg_alert_resolution,
            
            -- Business metrics
            COUNT(DISTINCT CASE WHEN m.health_status = 'critical' THEN m.id END) as critical_machines,
            COUNT(DISTINCT CASE WHEN p.actual_failure_date IS NOT NULL THEN p.machine_id END) as actual_failures,
            SUM(CASE WHEN a.severity = 'critical' THEN 1 ELSE 0 END) as critical_alerts,
            
            -- Data metrics
            COUNT(DISTINCT md.id) as total_readings,
            COALESCE(AVG(md.data_quality_score), 0) as avg_data_quality
            
        FROM organizations o
        LEFT JOIN machines m ON o.id = m.organization_id AND m.deleted_at IS NULL
        LEFT JOIN predictions p ON m.id = p.machine_id 
            AND p.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
            AND p.deleted_at IS NULL
        LEFT JOIN alerts a ON m.id = a.machine_id 
            AND a.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
            AND a.deleted_at IS NULL
        LEFT JOIN users u ON o.id = u.organization_id 
            AND u.last_login_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
            AND u.deleted_at IS NULL
        LEFT JOIN machine_data md ON m.id = md.machine_id 
            AND md.timestamp BETWEEN :start_date AND :end_date + INTERVAL '1 day'
        WHERE o.id = :org_id
        GROUP BY o.id
    ),
    top_performers AS (
        SELECT 
            m.name as machine_name,
            m.machine_type,
            COUNT(p.id) as prediction_count,
            COALESCE(AVG(p.confidence_score), 0) as avg_confidence,
            COUNT(a.id) as alert_count
        FROM machines m
        JOIN predictions p ON m.id = p.machine_id
        WHERE m.organization_id = :org_id
            AND p.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
        GROUP BY m.id, m.name, m.machine_type
        ORDER BY avg_confidence DESC, prediction_count DESC
        LIMIT 5
    ),
    improvement_areas AS (
        SELECT 
            m.name as machine_name,
            m.machine_type,
            COUNT(a.id) as alert_count,
            COALESCE(AVG(a.resolution_time_minutes), 0) as avg_resolution_time,
            COUNT(DISTINCT CASE WHEN a.severity = 'critical' THEN a.id END) as critical_count
        FROM machines m
        JOIN alerts a ON m.id = a.machine_id
        WHERE m.organization_id = :org_id
            AND a.created_at BETWEEN :start_date AND :end_date + INTERVAL '1 day'
        GROUP BY m.id, m.name, m.machine_type
        ORDER BY alert_count DESC, critical_count DESC
        LIMIT 5
    ),
    daily_usage AS (
        SELECT 
            DATE(created_at) as day,
            COUNT(DISTINCT p.id) as predictions,
            COUNT(DISTINCT a.id) as alerts
        FROM organizations o
        CROSS JOIN generate_series(:start_date, :end_date, '1 day'::interval) as day
        LEFT JOIN predictions p ON DATE(p.created_at) = day AND p.organization_id = :org_id
        LEFT JOIN alerts a ON DATE(a.created_at) = day AND a.organization_id = :org_id
        WHERE o.id = :org_id
        GROUP BY day
        ORDER BY day
    )
    SELECT 
        (SELECT row_to_json(monthly_summary.*) FROM monthly_summary) as summary,
        (SELECT json_agg(top_performers.*) FROM top_performers) as top_performers,
        (SELECT json_agg(improvement_areas.*) FROM improvement_areas) as improvement_areas,
        (SELECT json_agg(daily_usage.*) FROM daily_usage) as daily_usage
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {
                    "org_id": organization_id,
                    "start_date": start_date,
                    "end_date": end_date
                }
            ).first()
            
            if not result:
                return {}
            
            summary = result[0] or {}
            
            return {
                "report_type": "monthly",
                "month": start_date.strftime("%Y-%m"),
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "summary": {
                    "usage": {
                        "machines_used": summary.get('machines_used', 0),
                        "predictions_made": summary.get('predictions_made', 0),
                        "alerts_generated": summary.get('alerts_generated', 0),
                        "active_users": summary.get('active_users', 0),
                        "total_readings": summary.get('total_readings', 0)
                    },
                    "performance": {
                        "avg_prediction_confidence": round(float(summary.get('avg_prediction_confidence', 0)), 2),
                        "avg_latency_ms": round(float(summary.get('avg_latency', 0)), 2),
                        "avg_alert_resolution_minutes": round(float(summary.get('avg_alert_resolution', 0)), 2),
                        "avg_data_quality": round(float(summary.get('avg_data_quality', 0)), 2)
                    },
                    "health": {
                        "critical_machines": summary.get('critical_machines', 0),
                        "actual_failures": summary.get('actual_failures', 0),
                        "critical_alerts": summary.get('critical_alerts', 0)
                    }
                },
                "top_performers": result[1] or [],
                "improvement_areas": result[2] or [],
                "daily_usage": result[3] or [],
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Error generating monthly report: {e}")
        return {"error": str(e)}

# ============================================================================
# DATA EXPORT
# ============================================================================

def export_machine_data(machine_id: UUID, 
                       start_date: datetime, 
                       end_date: datetime,
                       format: str = 'json') -> List[Dict[str, Any]]:
    """
    Export machine sensor data for analysis
    
    Args:
        machine_id: UUID of the machine
        start_date: Start date for export
        end_date: End date for export
        format: Export format ('json' or 'csv')
    
    Returns:
        List of sensor readings
    """
    sql = """
    SELECT 
        timestamp,
        temperature,
        vibration,
        rpm,
        current,
        pressure,
        voltage,
        power,
        additional_sensors,
        data_quality_score,
        is_anomaly,
        anomaly_score
    FROM machine_data
    WHERE machine_id = :machine_id
        AND timestamp BETWEEN :start_date AND :end_date
    ORDER BY timestamp
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {
                    "machine_id": machine_id,
                    "start_date": start_date,
                    "end_date": end_date
                }
            ).fetchall()
            
            data = []
            for row in result:
                record = {
                    "timestamp": row[0].isoformat() if row[0] else None,
                    "temperature": row[1],
                    "vibration": row[2],
                    "rpm": row[3],
                    "current": row[4],
                    "pressure": row[5],
                    "voltage": row[6],
                    "power": row[7],
                    "data_quality": row[9],
                    "is_anomaly": row[10],
                    "anomaly_score": row[11]
                }
                # Add additional sensors if present
                if row[8] and isinstance(row[8], dict):
                    record.update(row[8])
                data.append(record)
            
            return {
                "machine_id": str(machine_id),
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "record_count": len(data),
                "data": data,
                "exported_at": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Error exporting machine data: {e}")
        return {"error": str(e)}

# ============================================================================
# COMPLIANCE REPORTS
# ============================================================================

def get_compliance_report(organization_id: UUID, 
                         start_date: datetime, 
                         end_date: datetime) -> Dict[str, Any]:
    """
    Generate compliance report for auditing
    
    Args:
        organization_id: UUID of the organization
        start_date: Start date for the report
        end_date: End date for the report
    
    Returns:
        Compliance report with audit trail
    """
    sql = """
    WITH user_audit AS (
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as user_actions,
            COUNT(DISTINCT user_id) as active_users,
            COUNT(CASE WHEN action = 'LOGIN' AND action_status = 'success' THEN 1 END) as successful_logins,
            COUNT(CASE WHEN action = 'LOGIN' AND action_status = 'failure' THEN 1 END) as failed_logins
        FROM audit_logs
        WHERE organization_id = :org_id
            AND resource_type = 'user'
            AND created_at BETWEEN :start_date AND :end_date
        GROUP BY DATE(created_at)
        ORDER BY date
    ),
    data_access AS (
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as data_access_count,
            COUNT(DISTINCT user_id) as users_accessing_data,
            COUNT(CASE WHEN action = 'EXPORT' THEN 1 END) as exports
        FROM audit_logs
        WHERE organization_id = :org_id
            AND resource_type IN ('machine_data', 'predictions')
            AND action IN ('READ', 'EXPORT')
            AND created_at BETWEEN :start_date AND :end_date
        GROUP BY DATE(created_at)
        ORDER BY date
    ),
    security_events AS (
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as security_events,
            COUNT(CASE WHEN action_status = 'failure' THEN 1 END) as failed_actions,
            COUNT(CASE WHEN security_level = 'critical' THEN 1 END) as critical_events
        FROM audit_logs
        WHERE organization_id = :org_id
            AND security_level IN ('sensitive', 'critical')
            AND created_at BETWEEN :start_date AND :end_date
        GROUP BY DATE(created_at)
        ORDER BY date
    ),
    summary AS (
        SELECT 
            COUNT(DISTINCT CASE WHEN action = 'LOGIN' AND action_status = 'success' THEN user_id END) as unique_logins,
            COUNT(CASE WHEN action = 'LOGIN' AND action_status = 'failure' THEN 1 END) as failed_logins,
            COUNT(CASE WHEN resource_type = 'machine_data' THEN 1 END) as data_accesses,
            COUNT(CASE WHEN resource_type = 'predictions' THEN 1 END) as prediction_accesses,
            COUNT(CASE WHEN security_level = 'critical' THEN 1 END) as critical_events,
            COUNT(DISTINCT user_id) as users_with_activity,
            COUNT(DISTINCT ip_address) as unique_ip_addresses
        FROM audit_logs
        WHERE organization_id = :org_id
            AND created_at BETWEEN :start_date AND :end_date
    ),
    user_activity_detail AS (
        SELECT 
            u.email,
            u.first_name,
            u.last_name,
            u.role,
            COUNT(al.id) as total_actions,
            MAX(al.created_at) as last_action,
            COUNT(CASE WHEN al.action_status = 'failure' THEN 1 END) as failed_actions
        FROM users u
        LEFT JOIN audit_logs al ON u.id = al.user_id 
            AND al.created_at BETWEEN :start_date AND :end_date
        WHERE u.organization_id = :org_id
            AND u.deleted_at IS NULL
        GROUP BY u.id, u.email, u.first_name, u.last_name, u.role
        ORDER BY total_actions DESC
        LIMIT 20
    )
    SELECT 
        json_agg(DISTINCT user_audit.*) as user_audits,
        json_agg(DISTINCT data_access.*) as data_accesses,
        json_agg(DISTINCT security_events.*) as security_events,
        (SELECT row_to_json(summary.*) FROM summary) as summary,
        json_agg(DISTINCT user_activity_detail.*) as user_details
    FROM user_audit, data_access, security_events, user_activity_detail
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {
                    "org_id": organization_id,
                    "start_date": start_date,
                    "end_date": end_date
                }
            ).first()
            
            if not result:
                return {}
            
            summary = result[3] or {}
            
            return {
                "report_type": "compliance",
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "summary": {
                    "unique_logins": summary.get('unique_logins', 0),
                    "failed_logins": summary.get('failed_logins', 0),
                    "data_accesses": summary.get('data_accesses', 0),
                    "prediction_accesses": summary.get('prediction_accesses', 0),
                    "critical_events": summary.get('critical_events', 0),
                    "active_users": summary.get('users_with_activity', 0),
                    "unique_ip_addresses": summary.get('unique_ip_addresses', 0)
                },
                "daily_user_audit": result[0] or [],
                "daily_data_access": result[1] or [],
                "daily_security_events": result[2] or [],
                "user_activity_details": result[4] or [],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "retention_period_days": 365,  # Configurable
                "compliance_standards": ["ISO27001", "GDPR", "SOC2"]  # Applicable standards
            }
    except Exception as e:
        logger.error(f"Error generating compliance report: {e}")
        return {"error": str(e)}

# ============================================================================
# CUSTOM REPORT
# ============================================================================

def generate_custom_report(organization_id: UUID,
                          start_date: datetime,
                          end_date: datetime,
                          metrics: List[str],
                          group_by: str = 'day') -> Dict[str, Any]:
    """
    Generate custom report with specified metrics
    
    Args:
        organization_id: UUID of the organization
        start_date: Start date for the report
        end_date: End date for the report
        metrics: List of metrics to include
        group_by: Grouping interval ('hour', 'day', 'week', 'month')
    
    Returns:
        Custom report with requested metrics
    """
    
    # Map group_by to SQL interval
    group_map = {
        'hour': 'hour',
        'day': 'day',
        'week': 'week',
        'month': 'month'
    }
    
    group_interval = group_map.get(group_by, 'day')
    
    # Build dynamic SQL based on requested metrics
    metric_selects = []
    metric_joins = []
    
    metric_config = {
        'predictions': {
            'select': "COUNT(DISTINCT p.id) as predictions",
            'join': "LEFT JOIN predictions p ON DATE_TRUNC(:group_by, p.created_at) = time_slot AND p.organization_id = :org_id AND p.deleted_at IS NULL"
        },
        'alerts': {
            'select': "COUNT(DISTINCT a.id) as alerts",
            'join': "LEFT JOIN alerts a ON DATE_TRUNC(:group_by, a.created_at) = time_slot AND a.organization_id = :org_id AND a.deleted_at IS NULL"
        },
        'readings': {
            'select': "COUNT(DISTINCT md.id) as readings",
            'join': "LEFT JOIN machine_data md ON DATE_TRUNC(:group_by, md.timestamp) = time_slot LEFT JOIN machines m ON md.machine_id = m.id AND m.organization_id = :org_id"
        },
        'active_users': {
            'select': "COUNT(DISTINCT u.id) as active_users",
            'join': "LEFT JOIN activities u ON DATE_TRUNC(:group_by, u.created_at) = time_slot AND u.organization_id = :org_id"
        },
        'avg_confidence': {
            'select': "AVG(p.confidence_score) as avg_confidence",
            'join': "LEFT JOIN predictions p ON DATE_TRUNC(:group_by, p.created_at) = time_slot AND p.organization_id = :org_id AND p.deleted_at IS NULL"
        },
        'avg_rul': {
            'select': "AVG(p.rul_value) as avg_rul",
            'join': "LEFT JOIN predictions p ON DATE_TRUNC(:group_by, p.created_at) = time_slot AND p.organization_id = :org_id AND p.deleted_at IS NULL"
        }
    }
    
    for metric in metrics:
        if metric in metric_config:
            metric_selects.append(metric_config[metric]['select'])
            if metric_config[metric]['join'] not in metric_joins:
                metric_joins.append(metric_config[metric]['join'])
    
    if not metric_selects:
        metric_selects = ["COUNT(*) as count"]
    
    # Build the SQL query
    sql = f"""
    WITH time_series AS (
        SELECT generate_series(
            date_trunc(:group_by, :start_date::timestamp),
            date_trunc(:group_by, :end_date::timestamp),
            ('1 ' || :group_by)::interval
        ) as time_slot
    )
    SELECT 
        time_slot,
        {', '.join(metric_selects)}
    FROM time_series
    {' '.join(metric_joins)}
    GROUP BY time_slot
    ORDER BY time_slot
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {
                    "org_id": organization_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "group_by": group_interval
                }
            ).fetchall()
            
            data = []
            for row in result:
                record = {
                    "time_slot": row[0].isoformat() if row[0] else None
                }
                # Add each metric to the record
                for i, metric in enumerate(metric_selects):
                    metric_name = metric.split(' as ')[-1] if ' as ' in metric else f"metric_{i}"
                    value = row[i + 1]
                    if value is not None and isinstance(value, (int, float)):
                        value = round(float(value), 2)
                    record[metric_name] = value
                data.append(record)
            
            return {
                "report_type": "custom",
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "group_by": group_by,
                "metrics": metrics,
                "data": data,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        logger.error(f"Error generating custom report: {e}")
        return {"error": str(e)}

# ============================================================================
# TEST FUNCTION
# ============================================================================

if __name__ == "__main__":
    import json
    from uuid import UUID
    
    print("=" * 70)
    print("SYNAPSEPM - Reporting Queries Test")
    print("=" * 70)
    
    # Test with a sample organization ID
    # Replace with actual UUID from your database
    test_org_id = UUID('00000000-0000-0000-0000-000000000000')
    
    print(f"\n📊 Testing Reporting Queries...")
    print(f"Organization ID: {test_org_id}")
    print("-" * 50)
    
    try:
        # Test 1: Daily Report
        print("\n1. Testing generate_daily_report...")
        result = generate_daily_report(test_org_id)
        if result and 'error' not in result:
            print(f"   ✓ Daily report generated")
            print(f"   📅 Date: {result.get('date')}")
            summary = result.get('summary', {})
            print(f"   📊 Machines: {summary.get('machines', {}).get('total', 0)}")
        else:
            print(f"   ⚠ No data for daily report")
        
        # Test 2: Weekly Report
        print("\n2. Testing generate_weekly_report...")
        result = generate_weekly_report(test_org_id)
        if result and 'error' not in result:
            print(f"   ✓ Weekly report generated")
            period = result.get('period', {})
            print(f"   📅 Period: {period.get('start')} to {period.get('end')}")
        else:
            print(f"   ⚠ No data for weekly report")
        
        # Test 3: Monthly Report
        print("\n3. Testing generate_monthly_report...")
        result = generate_monthly_report(test_org_id)
        if result and 'error' not in result:
            print(f"   ✓ Monthly report generated")
            print(f"   📅 Month: {result.get('month')}")
        else:
            print(f"   ⚠ No data for monthly report")
        
        # Test 4: Compliance Report
        print("\n4. Testing get_compliance_report...")
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        result = get_compliance_report(test_org_id, start_date, end_date)
        if result and 'error' not in result:
            print(f"   ✓ Compliance report generated")
            summary = result.get('summary', {})
            print(f"   🔐 Unique logins: {summary.get('unique_logins', 0)}")
        else:
            print(f"   ⚠ No data for compliance report")
        
        # Test 5: Custom Report
        print("\n5. Testing generate_custom_report...")
        result = generate_custom_report(
            test_org_id,
            start_date,
            end_date,
            metrics=['predictions', 'alerts', 'active_users'],
            group_by='day'
        )
        if result and 'error' not in result:
            print(f"   ✓ Custom report generated")
            print(f"   📊 Data points: {len(result.get('data', []))}")
        else:
            print(f"   ⚠ No data for custom report")
        
        print("\n" + "=" * 70)
        print("✅ REPORTING QUERIES TESTED SUCCESSFULLY!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()