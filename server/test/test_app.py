#!/usr/bin/env python3
"""
Unit Tests for SynapsePM - v11.0.0
Run with: pytest tests/
"""

import os
import sys
import json
import pytest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db, User, Organization, Machine, Prediction, Alert
from flask import url_for
import jwt

# ============================================================
# TEST CONFIGURATION
# ============================================================

@pytest.fixture
def app():
    """Create and configure a test app instance"""
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "REDIS_URL": None,
        "ENABLE_RATE_LIMITING": False,
        "WTF_CSRF_ENABLED": False,
        "MAIL_SUPPRESS_SEND": True,
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Test client for making requests"""
    return app.test_client()

@pytest.fixture
def auth_token(app, client):
    """Create a test user and return auth token"""
    with app.app_context():
        # Create test organization
        org = Organization(
            name="Test Org",
            slug="test-org",
            primary_email="test@example.com",
            plan="FREE",
            subscription_status="active"
        )
        db.session.add(org)
        db.session.flush()
        
        # Create test user
        user = User(
            organization_id=org.id,
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            role="org_admin",
            is_active=True,
            is_verified=True
        )
        user.set_password("Test@123456")
        db.session.add(user)
        db.session.commit()
        
        # Generate token
        token = user.generate_auth_token()
        return token, user, org

# ============================================================
# AUTHENTICATION TESTS
# ============================================================

class TestAuth:
    """Test authentication endpoints"""
    
    def test_register_success(self, client):
        """Test successful registration"""
        response = client.post('/api/v1/auth/register', json={
            'email': 'newuser@example.com',
            'password': 'Test@123456',
            'first_name': 'New',
            'last_name': 'User',
            'company': 'Test Company'
        })
        data = response.get_json()
        assert response.status_code == 201
        assert data['success'] is True
        assert 'access_token' in data
        assert 'user' in data
        assert data['user']['email'] == 'newuser@example.com'
    
    def test_register_duplicate_email(self, client):
        """Test registration with duplicate email"""
        # First registration
        client.post('/api/v1/auth/register', json={
            'email': 'duplicate@example.com',
            'password': 'Test@123456',
            'first_name': 'Test',
            'last_name': 'User',
            'company': 'Test Company'
        })
        
        # Second registration with same email
        response = client.post('/api/v1/auth/register', json={
            'email': 'duplicate@example.com',
            'password': 'Test@123456',
            'first_name': 'Test',
            'last_name': 'User',
            'company': 'Test Company'
        })
        data = response.get_json()
        assert response.status_code == 409
        assert data['success'] is False
    
    def test_register_weak_password(self, client):
        """Test registration with weak password"""
        response = client.post('/api/v1/auth/register', json={
            'email': 'weak@example.com',
            'password': '123',
            'first_name': 'Test',
            'last_name': 'User',
            'company': 'Test Company'
        })
        data = response.get_json()
        assert response.status_code == 400
        assert 'Password must be at least' in data['error']
    
    def test_register_invalid_email(self, client):
        """Test registration with invalid email"""
        response = client.post('/api/v1/auth/register', json={
            'email': 'not-an-email',
            'password': 'Test@123456',
            'first_name': 'Test',
            'last_name': 'User',
            'company': 'Test Company'
        })
        data = response.get_json()
        assert response.status_code == 400
        assert 'Invalid email' in data['error']
    
    def test_login_success(self, client):
        """Test successful login"""
        # Register first
        client.post('/api/v1/auth/register', json={
            'email': 'login@example.com',
            'password': 'Test@123456',
            'first_name': 'Login',
            'last_name': 'Test',
            'company': 'Test Company'
        })
        
        # Login
        response = client.post('/api/v1/auth/login', json={
            'email': 'login@example.com',
            'password': 'Test@123456'
        })
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert 'access_token' in data
        assert 'user' in data
    
    def test_login_wrong_password(self, client):
        """Test login with wrong password"""
        # Register first
        client.post('/api/v1/auth/register', json={
            'email': 'wrongpass@example.com',
            'password': 'Test@123456',
            'first_name': 'Wrong',
            'last_name': 'Pass',
            'company': 'Test Company'
        })
        
        # Login with wrong password
        response = client.post('/api/v1/auth/login', json={
            'email': 'wrongpass@example.com',
            'password': 'WrongPassword'
        })
        data = response.get_json()
        assert response.status_code == 401
        assert data['success'] is False
    
    def test_login_unverified_email(self, client):
        """Test login with unverified email"""
        # Create user without verification
        response = client.post('/api/v1/auth/register', json={
            'email': 'unverified@example.com',
            'password': 'Test@123456',
            'first_name': 'Unverified',
            'last_name': 'User',
            'company': 'Test Company'
        })
        data = response.get_json()
        
        # Should still get tokens but requires verification
        assert 'access_token' in data
        assert data['requires_verification'] is True
    
    def test_reset_password_flow(self, client):
        """Test password reset flow"""
        # Register first
        client.post('/api/v1/auth/register', json={
            'email': 'reset@example.com',
            'password': 'Test@123456',
            'first_name': 'Reset',
            'last_name': 'Test',
            'company': 'Test Company'
        })
        
        # Request password reset OTP
        response = client.post('/api/v1/auth/forgot-password', json={
            'email': 'reset@example.com'
        })
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True

# ============================================================
# MACHINE TESTS
# ============================================================

class TestMachines:
    """Test machine endpoints"""
    
    def test_create_machine_success(self, client, auth_token):
        """Test successful machine creation"""
        token, user, org = auth_token
        
        response = client.post('/api/v1/machines', json={
            'name': 'Test Machine',
            'machine_type': 'CNC',
            'manufacturer': 'Test Corp',
            'model': 'T-1000',
            'serial_number': 'SN-12345',
            'location': 'Factory A'
        }, headers={'Authorization': f'Bearer {token}'})
        
        data = response.get_json()
        assert response.status_code == 201
        assert data['success'] is True
        assert data['machine']['name'] == 'Test Machine'
        assert data['machine']['machine_type'] == 'CNC'
    
    def test_create_machine_validation_fails(self, client, auth_token):
        """Test machine creation with missing fields"""
        token, user, org = auth_token
        
        response = client.post('/api/v1/machines', json={
            'name': 'Test Machine'
            # Missing machine_type
        }, headers={'Authorization': f'Bearer {token}'})
        
        data = response.get_json()
        assert response.status_code == 400
        assert data['success'] is False
    
    def test_list_machines(self, client, auth_token):
        """Test listing machines"""
        token, user, org = auth_token
        
        # Create a machine first
        client.post('/api/v1/machines', json={
            'name': 'Test Machine 1',
            'machine_type': 'CNC'
        }, headers={'Authorization': f'Bearer {token}'})
        
        # List machines
        response = client.get('/api/v1/machines', 
            headers={'Authorization': f'Bearer {token}'})
        
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert 'items' in data
        assert len(data['items']) >= 1
    
    def test_add_sensor_data(self, client, auth_token):
        """Test adding sensor data to machine"""
        token, user, org = auth_token
        
        # Create machine
        machine_res = client.post('/api/v1/machines', json={
            'name': 'Sensor Machine',
            'machine_type': 'Test'
        }, headers={'Authorization': f'Bearer {token}'})
        machine_id = machine_res.get_json()['machine']['id']
        
        # Add sensor data
        response = client.post(f'/api/v1/machines/{machine_id}/sensor-data', json={
            'temperature': 75.5,
            'vibration': 3.2,
            'pressure': 60.0,
            'readings': {'extra': 'data'}
        }, headers={'Authorization': f'Bearer {token}'})
        
        data = response.get_json()
        assert response.status_code == 201
        assert data['success'] is True
        assert data['sensor_data']['temperature'] == 75.5

# ============================================================
# PREDICTION TESTS
# ============================================================

class TestPredictions:
    """Test prediction endpoints"""
    
    def test_run_prediction(self, client, auth_token):
        """Test running prediction"""
        token, user, org = auth_token
        
        # Create machine
        machine_res = client.post('/api/v1/machines', json={
            'name': 'Prediction Machine',
            'machine_type': 'Test'
        }, headers={'Authorization': f'Bearer {token}'})
        machine_id = machine_res.get_json()['machine']['id']
        
        # Add sensor data
        client.post(f'/api/v1/machines/{machine_id}/sensor-data', json={
            'temperature': 75.5,
            'vibration': 3.2,
            'pressure': 60.0
        }, headers={'Authorization': f'Bearer {token}'})
        
        # Run prediction
        response = client.post('/api/v1/predictions/run', json={
            'machine_id': machine_id
        }, headers={'Authorization': f'Bearer {token}'})
        
        data = response.get_json()
        # May return 422 if no model available, or 200 if prediction works
        assert response.status_code in [200, 422]
        if response.status_code == 200:
            assert data['success'] is True
            assert 'prediction' in data

# ============================================================
# ALERT TESTS
# ============================================================

class TestAlerts:
    """Test alert endpoints"""
    
    def test_list_alerts(self, client, auth_token):
        """Test listing alerts"""
        token, user, org = auth_token
        
        response = client.get('/api/v1/alerts', 
            headers={'Authorization': f'Bearer {token}'})
        
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert 'items' in data

# ============================================================
# ADMIN TESTS
# ============================================================

class TestAdmin:
    """Test admin endpoints"""
    
    def test_admin_stats(self, client, auth_token):
        """Test admin stats endpoint"""
        token, user, org = auth_token
        
        # Make sure user is admin
        if user.role in ['super_admin', 'org_admin']:
            response = client.get('/api/v1/admin/stats', 
                headers={'Authorization': f'Bearer {token}'})
            data = response.get_json()
            assert response.status_code == 200
            assert data['success'] is True
            assert 'stats' in data

# ============================================================
# HEALTH CHECK TESTS
# ============================================================

class TestHealth:
    """Test health endpoints"""
    
    def test_health(self, client):
        """Test health check"""
        response = client.get('/health')
        data = response.get_json()
        assert response.status_code in [200, 503]
        assert 'status' in data
        assert 'version' in data
    
    def test_ping(self, client):
        """Test ping"""
        response = client.get('/ping')
        data = response.get_json()
        assert response.status_code == 200
        assert data['status'] == 'pong'
    
    def test_api_index(self, client):
        """Test API index"""
        response = client.get('/api')
        data = response.get_json()
        assert response.status_code == 200
        assert 'service' in data
        assert 'version' in data
        assert 'endpoints' in data

# ============================================================
# RUN TESTS
# ============================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])