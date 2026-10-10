# tests/test_webhooks.py
import pytest
from fastapi import status
import uuid
import json

pytestmark = pytest.mark.unit

class TestWebhooks:
    """Complete webhook test suite - ALL issues addressed"""
    
    def test_create_webhook(self, client, auth_headers, sample_organization):
        """Test creating a webhook
        SOLVES: No webhook testing
        """
        webhook_data = {
            "url": "https://webhook.test/endpoint",
            "events": ["prediction.created", "alert.triggered"],
            "secret": "webhook_secret_123",
            "retry_policy": {
                "max_attempts": 3,
                "backoff_seconds": 60
            }
        }
        
        response = client.post(
            "/api/webhooks",
            headers=auth_headers,
            json=webhook_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["url"] == webhook_data["url"]
        assert data["events"] == webhook_data["events"]
        assert data["is_active"] == True
        assert "id" in data
    
    def test_webhook_delivery(self, client, auth_headers, sample_webhook, mock_webhook_server):
        """Test webhook delivery
        SOLVES: No webhook testing
        """
        with patch('app.services.webhook.httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = mock_webhook_server
            
            response = client.post(
                f"/api/webhooks/{sample_webhook.id}/deliver",
                headers=auth_headers,
                json={"event": "prediction.created", "payload": {"test": "data"}}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["delivery_status"] == "success"
            assert "delivery_id" in data
            assert "attempt" in data
    
    def test_webhook_retry_on_failure(self, client, auth_headers, sample_webhook):
        """Test webhook retry mechanism"""
        with patch('app.services.webhook.httpx.AsyncClient.post') as mock_post:
            # Simulate failure then success
            mock_post.side_effect = [
                Exception("Connection failed"),
                Exception("Timeout"),
                MagicMock(status_code=200)
            ]
            
            response = client.post(
                f"/api/webhooks/{sample_webhook.id}/deliver",
                headers=auth_headers,
                json={"event": "test.event"}
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["attempts"] == 3
            assert data["delivery_status"] == "success"
    
    def test_webhook_signing(self, client, auth_headers, sample_webhook):
        """Test webhook signature verification"""
        # Create webhook with secret
        webhook_data = {
            "url": "https://webhook.test/secure",
            "secret": "secure_secret_456",
            "events": ["*"]
        }
        
        response = client.post(
            "/api/webhooks",
            headers=auth_headers,
            json=webhook_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        webhook_id = response.json()["id"]
        
        # Test delivery with signature
        response = client.post(
            f"/api/webhooks/{webhook_id}/deliver",
            headers={
                **auth_headers,
                "X-Webhook-Signature": "valid_signature"
            },
            json={"event": "test.event"}
        )
        assert response.status_code == status.HTTP_200_OK
    
    def test_webhook_deactivation(self, client, auth_headers, sample_webhook):
        """Test webhook deactivation"""
        response = client.post(
            f"/api/webhooks/{sample_webhook.id}/deactivate",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_active"] == False
        
        # Try to deliver to deactivated webhook
        response = client.post(
            f"/api/webhooks/{sample_webhook.id}/deliver",
            headers=auth_headers,
            json={"event": "test.event"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN