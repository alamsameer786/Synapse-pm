# tests/test_alerts.py
import pytest
from fastapi import status
import uuid

pytestmark = pytest.mark.unit

class TestAlerts:
    """Complete alert system tests - ALL issues addressed"""
    
    def test_create_alert(self, client, auth_headers, sample_machine):
        """Test creating an alert
        SOLVES: No alert system testing
        """
        alert_data = {
            "machine_id": sample_machine.id,
            "type": "performance",
            "severity": "warning",
            "message": "CPU usage exceeded 80%",
            "details": {
                "cpu_usage": 85.5,
                "threshold": 80,
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }
        
        response = client.post(
            "/api/alerts",
            headers=auth_headers,
            json=alert_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["type"] == alert_data["type"]
        assert data["severity"] == alert_data["severity"]
        assert data["message"] == alert_data["message"]
        assert data["status"] == "active"
        assert "id" in data
    
    def test_get_alerts_with_filters(self, client, auth_headers):
        """Test getting alerts with filters"""
        filters = [
            "status=active",
            "severity=critical",
            "type=security",
            "from_date=2024-01-01",
            "to_date=2024-12-31"
        ]
        
        for filter_param in filters:
            response = client.get(
                f"/api/alerts?{filter_param}",
                headers=auth_headers
            )
            assert response.status_code == status.HTTP_200_OK
    
    def test_acknowledge_alert(self, client, auth_headers, sample_alert):
        """Test acknowledging an alert"""
        response = client.post(
            f"/api/alerts/{sample_alert.id}/acknowledge",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "acknowledged"
        assert "acknowledged_at" in data
        assert "acknowledged_by" in data
    
    def test_resolve_alert(self, client, auth_headers, sample_alert):
        """Test resolving an alert"""
        response = client.post(
            f"/api/alerts/{sample_alert.id}/resolve",
            headers=auth_headers,
            json={"resolution": "Issue fixed"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "resolved"
        assert "resolved_at" in data
        assert "resolution" in data
    
    def test_alert_thresholds(self, client, auth_headers, sample_machine):
        """Test alert thresholds"""
        thresholds = [
            {"metric": "cpu", "threshold": 80, "severity": "warning"},
            {"metric": "memory", "threshold": 85, "severity": "error"},
            {"metric": "latency", "threshold": 2.0, "severity": "critical"}
        ]
        
        for threshold in thresholds:
            response = client.post(
                "/api/alerts/thresholds",
                headers=auth_headers,
                json=threshold
            )
            assert response.status_code == status.HTTP_201_CREATED
    
    def test_alert_notifications(self, client, auth_headers, sample_alert, mock_email_service):
        """Test alert notifications"""
        response = client.post(
            f"/api/alerts/{sample_alert.id}/notify",
            headers=auth_headers,
            json={"channels": ["email", "webhook"]}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "notifications" in data
        assert data["notifications"]["email"] == "sent"
        
        # Verify email was called
        mock_email_service.send_alert_email.assert_called_once()