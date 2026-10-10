"""
SynapsePM - Machine Repository
Data access layer for Machine operations
"""

import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import text, and_, or_, func, desc, asc, case
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError

# ===== FIX: Add absolute import path =====
# Get project root and add to path
_current_file = Path(__file__).resolve()
_repositories_dir = _current_file.parent
_database_dir = _repositories_dir.parent
_services_dir = _database_dir.parent
_project_root = _services_dir.parent

if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Use absolute imports
from services.database.connection import db_connection
from services.database.models import (
    Machine, MachineData, User, Organization, Alert, AuditLog, Prediction
)
# ===== End of fix =====

import logging

logger = logging.getLogger(__name__)

class MachineRepository:
    """Repository for Machine data operations"""
    
    def __init__(self):
        self.db = db_connection
    
    def create_machine(self, organization_id: UUID, created_by_id: UUID, machine_data: Dict) -> Optional[Machine]:
        """Create a new machine"""
        try:
            with self.db.session_scope() as session:
                # Check organization exists
                org = session.query(Organization).filter(
                    Organization.id == organization_id,
                    Organization.deleted_at.is_(None)
                ).first()
                
                if not org:
                    raise ValueError(f"Organization {organization_id} not found")
                
                # Check machine limit
                machine_count = session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None)
                ).count()
                
                if machine_count >= org.max_machines:
                    raise ValueError(f"Organization machine limit reached ({org.max_machines})")
                
                # Create machine
                machine = Machine(
                    organization_id=organization_id,
                    created_by_id=created_by_id,
                    name=machine_data.get('name'),
                    machine_type=machine_data.get('machine_type'),
                    manufacturer=machine_data.get('manufacturer'),
                    model=machine_data.get('model'),
                    serial_number=machine_data.get('serial_number'),
                    asset_tag=machine_data.get('asset_tag'),
                    location=machine_data.get('location'),
                    status=machine_data.get('status', 'offline'),
                    health_status=machine_data.get('health_status', 'unknown'),
                    is_critical=machine_data.get('is_critical', False),
                    temperature=machine_data.get('temperature'),
                    vibration=machine_data.get('vibration'),
                    rpm=machine_data.get('rpm'),
                    current=machine_data.get('current'),
                    pressure=machine_data.get('pressure'),
                    voltage=machine_data.get('voltage'),
                    power=machine_data.get('power'),
                    operational_hours=machine_data.get('operational_hours', 0),
                    description=machine_data.get('description'),
                    specifications=machine_data.get('specifications', {}),
                    machine_metadata=machine_data.get('machine_metadata', {})
                )
                
                session.add(machine)
                session.flush()
                
                # Update organization machine count
                org.current_machines = machine_count + 1
                
                # Create audit log
                audit = AuditLog(
                    organization_id=organization_id,
                    user_id=created_by_id,
                    action='CREATE_MACHINE',
                    action_status='success',
                    resource_type='machine',
                    resource_id=machine.id,
                    resource_name=machine.name,
                    new_values=machine.to_dict() if hasattr(machine, 'to_dict') else {},
                    ip_address=machine_data.get('ip_address'),
                    user_agent=machine_data.get('user_agent'),
                    security_level='normal'
                )
                session.add(audit)
                
                session.commit()
                logger.info(f"Machine created: {machine.id} for org {organization_id}")
                
                return machine
                
        except Exception as e:
            logger.error(f"Error creating machine: {e}")
            return None
    
    def get_machine_by_id(self, machine_id: UUID, organization_id: Optional[UUID] = None) -> Optional[Machine]:
        """Get machine by ID, optionally verify organization"""
        try:
            with self.db.session_scope() as session:
                query = session.query(Machine).filter(
                    Machine.id == machine_id,
                    Machine.deleted_at.is_(None)
                )
                
                if organization_id:
                    query = query.filter(Machine.organization_id == organization_id)
                
                return query.options(
                    joinedload(Machine.organization),
                    joinedload(Machine.creator)
                ).first()
        except Exception as e:
            logger.error(f"Error getting machine {machine_id}: {e}")
            return None
    
    def get_machines_by_organization(self, 
                                    organization_id: UUID,
                                    status: Optional[str] = None,
                                    machine_type: Optional[str] = None,
                                    health_status: Optional[str] = None,
                                    skip: int = 0, 
                                    limit: int = 100) -> List[Machine]:
        """Get all machines in an organization with filters"""
        try:
            with self.db.session_scope() as session:
                query = session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None)
                )
                
                if status:
                    query = query.filter(Machine.status == status)
                
                if machine_type:
                    query = query.filter(Machine.machine_type == machine_type)
                
                if health_status:
                    query = query.filter(Machine.health_status == health_status)
                
                return query.options(
                    joinedload(Machine.creator)
                ).order_by(Machine.created_at.desc()).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Error getting machines for org {organization_id}: {e}")
            return []
    
    def update_machine(self, machine_id: UUID, user_id: UUID, updates: Dict) -> Optional[Machine]:
        """Update machine information"""
        try:
            with self.db.session_scope() as session:
                machine = session.query(Machine).filter(
                    Machine.id == machine_id,
                    Machine.deleted_at.is_(None)
                ).first()
                
                if not machine:
                    return None
                
                # Store old values for audit
                old_values = machine.to_dict() if hasattr(machine, 'to_dict') else {}
                changed_fields = []
                
                # Apply updates
                for key, value in updates.items():
                    if hasattr(machine, key) and value is not None:
                        old_value = getattr(machine, key)
                        if old_value != value:
                            setattr(machine, key, value)
                            changed_fields.append(key)
                
                if changed_fields:
                    # Create audit log
                    audit = AuditLog(
                        organization_id=machine.organization_id,
                        user_id=user_id,
                        action='UPDATE_MACHINE',
                        action_status='success',
                        resource_type='machine',
                        resource_id=machine.id,
                        resource_name=machine.name,
                        old_values=old_values,
                        new_values=machine.to_dict() if hasattr(machine, 'to_dict') else {},
                        changed_fields=changed_fields,
                        ip_address=updates.get('ip_address'),
                        user_agent=updates.get('user_agent'),
                        security_level='normal'
                    )
                    session.add(audit)
                    session.commit()
                
                return machine
                
        except Exception as e:
            logger.error(f"Error updating machine {machine_id}: {e}")
            return None
    
    def delete_machine(self, machine_id: UUID, user_id: UUID, hard_delete: bool = False) -> bool:
        """Soft or hard delete machine"""
        try:
            with self.db.session_scope() as session:
                machine = session.query(Machine).filter(Machine.id == machine_id).first()
                
                if not machine:
                    return False
                
                if hard_delete:
                    # Hard delete - also delete related records
                    session.query(MachineData).filter(MachineData.machine_id == machine_id).delete()
                    session.delete(machine)
                else:
                    # Soft delete
                    machine.soft_delete()
                    
                    # Update organization count
                    org = session.query(Organization).get(machine.organization_id)
                    if org:
                        org.current_machines = max(0, org.current_machines - 1)
                    
                    # Create audit log
                    audit = AuditLog(
                        organization_id=machine.organization_id,
                        user_id=user_id,
                        action='DELETE_MACHINE',
                        action_status='success',
                        resource_type='machine',
                        resource_id=machine.id,
                        resource_name=machine.name,
                        old_values=machine.to_dict() if hasattr(machine, 'to_dict') else {},
                        security_level='normal'
                    )
                    session.add(audit)
                
                session.commit()
                logger.info(f"Machine {machine_id} {'hard' if hard_delete else 'soft'} deleted")
                return True
                
        except Exception as e:
            logger.error(f"Error deleting machine {machine_id}: {e}")
            return False
    
    def update_sensor_data(self, machine_id: UUID, sensor_readings: Dict) -> Optional[MachineData]:
        """Add new sensor reading and update machine current values"""
        try:
            with self.db.session_scope() as session:
                # Check if machine exists
                machine = session.query(Machine).filter(
                    Machine.id == machine_id,
                    Machine.deleted_at.is_(None)
                ).first()
                
                if not machine:
                    return None
                
                # Create sensor data record
                sensor_data = MachineData(
                    machine_id=machine_id,
                    timestamp=sensor_readings.get('timestamp', datetime.now(timezone.utc)),
                    temperature=sensor_readings.get('temperature'),
                    vibration=sensor_readings.get('vibration'),
                    rpm=sensor_readings.get('rpm'),
                    current=sensor_readings.get('current'),
                    pressure=sensor_readings.get('pressure'),
                    voltage=sensor_readings.get('voltage'),
                    power=sensor_readings.get('power'),
                    additional_sensors=sensor_readings.get('additional_sensors', {}),
                    data_quality_score=sensor_readings.get('data_quality_score'),
                    is_anomaly=sensor_readings.get('is_anomaly', False)
                )
                session.add(sensor_data)
                
                # Update machine current values
                for key, value in sensor_readings.items():
                    if hasattr(machine, key) and key not in ['timestamp', 'additional_sensors', 'data_quality_score', 'is_anomaly']:
                        if value is not None:
                            setattr(machine, key, value)
                
                machine.last_reading_at = datetime.now(timezone.utc)
                
                session.commit()
                logger.info(f"Sensor data added for machine {machine_id}")
                
                return sensor_data
                
        except Exception as e:
            logger.error(f"Error updating sensor data for machine {machine_id}: {e}")
            return None
    
    def get_sensor_history(self, machine_id: UUID, 
                          start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None,
                          limit: int = 1000) -> List[MachineData]:
        """Get sensor data history for a machine"""
        try:
            with self.db.session_scope() as session:
                query = session.query(MachineData).filter(
                    MachineData.machine_id == machine_id
                )
                
                if start_time:
                    query = query.filter(MachineData.timestamp >= start_time)
                if end_time:
                    query = query.filter(MachineData.timestamp <= end_time)
                
                return query.order_by(MachineData.timestamp.desc()).limit(limit).all()
        except Exception as e:
            logger.error(f"Error getting sensor history for machine {machine_id}: {e}")
            return []
    
    def get_sensor_statistics(self, machine_id: UUID, 
                             start_time: Optional[datetime] = None,
                             end_time: Optional[datetime] = None) -> Dict:
        """Get sensor data statistics for a machine"""
        try:
            with self.db.session_scope() as session:
                query = session.query(
                    func.avg(MachineData.temperature).label('avg_temp'),
                    func.min(MachineData.temperature).label('min_temp'),
                    func.max(MachineData.temperature).label('max_temp'),
                    func.stddev(MachineData.temperature).label('std_temp'),
                    func.avg(MachineData.vibration).label('avg_vib'),
                    func.min(MachineData.vibration).label('min_vib'),
                    func.max(MachineData.vibration).label('max_vib'),
                    func.stddev(MachineData.vibration).label('std_vib'),
                    func.avg(MachineData.pressure).label('avg_press'),
                    func.min(MachineData.pressure).label('min_press'),
                    func.max(MachineData.pressure).label('max_press'),
                    func.stddev(MachineData.pressure).label('std_press'),
                    func.count(MachineData.id).label('reading_count'),
                    func.sum(case((MachineData.is_anomaly == True, 1), else_=0)).label('anomaly_count')
                ).filter(MachineData.machine_id == machine_id)
                
                if start_time:
                    query = query.filter(MachineData.timestamp >= start_time)
                if end_time:
                    query = query.filter(MachineData.timestamp <= end_time)
                
                result = query.first()
                
                if not result:
                    return {}
                
                return {
                    'temperature': {
                        'avg': float(result[0]) if result[0] else 0,
                        'min': float(result[1]) if result[1] else 0,
                        'max': float(result[2]) if result[2] else 0,
                        'std': float(result[3]) if result[3] else 0
                    },
                    'vibration': {
                        'avg': float(result[4]) if result[4] else 0,
                        'min': float(result[5]) if result[5] else 0,
                        'max': float(result[6]) if result[6] else 0,
                        'std': float(result[7]) if result[7] else 0
                    },
                    'pressure': {
                        'avg': float(result[8]) if result[8] else 0,
                        'min': float(result[9]) if result[9] else 0,
                        'max': float(result[10]) if result[10] else 0,
                        'std': float(result[11]) if result[11] else 0
                    },
                    'readings': result[12] or 0,
                    'anomalies': result[13] or 0,
                    'anomaly_rate': (result[13] / result[12] * 100) if result[12] and result[12] > 0 else 0
                }
        except Exception as e:
            logger.error(f"Error getting sensor statistics for machine {machine_id}: {e}")
            return {}
    
    def get_machines_due_for_maintenance(self, organization_id: UUID, days_ahead: int = 7) -> List[Machine]:
        """Get machines due for maintenance in the next X days"""
        try:
            with self.db.session_scope() as session:
                now = datetime.now(timezone.utc)
                cutoff = now + timedelta(days=days_ahead)
                
                return session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None),
                    Machine.next_maintenance_at <= cutoff,
                    Machine.next_maintenance_at >= now
                ).all()
        except Exception as e:
            logger.error(f"Error getting machines due for maintenance: {e}")
            return []
    
    def get_machine_stats(self, organization_id: UUID) -> Dict:
        """Get machine statistics for dashboard"""
        try:
            with self.db.session_scope() as session:
                # Total count
                total = session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None)
                ).count()
                
                # Status breakdown
                status_counts = session.query(
                    Machine.status,
                    func.count(Machine.id)
                ).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None)
                ).group_by(Machine.status).all()
                
                # Health breakdown
                health_counts = session.query(
                    Machine.health_status,
                    func.count(Machine.id)
                ).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None)
                ).group_by(Machine.health_status).all()
                
                # Critical machines
                critical_count = session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None),
                    Machine.health_status == 'critical'
                ).count()
                
                # Maintenance due
                maintenance_due = session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None),
                    Machine.next_maintenance_at <= datetime.now(timezone.utc)
                ).count()
                
                # Online/Offline
                online_count = session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None),
                    Machine.status == 'online'
                ).count()
                
                return {
                    'total_machines': total,
                    'online_machines': online_count,
                    'offline_machines': total - online_count,
                    'critical_machines': critical_count,
                    'maintenance_due': maintenance_due,
                    'status_breakdown': {status: count for status, count in status_counts},
                    'health_breakdown': {health: count for health, count in health_counts}
                }
        except Exception as e:
            logger.error(f"Error getting machine stats for org {organization_id}: {e}")
            return {}
    
    def bulk_update_machines(self, organization_id: UUID, user_id: UUID,
                            machine_ids: List[UUID], updates: Dict) -> int:
        """Bulk update multiple machines"""
        try:
            with self.db.session_scope() as session:
                count = session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.id.in_(machine_ids),
                    Machine.deleted_at.is_(None)
                ).update(updates, synchronize_session=False)
                
                if count > 0:
                    # Create audit log
                    audit = AuditLog(
                        organization_id=organization_id,
                        user_id=user_id,
                        action='BULK_UPDATE_MACHINES',
                        action_status='success',
                        resource_type='machine',
                        resource_name=f"Bulk update of {count} machines",
                        new_values=updates,
                        security_level='normal'
                    )
                    session.add(audit)
                    session.commit()
                
                return count
        except Exception as e:
            logger.error(f"Error bulk updating machines: {e}")
            return 0
    
    def search_machines(self, organization_id: UUID, search_term: str, 
                        skip: int = 0, limit: int = 100) -> List[Machine]:
        """Search machines by name, serial number, or type"""
        try:
            with self.db.session_scope() as session:
                search = f"%{search_term}%"
                return session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None),
                    or_(
                        Machine.name.ilike(search),
                        Machine.serial_number.ilike(search),
                        Machine.machine_type.ilike(search),
                        Machine.manufacturer.ilike(search),
                        Machine.location.ilike(search)
                    )
                ).order_by(Machine.name).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Error searching machines: {e}")
            return []
    
    def get_latest_sensor_data(self, machine_id: UUID) -> Optional[MachineData]:
        """Get the latest sensor reading for a machine"""
        try:
            with self.db.session_scope() as session:
                return session.query(MachineData).filter(
                    MachineData.machine_id == machine_id
                ).order_by(MachineData.timestamp.desc()).first()
        except Exception as e:
            logger.error(f"Error getting latest sensor data: {e}")
            return None
    
    def get_machine_count_by_type(self, organization_id: UUID) -> Dict[str, int]:
        """Get machine count grouped by type"""
        try:
            with self.db.session_scope() as session:
                results = session.query(
                    Machine.machine_type,
                    func.count(Machine.id)
                ).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None)
                ).group_by(Machine.machine_type).all()
                
                return {machine_type or 'unknown': count for machine_type, count in results}
        except Exception as e:
            logger.error(f"Error getting machine count by type: {e}")
            return {}
    
    def get_critical_machines(self, organization_id: UUID) -> List[Machine]:
        """Get all critical machines"""
        try:
            with self.db.session_scope() as session:
                return session.query(Machine).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None),
                    Machine.is_critical == True
                ).all()
        except Exception as e:
            logger.error(f"Error getting critical machines: {e}")
            return []
    
    def get_machine_health_summary(self, organization_id: UUID) -> Dict:
        """Get machine health summary for dashboard"""
        try:
            with self.db.session_scope() as session:
                result = session.query(
                    func.count(Machine.id).label('total'),
                    func.sum(case((Machine.health_status == 'healthy', 1), else_=0)).label('healthy'),
                    func.sum(case((Machine.health_status == 'warning', 1), else_=0)).label('warning'),
                    func.sum(case((Machine.health_status == 'critical', 1), else_=0)).label('critical'),
                    func.sum(case((Machine.status == 'online', 1), else_=0)).label('online'),
                    func.sum(case((Machine.status == 'offline', 1), else_=0)).label('offline')
                ).filter(
                    Machine.organization_id == organization_id,
                    Machine.deleted_at.is_(None)
                ).first()
                
                if not result:
                    return {}
                
                return {
                    'total': result[0] or 0,
                    'healthy': result[1] or 0,
                    'warning': result[2] or 0,
                    'critical': result[3] or 0,
                    'online': result[4] or 0,
                    'offline': result[5] or 0,
                    'health_percentage': {
                        'healthy': ((result[1] or 0) / (result[0] or 1) * 100) if result[0] else 0,
                        'warning': ((result[2] or 0) / (result[0] or 1) * 100) if result[0] else 0,
                        'critical': ((result[3] or 0) / (result[0] or 1) * 100) if result[0] else 0
                    }
                }
        except Exception as e:
            logger.error(f"Error getting machine health summary: {e}")
            return {}
    
    def get_machine_predictions(self, machine_id: UUID, limit: int = 10) -> List[Prediction]:
        """Get latest predictions for a machine"""
        try:
            with self.db.session_scope() as session:
                return session.query(Prediction).filter(
                    Prediction.machine_id == machine_id,
                    Prediction.deleted_at.is_(None)
                ).order_by(Prediction.created_at.desc()).limit(limit).all()
        except Exception as e:
            logger.error(f"Error getting machine predictions: {e}")
            return []
    
    def get_machine_alerts(self, machine_id: UUID, active_only: bool = True, limit: int = 10) -> List[Alert]:
        """Get alerts for a machine"""
        try:
            with self.db.session_scope() as session:
                query = session.query(Alert).filter(
                    Alert.machine_id == machine_id,
                    Alert.deleted_at.is_(None)
                )
                
                if active_only:
                    query = query.filter(Alert.alert_status == 'active')
                
                return query.order_by(Alert.created_at.desc()).limit(limit).all()
        except Exception as e:
            logger.error(f"Error getting machine alerts: {e}")
            return []


