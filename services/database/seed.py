"""
SYNAPSEPM - ENTERPRISE DATABASE SEEDER v3.0
GLOBAL MARKET READY - Production-grade seeding
"""

import sys
import os
import json
import secrets
import logging
import getpass
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum
import uuid
import time
import traceback
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import adapt, register_adapter, AsIs
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("⚠️ psycopg2 not installed. Install with: pip install psycopg2-binary")

def adapt_uuid(uuid_obj):
    return AsIs("'{}'::uuid".format(uuid_obj))

try:
    register_adapter(uuid.UUID, adapt_uuid)
except:
    pass

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    print("⚠️ bcrypt not installed. Install with: pip install bcrypt")

# ============================================================================
# LOGGING
# ============================================================================

class Logger:
    def __init__(self):
        self.correlation_id = str(uuid.uuid4())
    
    def info(self, msg, **kwargs):
        print(f"[INFO] {msg}")
    
    def warning(self, msg, **kwargs):
        print(f"[WARNING] {msg}")
    
    def error(self, msg, **kwargs):
        print(f"[ERROR] {msg}")
    
    def critical(self, msg, **kwargs):
        print(f"[CRITICAL] {msg}")

logger = Logger()

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class SeedConfig:
    environment: str = "development"
    force: bool = False
    dry_run: bool = False
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "synapse_db"
    db_user: str = "postgres"
    db_password: Optional[str] = None
    
    @classmethod
    def from_env(cls):
        return cls(
            environment=os.getenv("ENVIRONMENT", "development"),
            force=os.getenv("SEED_FORCE", "false").lower() == "true",
            dry_run=os.getenv("SEED_DRY_RUN", "false").lower() == "true",
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", 5432)),
            db_name=os.getenv("DB_NAME", "synapse_db"),
            db_user=os.getenv("DB_USER", "postgres"),
            db_password=os.getenv("DB_PASSWORD"),
        )

# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class ConnectionManager:
    def __init__(self, config: SeedConfig):
        self.config = config

    @contextmanager
    def get_connection(self, dbname: str = None, autocommit: bool = False):
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2-binary is required")
        
        dbname = dbname or self.config.db_name
        conn = None
        try:
            conn = psycopg2.connect(
                dbname=dbname,
                user=self.config.db_user,
                password=self.config.db_password,
                host=self.config.db_host,
                port=self.config.db_port,
                connect_timeout=10
            )
            conn.autocommit = autocommit
            yield conn
            if not autocommit:
                conn.commit()
        finally:
            if conn:
                conn.close()

# ============================================================================
# PASSWORD GENERATOR
# ============================================================================

class PasswordGenerator:
    def generate(self) -> str:
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()"
        return ''.join(secrets.choice(alphabet) for _ in range(16))

# ============================================================================
# DATABASE SEEDER
# ============================================================================

