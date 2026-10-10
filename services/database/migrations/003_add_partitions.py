"""
SynapsePM - Add Table Partitions
Creates partitions for time-series tables
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta

revision = '003_add_partitions'
down_revision = '002_add_indexes'
branch_labels = None
depends_on = None

def upgrade():
    """Create table partitions"""
    
    # Convert machine_data to partitioned table
    op.execute("""
        -- Create new partitioned table
        CREATE TABLE machine_data_new (
            LIKE machine_data INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES
        ) PARTITION BY RANGE (timestamp)
    """)
    
    # Create partitions for last 12 months and next 3 months
    current = datetime.now().replace(day=1)
    
    # Past 12 months
    for i in range(12, 0, -1):
        month = current - timedelta(days=30*i)
        month_str = month.strftime('%Y_%m')
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        
        op.execute(f"""
            CREATE TABLE machine_data_{month_str} PARTITION OF machine_data_new
            FOR VALUES FROM ('{month.date()}') TO ('{next_month.date()}')
        """)
    
    # Next 3 months
    for i in range(0, 4):
        month = current + timedelta(days=30*i)
        month_str = month.strftime('%Y_%m')
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        
        op.execute(f"""
            CREATE TABLE machine_data_{month_str} PARTITION OF machine_data_new
            FOR VALUES FROM ('{month.date()}') TO ('{next_month.date()}')
        """)
    
    # Copy data (in batches for large tables)
    op.execute("""
        INSERT INTO machine_data_new 
        SELECT * FROM machine_data 
        WHERE timestamp >= CURRENT_DATE - INTERVAL '1 year'
    """)
    
    # Drop old table and rename new one
    op.execute("DROP TABLE machine_data CASCADE")
    op.execute("ALTER TABLE machine_data_new RENAME TO machine_data")
    
    # Recreate indexes
    op.create_index('idx_machine_data_machine_time', 'machine_data', 
                   ['machine_id', sa.text('timestamp DESC')])
    op.create_index('idx_machine_data_timestamp', 'machine_data', 
                   [sa.text('timestamp DESC')])
    
    # Create audit_logs partitions
    op.execute("""
        CREATE TABLE audit_logs_new (
            LIKE audit_logs INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES
        ) PARTITION BY RANGE (created_at)
    """)
    
    # Create quarterly partitions for audit logs
    for i in range(-4, 4):  # 4 quarters back, 4 forward
        quarter_start = current.replace(month=((current.month - 1) // 3) * 3 + 1, day=1)
        quarter_start = quarter_start + timedelta(days=90*i)
        quarter_end = quarter_start + timedelta(days=90)
        
        quarter_name = f"audit_logs_{quarter_start.year}_q{((quarter_start.month-1)//3)+1}"
        
        op.execute(f"""
            CREATE TABLE {quarter_name} PARTITION OF audit_logs_new
            FOR VALUES FROM ('{quarter_start.date()}') TO ('{quarter_end.date()}')
        """)
    
    # Copy last 2 years of audit logs
    op.execute("""
        INSERT INTO audit_logs_new 
        SELECT * FROM audit_logs 
        WHERE created_at >= CURRENT_DATE - INTERVAL '2 years'
    """)
    
    # Drop old table and rename new one
    op.execute("DROP TABLE audit_logs CASCADE")
    op.execute("ALTER TABLE audit_logs_new RENAME TO audit_logs")
    
    # Recreate indexes
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_org_id', 'audit_logs', ['organization_id'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'])
    op.create_index('idx_audit_created', 'audit_logs', [sa.text('created_at DESC')])
    
    # Create function for automatic partition creation
    op.execute("""
        CREATE OR REPLACE FUNCTION create_next_month_partition()
        RETURNS void AS $$
        DECLARE
            next_month date;
            partition_name text;
        BEGIN
            next_month := (date_trunc('month', CURRENT_DATE) + INTERVAL '1 month')::date;
            partition_name := 'machine_data_' || to_char(next_month, 'YYYY_MM');
            
            EXECUTE format('
                CREATE TABLE IF NOT EXISTS %I PARTITION OF machine_data
                FOR VALUES FROM (%L) TO (%L)',
                partition_name,
                next_month,
                next_month + INTERVAL '1 month'
            );
        END;
        $$ LANGUAGE plpgsql;
    """)

def downgrade():
    """Remove partitions"""
    
    # Convert back to regular table
    op.execute("""
        CREATE TABLE machine_data_backup AS SELECT * FROM machine_data
    """)
    op.execute("DROP TABLE machine_data CASCADE")
    op.execute("ALTER TABLE machine_data_backup RENAME TO machine_data")
    
    op.execute("""
        CREATE TABLE audit_logs_backup AS SELECT * FROM audit_logs
    """)
    op.execute("DROP TABLE audit_logs CASCADE")
    op.execute("ALTER TABLE audit_logs_backup RENAME TO audit_logs")
    
    # Recreate indexes
    op.create_index('idx_machine_data_machine_time', 'machine_data', 
                   ['machine_id', 'timestamp'])
    op.create_index('idx_machine_data_timestamp', 'machine_data', ['timestamp'])
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_created', 'audit_logs', ['created_at'])
    
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS create_next_month_partition()")