# Singleton instance
machine_repository = MachineRepository()


# ===== Test section for direct execution =====
if __name__ == "__main__":
    print("=" * 70)
    print("Machine Repository - Test Mode")
    print("=" * 70)
    
    try:
        # Test database connection using health_check method
        print("\n📡 Testing database connection...")
        health = db_connection.health_check()
        
        if health.get('status') == 'healthy':
            print(f"✅ Database connected successfully")
            print(f"   Database: {health.get('details', {}).get('database', 'Unknown')}")
            print(f"   Active connections: {health.get('active_connections', 0)}")
            print(f"   Connection pool size: {health.get('connection_pool_size', 0)}")
        else:
            print(f"❌ Connection failed: {health.get('error', 'Unknown')}")
        
        print("\n✅ MachineRepository is ready")
        print(f"   Available methods: {[m for m in dir(machine_repository) if not m.startswith('_')]}")
        
        # Optional: Test getting first organization
        print("\n📊 Checking for existing organizations...")
        with db_connection.session_scope() as session:
            first_org = session.query(Organization).filter(
                Organization.deleted_at.is_(None)
            ).first()
            
            if first_org:
                print(f"   Found organization: {first_org.name}")
                print(f"   Machine stats: {machine_repository.get_machine_stats(first_org.id)}")
            else:
                print("   ⚠ No organizations found. Run models.py first to create test data.")
        
        print("\n" + "=" * 70)
        print("✅ Machine Repository Ready!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()