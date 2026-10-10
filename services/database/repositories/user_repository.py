"""
SynapsePM - User Repository
Data access layer for User operations
"""

from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from ..models import User, Organization, Activity, AuditLog
from ..connection import db_connection

class UserRepository:
    """Repository for User data operations"""
    
    def __init__(self):
        self.db = db_connection
    
    def create_user(self, organization_id: UUID, user_data: Dict) -> User:
        """Create a new user"""
        with self.db.session_scope() as session:
            # Check organization limits
            org = session.query(Organization).get(organization_id)
            if org and org.current_users >= org.max_users:
                raise ValueError(f"Organization user limit reached ({org.max_users})")
            
            # Create user
            user = User(
                organization_id=organization_id,
                **user_data
            )
            
            session.add(user)
            session.flush()
            
            # Update organization user count
            if org:
                org.current_users += 1
            
            # Create audit log
            audit = AuditLog(
                organization_id=organization_id,
                user_id=user.id,
                action='CREATE',
                action_status='success',
                resource_type='user',
                resource_id=user.id,
                resource_name=user.email,
                new_values=user.to_dict()
            )
            session.add(audit)
            
            session.commit()
            
            return user
    
    def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID"""
        with self.db.session_scope() as session:
            return session.query(User).filter(
                User.id == user_id,
                User.deleted_at.is_(None)
            ).first()
    
    def get_user_by_email(self, email: str, organization_id: Optional[UUID] = None) -> Optional[User]:
        """Get user by email, optionally within organization"""
        with self.db.session_scope() as session:
            query = session.query(User).filter(
                User.email == email,
                User.deleted_at.is_(None)
            )
            
            if organization_id:
                query = query.filter(User.organization_id == organization_id)
            
            return query.first()
    
    def get_users_by_organization(self, organization_id: UUID, 
                                  skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users in an organization with pagination"""
        with self.db.session_scope() as session:
            return session.query(User).filter(
                User.organization_id == organization_id,
                User.deleted_at.is_(None)
            ).order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    
    def update_user(self, user_id: UUID, updates: Dict) -> Optional[User]:
        """Update user information"""
        with self.db.session_scope() as session:
            user = session.query(User).filter(
                User.id == user_id,
                User.deleted_at.is_(None)
            ).first()
            
            if not user:
                return None
            
            # Store old values for audit
            old_values = user.to_dict(include_sensitive=True)
            
            # Apply updates
            for key, value in updates.items():
                if hasattr(user, key) and value is not None:
                    setattr(user, key, value)
            
            # Create audit log
            audit = AuditLog(
                organization_id=user.organization_id,
                user_id=user_id,
                action='UPDATE',
                action_status='success',
                resource_type='user',
                resource_id=user.id,
                resource_name=user.email,
                old_values=old_values,
                new_values=user.to_dict(include_sensitive=True),
                changed_fields=list(updates.keys())
            )
            session.add(audit)
            
            session.commit()
            
            return user
    
    def delete_user(self, user_id: UUID, hard_delete: bool = False) -> bool:
        """Soft or hard delete user"""
        with self.db.session_scope() as session:
            user = session.query(User).filter(User.id == user_id).first()
            
            if not user:
                return False
            
            if hard_delete:
                # Hard delete
                session.delete(user)
            else:
                # Soft delete
                user.soft_delete()
                
                # Update organization count
                org = session.query(Organization).get(user.organization_id)
                if org:
                    org.current_users -= 1
                
                # Create audit log
                audit = AuditLog(
                    organization_id=user.organization_id,
                    user_id=user_id,
                    action='DELETE',
                    action_status='success',
                    resource_type='user',
                    resource_id=user.id,
                    resource_name=user.email
                )
                session.add(audit)
            
            session.commit()
            return True
    
    def authenticate_user(self, email: str, password: str, organization_id: Optional[UUID] = None) -> Optional[User]:
        """Authenticate user with email and password"""
        with self.db.session_scope() as session:
            user = self.get_user_by_email(email, organization_id)
            
            if not user:
                return None
            
            # Check if account is locked
            if user.is_locked:
                if user.locked_until and user.locked_until > datetime.now(timezone.utc):
                    raise ValueError(f"Account locked until {user.locked_until}")
                else:
                    # Auto-unlock after timeout
                    user.is_locked = False
                    user.login_attempts = 0
            
            # Verify password
            if user.check_password(password):
                # Success - reset attempts
                user.reset_login_attempts()
                
                # Log activity
                activity = Activity(
                    organization_id=user.organization_id,
                    user_id=user.id,
                    activity_type='login',
                    description=f"User {user.email} logged in successfully"
                )
                session.add(activity)
                
                session.commit()
                return user
            else:
                # Failed attempt
                user.increment_login_attempts()
                session.commit()
                return None
    
    def search_users(self, organization_id: UUID, query: str, 
                    role: Optional[str] = None) -> List[User]:
        """Search users by name or email"""
        with self.db.session_scope() as session:
            search = f"%{query}%"
            
            q = session.query(User).filter(
                User.organization_id == organization_id,
                User.deleted_at.is_(None),
                or_(
                    User.email.ilike(search),
                    User.first_name.ilike(search),
                    User.last_name.ilike(search)
                )
            )
            
            if role:
                q = q.filter(User.role == role)
            
            return q.order_by(User.created_at.desc()).limit(50).all()
    
    def get_user_stats(self, organization_id: UUID) -> Dict:
        """Get user statistics for dashboard"""
        with self.db.session_scope() as session:
            total = session.query(User).filter(
                User.organization_id == organization_id,
                User.deleted_at.is_(None)
            ).count()
            
            active_today = session.query(User).filter(
                User.organization_id == organization_id,
                User.deleted_at.is_(None),
                User.last_login_at >= datetime.now(timezone.utc).date()
            ).count()
            
            by_role = session.query(
                User.role, 
                User.is_active,
                User.is_verified
            ).filter(
                User.organization_id == organization_id,
                User.deleted_at.is_(None)
            ).all()
            
            role_counts = {}
            active_count = 0
            verified_count = 0
            
            for role, is_active, is_verified in by_role:
                role_counts[role] = role_counts.get(role, 0) + 1
                if is_active:
                    active_count += 1
                if is_verified:
                    verified_count += 1
            
            return {
                'total_users': total,
                'active_today': active_today,
                'active_users': active_count,
                'verified_users': verified_count,
                'by_role': role_counts
            }

# Singleton instance
user_repository = UserRepository()