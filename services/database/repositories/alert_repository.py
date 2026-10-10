"""
SynapsePM - Alert Repository
Data access layer for Alert operations
"""

from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

from ..models import Alert, User, Machine, AuditLog
from ..connection import db_connection

class AlertRepository:
    """Repository for Alert data operations"""
    
    def __init__(self):
        self.db = db_connection
    
    def create_alert(self, alert_data: Dict) -> Alert:
        """Create a new alert"""
        with self.db.session_scope() as session:
            alert = Alert(**alert_data)
            session.add(alert)
            session.flush()
            
            # Create audit log
            audit = AuditLog(
                organization_id=alert.organization_id,
                user_id=alert.user_id,
                action='CREATE',
                action_status='success',
                resource_type='alert',
                resource_id=alert.id,
                resource_name=alert.title,
                new_values=alert.to_dict()
            )
            session.add(audit)
            
            session.commit()
            return alert
    
    def get_alert_by_id(self, alert_id: UUID, organization_id: Optional[UUID] = None) -> Optional[Alert]:
        """Get alert by ID"""
        with self.db.session_scope() as session:
            query = session.query(Alert).filter(
                Alert.id == alert_id,
                Alert.deleted_at.is_(None)
            )
            
            if organization_id:
                query = query.filter(Alert.organization_id == organization_id)
            
            return query.first()
    
    def get_alerts_for_user(self, user_id: UUID, 
                           status: Optional[str] = None,
                           severity: Optional[str] = None,
                           limit: int = 50) -> List[Alert]:
        """Get alerts for a specific user"""
        with self.db.session_scope() as session:
            query = session.query(Alert).filter(
                Alert.user_id == user_id,
                Alert.deleted_at.is_(None)
            )
            
            if status:
                query = query.filter(Alert.alert_status == status)
            
            if severity:
                query = query.filter(Alert.severity == severity)
            
            return query.order_by(
                desc(Alert.priority),
                desc(Alert.created_at)
            ).limit(limit).all()
    
    def get_alerts_for_machine(self, machine_id: UUID,
                              unresolved_only: bool = True,
                              limit: int = 100) -> List[Alert]:
        """Get alerts for a specific machine"""
        with self.db.session_scope() as session:
            query = session.query(Alert).filter(
                Alert.machine_id == machine_id,
                Alert.deleted_at.is_(None)
            )
            
            if unresolved_only:
                query = query.filter(Alert.is_resolved == False)
            
            return query.order_by(
                desc(Alert.priority),
                desc(Alert.created_at)
            ).limit(limit).all()
    
    def get_active_alerts(self, organization_id: UUID,
                         severity: Optional[str] = None,
                         limit: int = 100) -> List[Alert]:
        """Get all active (unresolved) alerts for organization"""
        with self.db.session_scope() as session:
            query = session.query(Alert).filter(
                Alert.organization_id == organization_id,
                Alert.deleted_at.is_(None),
                Alert.is_resolved == False
            )
            
            if severity:
                query = query.filter(Alert.severity == severity)
            
            return query.order_by(
                desc(Alert.priority),
                desc(Alert.created_at)
            ).limit(limit).all()
    
    def acknowledge_alert(self, alert_id: UUID, user_id: UUID,
                         notes: Optional[str] = None) -> Optional[Alert]:
        """Acknowledge an alert"""
        with self.db.session_scope() as session:
            alert = session.query(Alert).get(alert_id)
            
            if not alert:
                return None
            
            alert.is_acknowledged = True
            alert.acknowledged_at = datetime.now(timezone.utc)
            alert.acknowledged_by_id = user_id
            if notes:
                alert.acknowledgment_notes = notes
            
            # Create audit log
            audit = AuditLog(
                organization_id=alert.organization_id,
                user_id=user_id,
                action='ACKNOWLEDGE',
                action_status='success',
                resource_type='alert',
                resource_id=alert.id,
                resource_name=alert.title
            )
            session.add(audit)
            
            session.commit()
            return alert
    
    def resolve_alert(self, alert_id: UUID, user_id: UUID,
                     resolution_notes: Optional[str] = None) -> Optional[Alert]:
        """Resolve an alert"""
        with self.db.session_scope() as session:
            alert = session.query(Alert).get(alert_id)
            
            if not alert:
                return None
            
            alert.is_resolved = True
            alert.resolved_at = datetime.now(timezone.utc)
            alert.resolved_by_id = user_id
            
            # Calculate resolution time
            if alert.created_at:
                resolution_time = (alert.resolved_at - alert.created_at).total_seconds() / 60
                alert.resolution_time_minutes = int(resolution_time)
            
            if resolution_notes:
                alert.resolution_notes = resolution_notes
            
            # Create audit log
            audit = AuditLog(
                organization_id=alert.organization_id,
                user_id=user_id,
                action='RESOLVE',
                action_status='success',
                resource_type='alert',
                resource_id=alert.id,
                resource_name=alert.title
            )
            session.add(audit)
            
            session.commit()
            return alert
    
    def escalate_alert(self, alert_id: UUID, escalate_to_id: UUID,
                      user_id: UUID, notes: Optional[str] = None) -> Optional[Alert]:
        """Escalate an alert to another user"""
        with self.db.session_scope() as session:
            alert = session.query(Alert).get(alert_id)
            
            if not alert:
                return None
            
            alert.is_escalated = True
            alert.escalated_to_id = escalate_to_id
            alert.escalated_at = datetime.now(timezone.utc)
            alert.escalation_level = (alert.escalation_level or 0) + 1
            
            if notes:
                alert.acknowledgment_notes = notes
            
            # Create audit log
            audit = AuditLog(
                organization_id=alert.organization_id,
                user_id=user_id,
                action='ESCALATE',
                action_status='success',
                resource_type='alert',
                resource_id=alert.id,
                resource_name=alert.title,
                new_values={'escalated_to': str(escalate_to_id)}
            )
            session.add(audit)
            
            session.commit()
            return alert
    
    def mark_as_read(self, alert_id: UUID, user_id: UUID) -> Optional[Alert]:
        """Mark alert as read"""
        with self.db.session_scope() as session:
            alert = session.query(Alert).filter(
                Alert.id == alert_id,
                Alert.user_id == user_id
            ).first()
            
            if not alert:
                return None
            
            alert.is_read = True
            alert.read_at = datetime.now(timezone.utc)
            
            session.commit()
            return alert
    
    def get_alert_stats(self, organization_id: UUID, days: int = 30) -> Dict:
        """Get alert statistics for dashboard"""
        with self.db.session_scope() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Basic stats
            stats = session.query(
                func.count(Alert.id).label('total_alerts'),
                func.sum(case([(Alert.is_resolved == False, 1)], else_=0)).label('active_alerts'),
                func.avg(Alert.resolution_time_minutes).label('avg_resolution_time')
            ).filter(
                Alert.organization_id == organization_id,
                Alert.deleted_at.is_(None),
                Alert.created_at >= cutoff
            ).first()
            
            # Severity breakdown
            severity_counts = session.query(
                Alert.severity,
                func.count(Alert.id)
            ).filter(
                Alert.organization_id == organization_id,
                Alert.deleted_at.is_(None),
                Alert.created_at >= cutoff
            ).group_by(Alert.severity).all()
            
            # Type breakdown
            type_counts = session.query(
                Alert.alert_type,
                func.count(Alert.id)
            ).filter(
                Alert.organization_id == organization_id,
                Alert.deleted_at.is_(None),
                Alert.created_at >= cutoff
            ).group_by(Alert.alert_type).all()
            
            # Daily trend
            daily_trend = session.query(
                func.date_trunc('day', Alert.created_at).label('day'),
                func.count(Alert.id).label('count'),
                func.sum(case([(Alert.severity == 'critical', 1)], else_=0)).label('critical_count')
            ).filter(
                Alert.organization_id == organization_id,
                Alert.deleted_at.is_(None),
                Alert.created_at >= cutoff
            ).group_by('day').order_by('day').all()
            
            # SLA compliance
            sla_stats = session.query(
                func.avg(case([(Alert.sla_breached == False, 1)], else_=0)).label('sla_compliance'),
                func.count(Alert.id).filter(Alert.sla_breached == True).label('sla_breaches')
            ).filter(
                Alert.organization_id == organization_id,
                Alert.deleted_at.is_(None),
                Alert.created_at >= cutoff
            ).first()
            
            return {
                'total_alerts': stats[0] or 0,
                'active_alerts': stats[1] or 0,
                'avg_resolution_time_minutes': float(stats[2]) if stats[2] else 0,
                'by_severity': {sev: count for sev, count in severity_counts},
                'by_type': {typ: count for typ, count in type_counts},
                'daily_trend': [
                    {
                        'date': day.isoformat(),
                        'total': count,
                        'critical': critical
                    }
                    for day, count, critical in daily_trend
                ],
                'sla_compliance': float(sla_stats[0]) if sla_stats[0] else 100,
                'sla_breaches': sla_stats[1] or 0
            }
    
    def bulk_resolve_alerts(self, alert_ids: List[UUID], user_id: UUID,
                           resolution_notes: Optional[str] = None) -> int:
        """Bulk resolve multiple alerts"""
        with self.db.session_scope() as session:
            now = datetime.now(timezone.utc)
            
            result = session.query(Alert).filter(
                Alert.id.in_(alert_ids),
                Alert.deleted_at.is_(None)
            ).update({
                Alert.is_resolved: True,
                Alert.resolved_at: now,
                Alert.resolved_by_id: user_id,
                Alert.resolution_notes: resolution_notes,
                Alert.updated_at: now
            }, synchronize_session=False)
            
            if result > 0:
                # Create bulk audit log
                audit = AuditLog(
                    organization_id=None,  # Will need to be determined
                    user_id=user_id,
                    action='BULK_RESOLVE',
                    action_status='success',
                    resource_type='alert',
                    resource_name=f"Bulk resolved {result} alerts",
                    new_values={'resolved_ids': [str(id) for id in alert_ids]}
                )
                session.add(audit)
                session.commit()
            
            return result

# Singleton instance
alert_repository = AlertRepository()