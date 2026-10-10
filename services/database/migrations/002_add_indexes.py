"""
SynapsePM - Add Performance Indexes
Optimizes database queries for production
"""

from alembic import op

revision = '002_add_indexes'
down_revision = '001_initial'
branch_labels = None
depends_on = None

def upgrade():
    """Add performance indexes"""
    
    # Organizations indexes
    op.create_index('idx_organizations_name', 'organizations', ['name'], 
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_organizations_subdomain', 'organizations', ['subdomain'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_organizations_plan', 'organizations', ['plan'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    
    # Users indexes
    op.create_index('idx_users_email', 'users', ['email'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_users_organization_id', 'users', ['organization_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_users_role', 'users', ['role'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_users_last_login', 'users', ['last_login_at'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    
    # Machines indexes
    op.create_index('idx_machines_organization_id', 'machines', ['organization_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_machines_status', 'machines', ['status'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_machines_health', 'machines', ['health_status'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_machines_next_maintenance', 'machines', ['next_maintenance_at'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    
    # Machine data indexes (with partial indexing for performance)
    op.create_index('idx_machine_data_machine_time', 'machine_data', 
                   ['machine_id', sa.text('timestamp DESC')])
    op.create_index('idx_machine_data_timestamp', 'machine_data', 
                   [sa.text('timestamp DESC')])
    op.create_index('idx_machine_data_anomaly', 'machine_data', 
                   ['machine_id'], 
                   postgresql_where=sa.text('is_anomaly = true'))
    
    # Predictions indexes
    op.create_index('idx_predictions_machine_id', 'predictions', ['machine_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_predictions_user_id', 'predictions', ['user_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_predictions_org_id', 'predictions', ['organization_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_predictions_status', 'predictions', ['prediction_status'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_predictions_created_at', 'predictions', 
                   [sa.text('created_at DESC')],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    
    # Alerts indexes
    op.create_index('idx_alerts_user_id', 'alerts', ['user_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_alerts_machine_id', 'alerts', ['machine_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_alerts_org_id', 'alerts', ['organization_id'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_alerts_severity', 'alerts', ['severity'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_alerts_status', 'alerts', ['alert_status'],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_alerts_created_at', 'alerts', 
                   [sa.text('created_at DESC')],
                   postgresql_where=sa.text('deleted_at IS NULL'))
    
    # Audit logs indexes
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_org_id', 'audit_logs', ['organization_id'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'])
    op.create_index('idx_audit_created', 'audit_logs', [sa.text('created_at DESC')])

def downgrade():
    """Remove indexes"""
    
    op.drop_index('idx_audit_created')
    op.drop_index('idx_audit_resource')
    op.drop_index('idx_audit_action')
    op.drop_index('idx_audit_org_id')
    op.drop_index('idx_audit_user_id')
    op.drop_index('idx_alerts_created_at')
    op.drop_index('idx_alerts_status')
    op.drop_index('idx_alerts_severity')
    op.drop_index('idx_alerts_org_id')
    op.drop_index('idx_alerts_machine_id')
    op.drop_index('idx_alerts_user_id')
    op.drop_index('idx_predictions_created_at')
    op.drop_index('idx_predictions_status')
    op.drop_index('idx_predictions_org_id')
    op.drop_index('idx_predictions_user_id')
    op.drop_index('idx_predictions_machine_id')
    op.drop_index('idx_machine_data_anomaly')
    op.drop_index('idx_machine_data_timestamp')
    op.drop_index('idx_machine_data_machine_time')
    op.drop_index('idx_machines_next_maintenance')
    op.drop_index('idx_machines_health')
    op.drop_index('idx_machines_status')
    op.drop_index('idx_machines_organization_id')
    op.drop_index('idx_users_last_login')
    op.drop_index('idx_users_role')
    op.drop_index('idx_users_organization_id')
    op.drop_index('idx_users_email')
    op.drop_index('idx_organizations_plan')
    op.drop_index('idx_organizations_subdomain')
    op.drop_index('idx_organizations_name')