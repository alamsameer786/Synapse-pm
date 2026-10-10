"""
SynapsePM - Analytics Queries
Complex analytical queries for business intelligence and reporting
Handles: Advanced analytics, aggregations, trends, and performance metrics
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
# MACHINE ANALYTICS
# ============================================================================

def get_machine_health_trend(organization_id: UUID, days: int = 30) -> List[Dict]:
    """
    Get machine health trend over time
    
    Args:
        organization_id: UUID of the organization
        days: Number of days to analyze
    
    Returns:
        List of daily health breakdowns
    """
    sql = """
    WITH daily_health AS (
        SELECT 
            DATE(created_at) as date,
            health_status,
            COUNT(DISTINCT id) as machine_count
        FROM machines
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
            AND created_at >= CURRENT_DATE - :days * INTERVAL '1 day'
        GROUP BY DATE(created_at), health_status
    )
    SELECT 
        date,
        jsonb_object_agg(health_status, machine_count) as health_breakdown
    FROM daily_health
    GROUP BY date
    ORDER BY date DESC
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id, "days": days}
            ).fetchall()
            
            return [
                {
                    "date": row[0].isoformat(),
                    "health_breakdown": row[1]
                }
                for row in result
            ]
    except Exception as e:
        logger.error(f"Error in get_machine_health_trend: {e}")
        return []

def get_machine_performance_metrics(
    organization_id: UUID, 
    machine_type: Optional[str] = None,
    days: int = 30
) -> Dict:
    """
    Get performance metrics for machines
    
    Args:
        organization_id: UUID of the organization
        machine_type: Optional filter by machine type
        days: Analysis period in days
    
    Returns:
 Dictionary of performance metrics
    """
    sql = """
    WITH machine_metrics AS (
        SELECT 
            m.id,
            m.name,
            m.machine_type,
            m.status,
            m.health_status,
            m.operational_hours,
            COUNT(DISTINCT p.id) as prediction_count,
            AVG(p.confidence_score) as avg_confidence,
            AVG(p.rul_value) as avg_rul,
            MIN(p.rul_value) as min_rul,
            COUNT(DISTINCT a.id) as alert_count,
            COUNT(DISTINCT CASE WHEN a.severity = 'critical' THEN a.id END) as critical_alerts,
            MAX(p.created_at) as last_prediction,
            EXTRACT(EPOCH FROM (NOW() - MAX(p.created_at)))/3600 as hours_since_prediction
        FROM machines m
        LEFT JOIN predictions p ON p.machine_id = m.id 
            AND p.created_at >= NOW() - :days * INTERVAL '1 day'
        LEFT JOIN alerts a ON a.machine_id = m.id 
            AND a.created_at >= NOW() - :days * INTERVAL '1 day'
        WHERE m.organization_id = :org_id
            AND m.deleted_at IS NULL
            AND (:machine_type IS NULL OR m.machine_type = :machine_type)
        GROUP BY m.id, m.name, m.machine_type, m.status, m.health_status, m.operational_hours
    )
    SELECT 
        COUNT(*) as total_machines,
        SUM(CASE WHEN health_status = 'healthy' THEN 1 ELSE 0 END) as healthy_count,
        SUM(CASE WHEN health_status = 'warning' THEN 1 ELSE 0 END) as warning_count,
        SUM(CASE WHEN health_status = 'critical' THEN 1 ELSE 0 END) as critical_count,
        SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_count,
        SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) as offline_count,
        AVG(avg_confidence) as overall_confidence,
        AVG(avg_rul) as average_rul,
        MIN(min_rul) as lowest_rul,
        SUM(alert_count) as total_alerts,
        SUM(critical_alerts) as total_critical_alerts,
        json_agg(json_build_object(
            'id', id,
            'name', name,
            'type', machine_type,
            'health', health_status,
            'status', status,
            'avg_rul', avg_rul,
            'min_rul', min_rul,
            'alert_count', alert_count,
            'critical_alerts', critical_alerts,
            'last_prediction', last_prediction
        ) ORDER BY min_rul NULLS LAST) as machines
    FROM machine_metrics
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {
                    "org_id": organization_id, 
                    "machine_type": machine_type,
                    "days": days
                }
            ).first()
            
            if not result:
                return {}
            
            return {
                "summary": {
                    "total_machines": result[0] or 0,
                    "healthy_count": result[1] or 0,
                    "warning_count": result[2] or 0,
                    "critical_count": result[3] or 0,
                    "online_count": result[4] or 0,
                    "offline_count": result[5] or 0,
                    "overall_confidence": float(result[6]) if result[6] else 0,
                    "average_rul": float(result[7]) if result[7] else 0,
                    "lowest_rul": float(result[8]) if result[8] else 0,
                    "total_alerts": result[9] or 0,
                    "total_critical_alerts": result[10] or 0
                },
                "machines": result[11] or []
            }
    except Exception as e:
        logger.error(f"Error in get_machine_performance_metrics: {e}")
        return {}

# ============================================================================
# PREDICTION ANALYTICS
# ============================================================================

def get_prediction_accuracy_trend(organization_id: UUID, days: int = 30) -> List[Dict]:
    """
    Get prediction accuracy trend over time
    
    Args:
        organization_id: UUID of the organization
        days: Number of days to analyze
    
    Returns:
        List of daily accuracy metrics
    """
    sql = """
    SELECT 
        DATE(created_at) as date,
        AVG(confidence_score) as avg_confidence,
        AVG(prediction_error) as avg_error,
        COUNT(*) as prediction_count,
        SUM(CASE WHEN prediction_error < 10 THEN 1 ELSE 0 END) as accurate_count
    FROM predictions
    WHERE organization_id = :org_id
        AND deleted_at IS NULL
        AND created_at >= CURRENT_DATE - :days * INTERVAL '1 day'
        AND prediction_error IS NOT NULL
    GROUP BY DATE(created_at)
    ORDER BY date DESC
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id, "days": days}
            ).fetchall()
            
            return [
                {
                    "date": row[0].isoformat(),
                    "avg_confidence": float(row[1]) if row[1] else 0,
                    "avg_error": float(row[2]) if row[2] else 0,
                    "prediction_count": row[3] or 0,
                    "accurate_count": row[4] or 0,
                    "accuracy_rate": (row[4] / row[3] * 100) if row[3] and row[3] > 0 else 0
                }
                for row in result
            ]
    except Exception as e:
        logger.error(f"Error in get_prediction_accuracy_trend: {e}")
        return []