class DatabaseSeeder:
    def __init__(self, config: SeedConfig):
        self.config = config
        self.conn = ConnectionManager(config)
        self.password_gen = PasswordGenerator()
        self._org_ids = {}
        self._metrics = {"records_created": {}}
    
    def seed(self, action: str = "all") -> Dict:
        try:
            if action in ["all", "organizations"]:
                self._seed_organizations()
            
            if action in ["all", "users"]:
                self._seed_users()
            
            if action in ["all", "machines"]:
                self._seed_machines()
            
            if action in ["all", "predictions"]:
                self._seed_predictions()
            
            if action in ["all", "alerts"]:
                self._seed_alerts()
            
            if action in ["all", "configs"]:
                self._seed_configs()
            
            return {
                "success": True,
                "metrics": self._metrics,
                "message": f"Seeding completed for {action}"
            }
        except Exception as e:
            logger.error(f"Seeding failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _seed_organizations(self):
        logger.info("📋 Creating organizations...")
        
        orgs = [
            {
                'name': 'Acme Corporation',
                'subdomain': 'acme',
                'industry': 'Manufacturing',
                'primary_email': 'admin@acme.com',
                'plan': 'ENTERPRISE',
                'max_users': 500,
                'max_machines': 500,
                'max_predictions_per_month': 10000,
                'is_active': True,
            },
            {
                'name': 'Startup Inc',
                'subdomain': 'startup',
                'industry': 'Technology',
                'primary_email': 'admin@startup.com',
                'plan': 'PROFESSIONAL',
                'max_users': 50,
                'max_machines': 50,
                'max_predictions_per_month': 1000,
                'is_active': True,
                'is_trial': True,
            }
        ]
        
        count = 0
        for org in orgs:
            try:
                with self.conn.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM organizations WHERE subdomain = %s", (org['subdomain'],))
                    existing = cur.fetchone()
                    
                    if existing:
                        self._org_ids[org['subdomain']] = existing[0]
                        logger.info(f"  ✅ Organization '{org['name']}' already exists")
                        continue
                    
                    org_id = uuid.uuid4()
                    cur.execute("""
                        INSERT INTO organizations (id, name, subdomain, industry, primary_email,
                            plan, max_users, max_machines, max_predictions_per_month, 
                            is_active, is_trial, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        org_id, org['name'], org['subdomain'], org['industry'], org['primary_email'],
                        org['plan'], org['max_users'], org['max_machines'], org['max_predictions_per_month'],
                        org['is_active'], org.get('is_trial', False),
                        datetime.now(timezone.utc), datetime.now(timezone.utc)
                    ))
                    result = cur.fetchone()
                    if result:
                        self._org_ids[org['subdomain']] = result[0]
                        count += 1
                        logger.info(f"  ✅ Created organization: {org['name']}")
            except Exception as e:
                logger.error(f"  ❌ Failed to create {org['name']}: {e}")
        
        self._metrics["records_created"]["organizations"] = count
        logger.info(f"✅ Organizations: {count} created")
    
    def _seed_users(self):
        logger.info("👤 Creating users...")
        
        if not self._org_ids:
            # Fetch existing orgs
            try:
                with self.conn.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id, subdomain FROM organizations")
                    for row in cur.fetchall():
                        self._org_ids[row[1]] = row[0]
            except Exception as e:
                logger.error(f"Failed to fetch organizations: {e}")
                return
        
        users = [
            {
                'org': 'acme',
                'username': 'superadmin',
                'email': 'superadmin@synapsepm.com',
                'first_name': 'Super',
                'last_name': 'Admin',
                'role': 'super_admin',
            },
            {
                'org': 'acme',
                'username': 'admin',
                'email': 'admin@acme.com',
                'first_name': 'John',
                'last_name': 'Admin',
                'role': 'org_admin',
            },
            {
                'org': 'acme',
                'username': 'engineer',
                'email': 'engineer@acme.com',
                'first_name': 'Jane',
                'last_name': 'Engineer',
                'role': 'engineer',
            },
            {
                'org': 'startup',
                'username': 'admin',
                'email': 'admin@startup.com',
                'first_name': 'Bob',
                'last_name': 'Admin',
                'role': 'org_admin',
            },
            {
                'org': 'startup',
                'username': 'user',
                'email': 'user@startup.com',
                'first_name': 'Alice',
                'last_name': 'User',
                'role': 'viewer',
            }
        ]
        
        passwords = {}
        count = 0
        
        for user in users:
            org_id = self._org_ids.get(user['org'])
            if not org_id:
                logger.warning(f"  ⚠️ Organization '{user['org']}' not found, skipping {user['email']}")
                continue
            
            try:
                password = self.password_gen.generate()
                passwords[user['username']] = password
                password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                user_id = uuid.uuid4()
                
                with self.conn.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM users WHERE organization_id = %s AND email = %s",
                        (org_id, user['email'])
                    )
                    existing = cur.fetchone()
                    
                    if existing:
                        logger.info(f"  ⚠️ User {user['email']} already exists")
                        continue
                    
                    cur.execute("""
                        INSERT INTO users (id, organization_id, username, email, _password_hash,
                            first_name, last_name, role, is_verified, is_active, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        user_id, org_id, user['username'], user['email'], password_hash,
                        user['first_name'], user['last_name'], user['role'],
                        True, True, datetime.now(timezone.utc), datetime.now(timezone.utc)
                    ))
                    result = cur.fetchone()
                    if result:
                        count += 1
                        logger.info(f"  ✅ Created user: {user['email']} (role: {user['role']})")
            except Exception as e:
                logger.error(f"  ❌ Failed to create {user['email']}: {e}")
        
        self._metrics["records_created"]["users"] = count
        logger.info(f"✅ Users: {count} created")
        
        # Log credentials
        if passwords:
            print("\n" + "=" * 70)
            print("🔐 USER CREDENTIALS (Save these!)")
            print("=" * 70)
            for username, password in passwords.items():
                print(f"  {username}: {password}")
            print("=" * 70)
            print("⚠️  CHANGE THESE PASSWORDS IMMEDIATELY!")
            print("=" * 70)
    
    def _seed_machines(self):
        logger.info("🏗️ Creating machines...")
        
        if not self._org_ids:
            try:
                with self.conn.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id, subdomain FROM organizations")
                    for row in cur.fetchall():
                        self._org_ids[row[1]] = row[0]
            except Exception as e:
                logger.error(f"Failed to fetch organizations: {e}")
                return
        
        machines = [
            {
                'org': 'acme',
                'name': 'Compressor A - Production Line',
                'machine_type': 'compressor',
                'manufacturer': 'Siemens',
                'model': 'C-2000',
                'status': 'online',
                'health_status': 'healthy',
                'is_critical': True,
                'temperature': 45.5,
                'vibration': 2.3,
                'rpm': 1750,
                'pressure': 85.5,
            },
            {
                'org': 'acme',
                'name': 'Motor B - Packaging Line',
                'machine_type': 'motor',
                'manufacturer': 'ABB',
                'model': 'M-100',
                'status': 'online',
                'health_status': 'warning',
                'is_critical': False,
                'temperature': 65.2,
                'vibration': 4.1,
                'rpm': 3450,
                'pressure': 45.0,
            },
            {
                'org': 'startup',
                'name': 'Test Pump',
                'machine_type': 'pump',
                'manufacturer': 'Grundfos',
                'model': 'P-500',
                'status': 'online',
                'health_status': 'healthy',
                'is_critical': False,
                'temperature': 32.0,
                'vibration': 1.2,
                'rpm': 1200,
                'pressure': 60.0,
            }
        ]
        
        count = 0
        for machine in machines:
            org_id = self._org_ids.get(machine['org'])
            if not org_id:
                continue
            
            try:
                serial = f'SN-{secrets.token_hex(8).upper()}'
                machine_id = uuid.uuid4()
                
                with self.conn.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM machines WHERE organization_id = %s AND name = %s",
                        (org_id, machine['name'])
                    )
                    if cur.fetchone():
                        logger.info(f"  ⚠️ Machine '{machine['name']}' already exists")
                        continue
                    
                    cur.execute("""
                        INSERT INTO machines (id, organization_id, name, machine_type, 
                            manufacturer, model, serial_number, status, health_status,
                            is_critical, temperature, vibration, rpm, pressure,
                            created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        machine_id, org_id, machine['name'], machine['machine_type'],
                        machine['manufacturer'], machine['model'], serial,
                        machine['status'], machine['health_status'],
                        machine['is_critical'], machine['temperature'], machine['vibration'],
                        machine['rpm'], machine['pressure'],
                        datetime.now(timezone.utc), datetime.now(timezone.utc)
                    ))
                    result = cur.fetchone()
                    if result:
                        count += 1
                        logger.info(f"  ✅ Created machine: {machine['name']}")
            except Exception as e:
                logger.error(f"  ❌ Failed to create {machine['name']}: {e}")
        
        self._metrics["records_created"]["machines"] = count
        logger.info(f"✅ Machines: {count} created")
    
    def _seed_predictions(self):
        logger.info("📊 Creating predictions...")
        
        import random
        
        try:
            with self.conn.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, organization_id FROM machines WHERE deleted_at IS NULL")
                machines = cur.fetchall()
        except Exception as e:
            logger.error(f"Failed to fetch machines: {e}")
            return
        
        if not machines:
            logger.warning("No machines found, skipping predictions")
            return
        
        try:
            with self.conn.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, organization_id FROM users WHERE deleted_at IS NULL")
                users = {row[1]: row[0] for row in cur.fetchall()}
        except Exception as e:
            logger.error(f"Failed to fetch users: {e}")
            return
        
        count = 0
        for machine_id, org_id in machines:
            user_id = users.get(org_id)
            if not user_id:
                continue
            
            num = random.randint(3, 8)
            for _ in range(num):
                rul = random.uniform(10, 500)
                confidence = random.uniform(0.7, 0.95)
                
                if rul > 200:
                    risk = 'low'
                    risk_score = random.uniform(0.1, 0.3)
                elif rul > 50:
                    risk = 'medium'
                    risk_score = random.uniform(0.4, 0.6)
                else:
                    risk = 'critical'
                    risk_score = random.uniform(0.7, 0.9)
                
                try:
                    pred_id = uuid.uuid4()
                    created = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30))
                    
                    with self.conn.get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO predictions (id, organization_id, machine_id, user_id,
                                rul_value, rul_unit, confidence_score, prediction_status,
                                risk_level, risk_score, failure_probability,
                                model_version, model_type, processing_time_ms,
                                created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            pred_id, org_id, machine_id, user_id,
                            rul, 'hours', confidence, 'completed',
                            risk, risk_score, random.uniform(0.01, 0.5),
                            'v1.0.0', 'lstm', random.randint(50, 200),
                            created, created
                        ))
                        if cur.fetchone():
                            count += 1
                except Exception as e:
                    pass
        
        self._metrics["records_created"]["predictions"] = count
        logger.info(f"✅ Predictions: {count} created")
    
    def _seed_alerts(self):
        logger.info("🔔 Creating alerts...")
        
        try:
            with self.conn.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, machine_id, organization_id, user_id, rul_value, risk_level
                    FROM predictions 
                    WHERE risk_level IN ('critical', 'high') 
                    ORDER BY created_at DESC LIMIT 10
                """)
                predictions = cur.fetchall()
        except Exception as e:
            logger.error(f"Failed to fetch predictions: {e}")
            return
        
        if not predictions:
            logger.info("No critical predictions found")
            return
        
        count = 0
        for pred_id, machine_id, org_id, user_id, rul, risk in predictions:
            try:
                alert_id = uuid.uuid4()
                severity = 'critical' if risk == 'critical' else 'high'
                
                with self.conn.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO alerts (id, organization_id, user_id, machine_id, prediction_id,
                            alert_type, severity, title, message, alert_status, priority,
                            created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        alert_id, org_id, user_id, machine_id, pred_id,
                        'prediction', severity,
                        f'Critical RUL Alert - {rul:.1f} hours remaining',
                        f'Machine has only {rul:.1f} hours remaining',
                        'active', 10,
                        datetime.now(timezone.utc), datetime.now(timezone.utc)
                    ))
                    if cur.fetchone():
                        count += 1
            except Exception as e:
                pass
        
        self._metrics["records_created"]["alerts"] = count
        logger.info(f"✅ Alerts: {count} created")
    
    def _seed_configs(self):
        logger.info("⚙️ Creating configurations...")
        
        configs = [
            {'key': 'system_name', 'value': 'SynapsePM', 'type': 'string', 'desc': 'System name'},
            {'key': 'maintenance_window', 'value': '2', 'type': 'integer', 'desc': 'Maintenance window hours'},
            {'key': 'default_prediction_model', 'value': 'lstm_v2', 'type': 'string', 'desc': 'Default model'},
            {'key': 'max_concurrent_training', 'value': '5', 'type': 'integer', 'desc': 'Max training jobs'},
            {'key': 'auto_retrain_enabled', 'value': 'true', 'type': 'boolean', 'desc': 'Auto retraining'},
        ]
        
        count = 0
        for config in configs:
            try:
                with self.conn.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO system_configs (id, config_key, config_value, data_type, description,
                            category, is_editable, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (config_key) DO UPDATE SET
                            config_value = EXCLUDED.config_value,
                            updated_at = EXCLUDED.updated_at
                        RETURNING id
                    """, (
                        uuid.uuid4(), config['key'], config['value'], config['type'],
                        config['desc'], 'system', True,
                        datetime.now(timezone.utc), datetime.now(timezone.utc)
                    ))
                    if cur.fetchone():
                        count += 1
            except Exception as e:
                pass
        
        self._metrics["records_created"]["configs"] = count
        logger.info(f"✅ Configs: {count} created")

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="SynapsePM Database Seeder")
    parser.add_argument("--action", default="all", 
                       choices=["all", "organizations", "users", "machines", "predictions", "alerts", "configs"])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env", default="development")
    
    args = parser.parse_args()
    
    config = SeedConfig.from_env()
    config.force = args.force
    config.dry_run = args.dry_run
    config.environment = args.env
    
    if not config.db_password:
        print("\n🔐 Enter database password:")
        config.db_password = getpass.getpass("Password: ")
    
    seeder = DatabaseSeeder(config)
    result = seeder.seed(args.action)
    
    if result["success"]:
        print("\n" + "=" * 70)
        print("✅ SEEDING COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print("\n📊 Records Created:")
        for table, count in result["metrics"]["records_created"].items():
            print(f"  • {table}: {count}")
        print("\n🚀 Database is ready for SynapsePM!")
        print("=" * 70)
        return 0
    else:
        print("\n❌ SEEDING FAILED:", result.get("error"))
        return 1

if __name__ == "__main__":
    sys.exit(main())