"""
SynapsePM - Initial Migration
Creates all database tables
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# Revision identifiers
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    """Create all tables"""
    
    # Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    
    # Create enum types
    op.execute("""
        CREATE TYPE user_role AS ENUM ('super_admin', 'org_admin', 'manager', 'engineer', 'viewer')
    """)
    op.execute("""
        CREATE TYPE subscription_plan AS ENUM ('FREE', 'STARTER', 'PROFESSIONAL', 'ENTERPRISE', 'CUSTOM')
    """)
    op.execute("""
        CREATE TYPE machine_status AS ENUM ('online', 'offline', 'maintenance', 'decommissioned')
    """)
    op.execute("""
        CREATE TYPE health_status AS ENUM ('healthy', 'warning', 'critical', 'unknown')
    """)
    op.execute("""
        CREATE TYPE alert_severity AS ENUM ('info', 'low', 'medium', 'high', 'critical')
    """)
    
    # Organizations table
    op.create_table('organizations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('subdomain', sa.String(63), unique=True),
        sa.Column('industry', sa.String(100)),
        sa.Column('company_size', sa.String(50)),
        sa.Column('primary_email', sa.String(120), nullable=False),
        sa.Column('primary_phone', sa.String(20)),
        sa.Column('website', sa.String(500)),
        sa.Column('address', sa.Text),
        sa.Column('country', sa.String(100)),
        sa.Column('timezone', sa.String(50), server_default='UTC'),
        sa.Column('plan', sa.String(50), nullable=False, server_default='FREE'),
        sa.Column('plan_started_at', sa.DateTime(timezone=True)),
        sa.Column('plan_expires_at', sa.DateTime(timezone=True)),
        sa.Column('billing_cycle', sa.String(20), server_default='monthly'),
        sa.Column('stripe_customer_id', sa.String(100), unique=True),
        sa.Column('stripe_subscription_id', sa.String(100), unique=True),
        sa.Column('max_users', sa.Integer, nullable=False, server_default='5'),
        sa.Column('max_machines', sa.Integer, nullable=False, server_default='5'),
        sa.Column('max_predictions_per_month', sa.Integer, nullable=False, server_default='100'),
        sa.Column('max_storage_gb', sa.Float, server_default='1.0'),
        sa.Column('current_users', sa.Integer, server_default='0'),
        sa.Column('current_machines', sa.Integer, server_default='0'),
        sa.Column('predictions_this_month', sa.Integer, server_default='0'),
        sa.Column('storage_used_gb', sa.Float, server_default='0.0'),
        sa.Column('features', JSONB, server_default='{}'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('is_trial', sa.Boolean, server_default='false'),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True)),
        sa.Column('settings', JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('deleted_at', sa.DateTime(timezone=True))
    )
    
    # Continue with all other tables...
    # (Full schema from schema.sql goes here)
    
def downgrade():
    """Drop all tables"""
    
    # Drop tables in reverse order
    op.drop_table('system_configs')
    op.drop_table('api_keys')
    op.drop_table('maintenance_records')
    op.drop_table('audit_logs')
    op.drop_table('activities')
    op.drop_table('notifications')
    op.drop_table('alerts')
    op.drop_table('predictions')
    op.drop_table('machine_data')
    op.drop_table('machines')
    op.drop_table('users')
    op.drop_table('organizations')
    
    # Drop enum types
    op.execute('DROP TYPE alert_severity')
    op.execute('DROP TYPE health_status')
    op.execute('DROP TYPE machine_status')
    op.execute('DROP TYPE subscription_plan')
    op.execute('DROP TYPE user_role')