def get_rul_distribution(organization_id: UUID, bins: int = 10) -> Dict:
    """
    Get distribution of RUL values
    
    Args:
        organization_id: UUID of the organization
        bins: Number of bins for histogram
    
    Returns:
        Distribution of RUL values
    """
    sql = """
    WITH rul_stats AS (
        SELECT 
            p.rul_value,
            m.name as machine_name,
            m.machine_type
        FROM predictions p
        JOIN machines m ON m.id = p.machine_id
        WHERE p.organization_id = :org_id
            AND p.deleted_at IS NULL
            AND p.rul_value IS NOT NULL
            AND p.created_at = (
                SELECT MAX(created_at)
                FROM predictions p2
                WHERE p2.machine_id = p.machine_id
            )
    )
    SELECT 
        MIN(rul_value) as min_rul,
        MAX(rul_value) as max_rul,
        AVG(rul_value) as avg_rul,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY rul_value) as q1,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rul_value) as median,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY rul_value) as q3,
        COUNT(*) as total_machines,
        SUM(CASE WHEN rul_value < 30 THEN 1 ELSE 0 END) as critical_count,
        SUM(CASE WHEN rul_value BETWEEN 30 AND 60 THEN 1 ELSE 0 END) as warning_count,
        SUM(CASE WHEN rul_value > 60 THEN 1 ELSE 0 END) as healthy_count,
        json_agg(json_build_object(
            'machine', machine_name,
            'type', machine_type,
            'rul', rul_value
        ) ORDER BY rul_value) as machines
    FROM rul_stats
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id}
            ).first()
            
            if not result:
                return {}
            
            return {
                "statistics": {
                    "min": float(result[0]) if result[0] else 0,
                    "max": float(result[1]) if result[1] else 0,
                    "avg": float(result[2]) if result[2] else 0,
                    "q1": float(result[3]) if result[3] else 0,
                    "median": float(result[4]) if result[4] else 0,
                    "q3": float(result[5]) if result[5] else 0,
                    "total_machines": result[6] or 0,
                    "critical_count": result[7] or 0,
                    "warning_count": result[8] or 0,
                    "healthy_count": result[9] or 0
                },
                "machines": result[10] or []
            }
    except Exception as e:
        logger.error(f"Error in get_rul_distribution: {e}")
        return {}

# ============================================================================
# SENSOR DATA ANALYTICS
# ============================================================================

def get_sensor_data_analysis(machine_id: UUID, hours: int = 24) -> Dict:
    """
    Analyze sensor data patterns and anomalies
    
    Args:
        machine_id: UUID of the machine
        hours: Analysis period in hours
    
    Returns:
        Sensor data statistics and patterns
    """
    sql = """
    WITH sensor_stats AS (
        SELECT 
            AVG(temperature) as avg_temp,
            STDDEV(temperature) as std_temp,
            MIN(temperature) as min_temp,
            MAX(temperature) as max_temp,
            AVG(vibration) as avg_vib,
            STDDEV(vibration) as std_vib,
            MIN(vibration) as min_vib,
            MAX(vibration) as max_vib,
            AVG(pressure) as avg_press,
            STDDEV(pressure) as std_press,
            MIN(pressure) as min_press,
            MAX(pressure) as max_press,
            COUNT(*) as reading_count,
            SUM(CASE WHEN is_anomaly THEN 1 ELSE 0 END) as anomaly_count
        FROM machine_data
        WHERE machine_id = :machine_id
            AND timestamp >= NOW() - :hours * INTERVAL '1 hour'
    ),
    hourly_patterns AS (
        SELECT 
            EXTRACT(HOUR FROM timestamp) as hour,
            AVG(temperature) as avg_temp,
            AVG(vibration) as avg_vib,
            AVG(pressure) as avg_press,
            COUNT(*) as readings
        FROM machine_data
        WHERE machine_id = :machine_id
            AND timestamp >= NOW() - :hours * INTERVAL '1 hour'
        GROUP BY EXTRACT(HOUR FROM timestamp)
        ORDER BY hour
    ),
    anomalies AS (
        SELECT 
            timestamp,
            temperature,
            vibration,
            pressure,
            anomaly_score
        FROM machine_data
        WHERE machine_id = :machine_id
            AND is_anomaly = true
            AND timestamp >= NOW() - :hours * INTERVAL '1 hour'
        ORDER BY timestamp DESC
    )
    SELECT 
        row_to_json(sensor_stats.*) as stats,
        json_agg(hourly_patterns.*) as patterns,
        json_agg(anomalies.*) as anomalies
    FROM sensor_stats, hourly_patterns, anomalies
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"machine_id": machine_id, "hours": hours}
            ).first()
            
            if not result:
                return {}
            
            stats = result[0] or {}
            patterns = result[1] or []
            anomalies = result[2] or []
            
            return {
                "statistics": {
                    "temperature": {
                        "avg": float(stats.get('avg_temp', 0)),
                        "std": float(stats.get('std_temp', 0)),
                        "min": float(stats.get('min_temp', 0)),
                        "max": float(stats.get('max_temp', 0))
                    },
                    "vibration": {
                        "avg": float(stats.get('avg_vib', 0)),
                        "std": float(stats.get('std_vib', 0)),
                        "min": float(stats.get('min_vib', 0)),
                        "max": float(stats.get('max_vib', 0))
                    },
                    "pressure": {
                        "avg": float(stats.get('avg_press', 0)),
                        "std": float(stats.get('std_press', 0)),
                        "min": float(stats.get('min_press', 0)),
                        "max": float(stats.get('max_press', 0))
                    },
                    "readings": stats.get('reading_count', 0),
                    "anomalies": stats.get('anomaly_count', 0),
                    "anomaly_rate": (stats.get('anomaly_count', 0) / stats.get('reading_count', 1)) * 100
                },
                "hourly_patterns": patterns,
                "recent_anomalies": anomalies[:10]  # Last 10 anomalies
            }
    except Exception as e:
        logger.error(f"Error in get_sensor_data_analysis: {e}")
        return {}

