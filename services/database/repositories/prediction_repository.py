"""
SynapsePM - Prediction Repository
Data access layer for Prediction operations
"""

from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from ..models import Prediction, Machine, User, Organization, Alert, AuditLog
from ..connection import db_connection

class PredictionRepository:
    """Repository for Prediction data operations"""
    
    def __init__(self):
        self.db = db_connection
    
    def create_prediction(self, prediction_data: Dict) -> Prediction:
        """Create a new prediction"""
        with self.db.session_scope() as session:
            prediction = Prediction(**prediction_data)
            session.add(prediction)
            session.flush()
            
            # Create audit log
            audit = AuditLog(
                organization_id=prediction.organization_id,
                user_id=prediction.user_id,
                action='CREATE',
                action_status='success',
                resource_type='prediction',
                resource_id=prediction.id,
                resource_name=f"Prediction for machine {prediction.machine_id}",
                new_values=prediction.to_dict()
            )
            session.add(audit)
            
            session.commit()
            
            return prediction
    
    def get_prediction_by_id(self, prediction_id: UUID, 
                            organization_id: Optional[UUID] = None) -> Optional[Prediction]:
        """Get prediction by ID"""
        with self.db.session_scope() as session:
            query = session.query(Prediction).filter(
                Prediction.id == prediction_id,
                Prediction.deleted_at.is_(None)
            )
            
            if organization_id:
                query = query.filter(Prediction.organization_id == organization_id)
            
            return query.first()
    
    def get_predictions_for_machine(self, machine_id: UUID,
                                   limit: int = 100,
                                   offset: int = 0) -> List[Prediction]:
        """Get all predictions for a machine"""
        with self.db.session_scope() as session:
            return session.query(Prediction).filter(
                Prediction.machine_id == machine_id,
                Prediction.deleted_at.is_(None)
            ).order_by(desc(Prediction.created_at)).offset(offset).limit(limit).all()
    
    def get_latest_prediction(self, machine_id: UUID) -> Optional[Prediction]:
        """Get the most recent prediction for a machine"""
        with self.db.session_scope() as session:
            return session.query(Prediction).filter(
                Prediction.machine_id == machine_id,
                Prediction.deleted_at.is_(None)
            ).order_by(desc(Prediction.created_at)).first()
    
    def get_predictions_by_date_range(self, organization_id: UUID,
                                     start_date: datetime,
                                     end_date: datetime,
                                     machine_id: Optional[UUID] = None) -> List[Prediction]:
        """Get predictions within a date range"""
        with self.db.session_scope() as session:
            query = session.query(Prediction).filter(
                Prediction.organization_id == organization_id,
                Prediction.deleted_at.is_(None),
                Prediction.created_at.between(start_date, end_date)
            )
            
            if machine_id:
                query = query.filter(Prediction.machine_id == machine_id)
            
            return query.order_by(desc(Prediction.created_at)).all()
    
    def update_prediction_feedback(self, prediction_id: UUID,
                                  actual_rul: float,
                                  user_rating: Optional[int] = None,
                                  feedback_notes: Optional[str] = None) -> Optional[Prediction]:
        """Update prediction with actual outcome for model improvement"""
        with self.db.session_scope() as session:
            prediction = session.query(Prediction).get(prediction_id)
            
            if not prediction:
                return None
            
            prediction.actual_rul = actual_rul
            prediction.prediction_error = prediction.rul_value - actual_rul
            
            if user_rating:
                prediction.user_rating = user_rating
            if feedback_notes:
                prediction.feedback_notes = feedback_notes
            
            session.commit()
            
            return prediction
    
    def get_prediction_stats(self, organization_id: UUID,
                           days: int = 30) -> Dict:
        """Get prediction statistics for dashboard"""
        with self.db.session_scope() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            
            # Basic stats
            stats = session.query(
                func.count(Prediction.id).label('total_predictions'),
                func.avg(Prediction.confidence_score).label('avg_confidence'),
                func.avg(Prediction.prediction_error).label('avg_error'),
                func.avg(Prediction.processing_time_ms).label('avg_latency')
            ).filter(
                Prediction.organization_id == organization_id,
                Prediction.deleted_at.is_(None),
                Prediction.created_at >= cutoff
            ).first()
            
            # Status breakdown
            status_counts = session.query(
                Prediction.prediction_status,
                func.count(Prediction.id)
            ).filter(
                Prediction.organization_id == organization_id,
                Prediction.deleted_at.is_(None),
                Prediction.created_at >= cutoff
            ).group_by(Prediction.prediction_status).all()
            
            # Risk level breakdown
            risk_counts = session.query(
                Prediction.risk_level,
                func.count(Prediction.id)
            ).filter(
                Prediction.organization_id == organization_id,
                Prediction.deleted_at.is_(None),
                Prediction.created_at >= cutoff
            ).group_by(Prediction.risk_level).all()
            
            # Daily trend
            daily_trend = session.query(
                func.date_trunc('day', Prediction.created_at).label('day'),
                func.count(Prediction.id).label('count'),
                func.avg(Prediction.confidence_score).label('avg_confidence')
            ).filter(
                Prediction.organization_id == organization_id,
                Prediction.deleted_at.is_(None),
                Prediction.created_at >= cutoff
            ).group_by('day').order_by('day').all()
            
            return {
                'total_predictions': stats[0] or 0,
                'avg_confidence': float(stats[1]) if stats[1] else 0,
                'avg_error': float(stats[2]) if stats[2] else 0,
                'avg_latency_ms': float(stats[3]) if stats[3] else 0,
                'by_status': {status: count for status, count in status_counts},
                'by_risk': {risk: count for risk, count in risk_counts},
                'daily_trend': [
                    {'date': day.isoformat(), 'count': count, 'confidence': float(conf)}
                    for day, count, conf in daily_trend
                ]
            }
    
    def get_underperforming_models(self, organization_id: UUID,
                                  threshold: float = 0.7) -> List[Dict]:
        """Get models with low confidence scores"""
        with self.db.session_scope() as session:
            results = session.query(
                Prediction.model_version,
                func.count(Prediction.id).label('total'),
                func.avg(Prediction.confidence_score).label('avg_confidence'),
                func.avg(Prediction.prediction_error).label('avg_error')
            ).filter(
                Prediction.organization_id == organization_id,
                Prediction.deleted_at.is_(None),
                Prediction.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
            ).group_by(Prediction.model_version).having(
                func.avg(Prediction.confidence_score) < threshold
            ).all()
            
            return [
                {
                    'model_version': r[0],
                    'total_predictions': r[1],
                    'avg_confidence': float(r[2]),
                    'avg_error': float(r[3])
                }
                for r in results
            ]

# Singleton instance
prediction_repository = PredictionRepository()