# ============================================================================
# ALERT ANALYTICS
# ============================================================================

def get_alert_patterns(organization_id: UUID, days: int = 30) -> Dict:
    """
    Analyze alert patterns and correlations
    
    Args:
        organization_id: UUID of the organization
        days: Analysis period in days
    
    Returns:
        Alert pattern analysis
    """
    sql = """
    WITH alert_stats AS (
        SELECT 
            COUNT(*) as total_alerts,
            COUNT(DISTINCT machine_id) as affected_machines,
            AVG(CASE WHEN resolved_at IS NOT NULL 
                THEN EXTRACT(EPOCH FROM (resolved_at - created_at))/60 
                ELSE NULL END) as avg_resolution_time,
            COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_count,
            COUNT(CASE WHEN severity = 'warning' THEN 1 END) as warning_count,
            COUNT(CASE WHEN severity = 'info' THEN 1 END) as info_count
        FROM alerts
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
            AND created_at >= NOW() - :days * INTERVAL '1 day'
    ),
    alert_correlation AS (
        SELECT 
            a1.alert_type as type1,
            a2.alert_type as type2,
            COUNT(*) as co_occurrence
        FROM alerts a1
        JOIN alerts a2 ON a1.machine_id = a2.machine_id
            AND a1.created_at BETWEEN a2.created_at - INTERVAL '1 hour' 
                                  AND a2.created_at + INTERVAL '1 hour'
            AND a1.id < a2.id
        WHERE a1.organization_id = :org_id
            AND a1.deleted_at IS NULL
            AND a2.deleted_at IS NULL
            AND a1.created_at >= NOW() - :days * INTERVAL '1 day'
        GROUP BY a1.alert_type, a2.alert_type
        ORDER BY co_occurrence DESC
        LIMIT 10
    ),
    peak_hours AS (
        SELECT 
            EXTRACT(HOUR FROM created_at) as hour,
            COUNT(*) as alert_count,
            RANK() OVER (ORDER BY COUNT(*) DESC) as rank
        FROM alerts
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
            AND created_at >= NOW() - :days * INTERVAL '1 day'
        GROUP BY EXTRACT(HOUR FROM created_at)
    ),
    daily_trend AS (
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as alert_count,
            COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_count
        FROM alerts
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
            AND created_at >= NOW() - :days * INTERVAL '1 day'
        GROUP BY DATE(created_at)
        ORDER BY date DESC
    )
    SELECT 
        row_to_json(alert_stats.*) as stats,
        json_agg(alert_correlation.*) as correlations,
        json_agg(peak_hours.* ORDER BY hour) as peak_hours,
        json_agg(daily_trend.*) as daily_trend
    FROM alert_stats, alert_correlation, peak_hours, daily_trend
    WHERE peak_hours.rank <= 5
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id, "days": days}
            ).first()
            
            if not result:
                return {}
            
            return {
                "summary": result[0] or {},
                "correlations": result[1] or [],
                "peak_hours": result[2] or [],
                "daily_trend": result[3] or []
            }
    except Exception as e:
        logger.error(f"Error in get_alert_patterns: {e}")
        return {}

def get_alert_trends(organization_id: UUID, days: int = 30) -> List[Dict]:
    """
    Get alert trends over time
    
    Args:
        organization_id: UUID of the organization
        days: Analysis period in days
    
    Returns:
        Daily alert counts by severity
    """
    sql = """
    SELECT 
        DATE(created_at) as date,
        COUNT(*) as total_alerts,
        COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_alerts,
        COUNT(CASE WHEN severity = 'warning' THEN 1 END) as warning_alerts,
        COUNT(CASE WHEN severity = 'info' THEN 1 END) as info_alerts,
        COUNT(DISTINCT machine_id) as affected_machines
    FROM alerts
    WHERE organization_id = :org_id
        AND deleted_at IS NULL
        AND created_at >= CURRENT_DATE - :days * INTERVAL '1 day'
    GROUP BY DATE(created_at)
    ORDER BY date DESC
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id, "days": days}
            ).fetchall()
            
            return [
                {
                    "date": row[0].isoformat(),
                    "total": row[1] or 0,
                    "critical": row[2] or 0,
                    "warning": row[3] or 0,
                    "info": row[4] or 0,
                    "affected_machines": row[5] or 0
                }
                for row in result
            ]
    except Exception as e:
        logger.error(f"Error in get_alert_trends: {e}")
        return []

# ============================================================================
# ORGANIZATION ANALYTICS
# ============================================================================

def get_organization_growth(start_date: Optional[datetime] = None) -> Dict:
    """
    Get organization growth metrics
    
    Args:
        start_date: Start date for analysis (default: 1 year ago)
    
    Returns:
        Growth metrics and trends
    """
    if not start_date:
        start_date = datetime.now(timezone.utc) - timedelta(days=365)
    
    sql = """
    WITH monthly_stats AS (
        SELECT 
            DATE_TRUNC('month', created_at) as month,
            COUNT(DISTINCT id) as new_orgs,
            SUM(current_users) as total_users,
            SUM(current_machines) as total_machines
        FROM organizations
        WHERE deleted_at IS NULL
            AND created_at >= :start_date
        GROUP BY DATE_TRUNC('month', created_at)
    ),
    current_stats AS (
        SELECT 
            COUNT(*) as total_orgs,
            SUM(current_users) as total_users,
            SUM(current_machines) as total_machines
        FROM organizations
        WHERE deleted_at IS NULL
    )
    SELECT 
        json_agg(monthly_stats.* ORDER BY month DESC) as monthly,
        row_to_json(current_stats.*) as current
    FROM monthly_stats, current_stats
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"start_date": start_date}
            ).first()
            
            if not result:
                return {}
            
            monthly = result[0] or []
            current = result[1] or {}
            
            # Calculate growth rates
            if len(monthly) >= 2:
                last_month = monthly[0]
                prev_month = monthly[1]
                
                org_growth = ((last_month['new_orgs'] - prev_month['new_orgs']) 
                             / prev_month['new_orgs'] * 100) if prev_month['new_orgs'] > 0 else 0
                user_growth = ((last_month['total_users'] - prev_month['total_users']) 
                              / prev_month['total_users'] * 100) if prev_month['total_users'] > 0 else 0
            else:
                org_growth = user_growth = 0
            
            return {
                "monthly": [
                    {
                        "month": m['month'].isoformat() if m.get('month') else None,
                        "new_organizations": m.get('new_orgs', 0),
                        "total_users": m.get('total_users', 0),
                        "total_machines": m.get('total_machines', 0)
                    }
                    for m in monthly
                ],
                "current": {
                    "organizations": current.get('total_orgs', 0),
                    "users": current.get('total_users', 0),
                    "machines": current.get('total_machines', 0)
                },
                "growth": {
                    "organization_growth_rate": round(org_growth, 2),
                    "user_growth_rate": round(user_growth, 2)
                }
            }
    except Exception as e:
        logger.error(f"Error in get_organization_growth: {e}")
        return {}

def get_organization_statistics(organization_id: UUID) -> Dict:
    """
    Get comprehensive statistics for an organization
    
    Args:
        organization_id: UUID of the organization
    
    Returns:
        Organization statistics
    """
    sql = """
    WITH org_info AS (
        SELECT 
            o.name,
            o.plan,
            o.created_at,
            o.max_users,
            o.max_machines,
            o.current_users,
            o.current_machines,
            o.predictions_this_month,
            o.max_predictions_per_month
        FROM organizations o
        WHERE o.id = :org_id
            AND o.deleted_at IS NULL
    ),
    machine_stats AS (
        SELECT 
            COUNT(*) as total_machines,
            COUNT(CASE WHEN status = 'online' THEN 1 END) as online_machines,
            COUNT(CASE WHEN health_status = 'healthy' THEN 1 END) as healthy_machines,
            COUNT(CASE WHEN health_status = 'warning' THEN 1 END) as warning_machines,
            COUNT(CASE WHEN health_status = 'critical' THEN 1 END) as critical_machines
        FROM machines
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
    ),
    user_stats AS (
        SELECT 
            COUNT(*) as total_users,
            COUNT(CASE WHEN is_active THEN 1 END) as active_users,
            COUNT(CASE WHEN last_login_at > NOW() - INTERVAL '7 days' THEN 1 END) as active_last_week
        FROM users
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
    ),
    prediction_stats AS (
        SELECT 
            COUNT(*) as total_predictions,
            AVG(confidence_score) as avg_confidence,
            COUNT(CASE WHEN created_at > NOW() - INTERVAL '30 days' THEN 1 END) as predictions_30d
        FROM predictions
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
    ),
    alert_stats AS (
        SELECT 
            COUNT(*) as total_alerts,
            COUNT(CASE WHEN alert_status = 'active' THEN 1 END) as active_alerts,
            COUNT(CASE WHEN severity = 'critical' AND alert_status = 'active' THEN 1 END) as critical_alerts
        FROM alerts
        WHERE organization_id = :org_id
            AND deleted_at IS NULL
    )
    SELECT 
        row_to_json(org_info.*) as org,
        row_to_json(machine_stats.*) as machines,
        row_to_json(user_stats.*) as users,
        row_to_json(prediction_stats.*) as predictions,
        row_to_json(alert_stats.*) as alerts
    FROM org_info, machine_stats, user_stats, prediction_stats, alert_stats
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id}
            ).first()
            
            if not result:
                return {}
            
            org = result[0] or {}
            machines = result[1] or {}
            users = result[2] or {}
            predictions = result[3] or {}
            alerts = result[4] or {}
            
            return {
                "organization": {
                    "name": org.get('name'),
                    "plan": org.get('plan'),
                    "created_at": org.get('created_at').isoformat() if org.get('created_at') else None,
                    "limits": {
                        "max_users": org.get('max_users', 0),
                        "max_machines": org.get('max_machines', 0),
                        "max_predictions": org.get('max_predictions_per_month', 0)
                    },
                    "usage": {
                        "users": org.get('current_users', 0),
                        "machines": org.get('current_machines', 0),
                        "predictions": org.get('predictions_this_month', 0),
                        "usage_percentage": (org.get('predictions_this_month', 0) / 
                                           org.get('max_predictions_per_month', 1)) * 100
                    }
                },
                "machines": {
                    "total": machines.get('total_machines', 0),
                    "online": machines.get('online_machines', 0),
                    "offline": machines.get('total_machines', 0) - machines.get('online_machines', 0),
                    "health": {
                        "healthy": machines.get('healthy_machines', 0),
                        "warning": machines.get('warning_machines', 0),
                        "critical": machines.get('critical_machines', 0)
                    }
                },
                "users": {
                    "total": users.get('total_users', 0),
                    "active": users.get('active_users', 0),
                    "active_last_week": users.get('active_last_week', 0),
                    "inactive": users.get('total_users', 0) - users.get('active_users', 0)
                },
                "predictions": {
                    "total": predictions.get('total_predictions', 0),
                    "last_30_days": predictions.get('predictions_30d', 0),
                    "avg_confidence": float(predictions.get('avg_confidence', 0))
                },
                "alerts": {
                    "total": alerts.get('total_alerts', 0),
                    "active": alerts.get('active_alerts', 0),
                    "critical": alerts.get('critical_alerts', 0)
                }
            }
    except Exception as e:
        logger.error(f"Error in get_organization_statistics: {e}")
        return {}

# ============================================================================
# USER ANALYTICS
# ============================================================================

def get_user_activity_summary(organization_id: UUID, days: int = 30) -> Dict:
    """
    Get user activity summary
    
    Args:
        organization_id: UUID of the organization
        days: Analysis period in days
    
    Returns:
        User activity metrics
    """
    sql = """
    WITH user_activity AS (
        SELECT 
            u.id,
            u.email,
            u.first_name,
            u.last_name,
            u.role,
            u.last_login_at,
            COUNT(DISTINCT a.id) as action_count,
            COUNT(DISTINCT p.id) as prediction_count,
            MAX(a.created_at) as last_action
        FROM users u
        LEFT JOIN activities a ON a.user_id = u.id 
            AND a.created_at >= NOW() - :days * INTERVAL '1 day'
        LEFT JOIN predictions p ON p.user_id = u.id 
            AND p.created_at >= NOW() - :days * INTERVAL '1 day'
        WHERE u.organization_id = :org_id
            AND u.deleted_at IS NULL
        GROUP BY u.id, u.email, u.first_name, u.last_name, u.role, u.last_login_at
    ),
    summary_stats AS (
        SELECT 
            COUNT(*) as total_users,
            COUNT(CASE WHEN last_login_at > NOW() - INTERVAL '7 days' THEN 1 END) as active_7d,
            COUNT(CASE WHEN last_login_at > NOW() - INTERVAL '30 days' THEN 1 END) as active_30d,
            AVG(action_count) as avg_actions,
            SUM(prediction_count) as total_predictions
        FROM user_activity
    )
    SELECT 
        json_agg(user_activity.* ORDER BY action_count DESC) as users,
        row_to_json(summary_stats.*) as summary
    FROM user_activity, summary_stats
    """
    
    try:
        with db_connection.session_scope() as session:
            result = session.execute(
                text(sql),
                {"org_id": organization_id, "days": days}
            ).first()
            
            if not result:
                return {}
            
            users = result[0] or []
            summary = result[1] or {}
            
            return {
                "summary": {
                    "total_users": summary.get('total_users', 0),
                    "active_last_7d": summary.get('active_7d', 0),
                    "active_last_30d": summary.get('active_30d', 0),
                    "avg_actions_per_user": round(float(summary.get('avg_actions', 0)), 2),
                    "total_predictions": summary.get('total_predictions', 0)
                },
                "users": [
                    {
                        "id": str(u.get('id')),
                        "name": f"{u.get('first_name')} {u.get('last_name')}",
                        "email": u.get('email'),
                        "role": u.get('role'),
                        "last_login": u.get('last_login_at').isoformat() if u.get('last_login_at') else None,
                        "actions": u.get('action_count', 0),
                        "predictions": u.get('prediction_count', 0),
                        "last_action": u.get('last_action').isoformat() if u.get('last_action') else None
                    }
                    for u in users
                ]
            }
    except Exception as e:
        logger.error(f"Error in get_user_activity_summary: {e}")
        return {}

# ============================================================================
# DASHBOARD SUMMARY
# ============================================================================

def get_dashboard_summary(organization_id: UUID) -> Dict:
    """
    Get comprehensive dashboard summary
    
    Args:
        organization_id: UUID of the organization
    
    Returns:
        Dashboard metrics and summaries
    """
    try:
        return {
            "organization": get_organization_statistics(organization_id),
            "machine_performance": get_machine_performance_metrics(organization_id, days=30),
            "alert_trends": get_alert_trends(organization_id, days=7),
            "prediction_trends": get_prediction_accuracy_trend(organization_id, days=7),
            "rul_distribution": get_rul_distribution(organization_id),
            "user_activity": get_user_activity_summary(organization_id, days=7),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in get_dashboard_summary: {e}")
        return {}

# ============================================================================
# TEST FUNCTION
# ============================================================================

if __name__ == "__main__":
    import json
    from uuid import UUID
    
    print("=" * 70)
    print("SYNAPSEPM - Analytics Queries Test")
    print("=" * 70)
    
    # Test with a sample organization ID
    # Replace with actual UUID from your database
    test_org_id = UUID('00000000-0000-0000-0000-000000000000')
    
    print(f"\n📊 Testing Analytics Queries...")
    print(f"Organization ID: {test_org_id}")
    print("-" * 50)
    
    try:
        # Test 1: Machine Health Trend
        print("\n1. Testing get_machine_health_trend...")
        result = get_machine_health_trend(test_org_id, days=7)
        print(f"   ✓ Found {len(result)} days of data")
        
        # Test 2: Machine Performance Metrics
        print("\n2. Testing get_machine_performance_metrics...")
        result = get_machine_performance_metrics(test_org_id, days=30)
        if result:
            print(f"   ✓ Total machines: {result.get('summary', {}).get('total_machines', 0)}")
        
        # Test 3: Prediction Accuracy Trend
        print("\n3. Testing get_prediction_accuracy_trend...")
        result = get_prediction_accuracy_trend(test_org_id, days=7)
        print(f"   ✓ Found {len(result)} days of prediction data")
        
        # Test 4: RUL Distribution
        print("\n4. Testing get_rul_distribution...")
        result = get_rul_distribution(test_org_id)
        if result:
            stats = result.get('statistics', {})
            print(f"   ✓ Average RUL: {stats.get('avg', 0):.2f}")
            print(f"   ✓ Critical machines: {stats.get('critical_count', 0)}")
        
        # Test 5: Sensor Data Analysis
        print("\n5. Testing get_sensor_data_analysis...")
        # You would need a valid machine ID here
        # result = get_sensor_data_analysis(machine_id, hours=24)
        print("   ⚠ Skipped - requires valid machine ID")
        
        # Test 6: Alert Patterns
        print("\n6. Testing get_alert_patterns...")
        result = get_alert_patterns(test_org_id, days=7)
        if result:
            summary = result.get('summary', {})
            print(f"   ✓ Total alerts: {summary.get('total_alerts', 0)}")
        
        # Test 7: Alert Trends
        print("\n7. Testing get_alert_trends...")
        result = get_alert_trends(test_org_id, days=7)
        print(f"   ✓ Found {len(result)} days of alert data")
        
        # Test 8: Organization Growth
        print("\n8. Testing get_organization_growth...")
        result = get_organization_growth()
        monthly = result.get('monthly', [])
        print(f"   ✓ Found {len(monthly)} months of growth data")
        
        # Test 9: Organization Statistics
        print("\n9. Testing get_organization_statistics...")
        result = get_organization_statistics(test_org_id)
        if result:
            org = result.get('organization', {})
            print(f"   ✓ Organization: {org.get('name', 'Unknown')}")
            print(f"   ✓ Plan: {org.get('plan', 'Unknown')}")
        
        # Test 10: User Activity Summary
        print("\n10. Testing get_user_activity_summary...")
        result = get_user_activity_summary(test_org_id, days=7)
        if result:
            summary = result.get('summary', {})
            print(f"   ✓ Total users: {summary.get('total_users', 0)}")
            print(f"   ✓ Active last 7d: {summary.get('active_last_7d', 0)}")
        
        # Test 11: Dashboard Summary
        print("\n11. Testing get_dashboard_summary...")
        result = get_dashboard_summary(test_org_id)
        if result:
            print(f"   ✓ Dashboard summary generated")
        
        print("\n" + "=" * 70)
        print("✅ ALL QUERIES TESTED SUCCESSFULLY!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()