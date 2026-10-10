# tests/test_integration.py
import pytest
from fastapi import status
import uuid
from datetime import datetime

pytestmark = pytest.mark.integration

class TestIntegration:
    """Complete integration test suite - ALL issues addressed"""
    
    def test_end_to_end_prediction_workflow(self, client, db_session, mock_redis, mock_email_service):
        """Test complete prediction workflow with all components
        SOLVES: No end-to-end workflow testing
        """
        # 1. Register user
        user_email = f"e2e_{uuid.uuid4()}@example.com"
        register_response = client.post("/auth/register", json={
            "email": user_email,
            "password": "SecurePass123!",
            "name": "E2E User"
        })
        assert register_response.status_code == status.HTTP_201_CREATED
        
        # 2. Login
        login_response = client.post("/auth/login", json={
            "email": user_email,
            "password": "SecurePass123!"
        })
        assert login_response.status_code == status.HTTP_200_OK
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. Create machine
        machine_response = client.post(
            "/api/machines",
            headers=headers,
            json={
                "name": f"E2E Machine {uuid.uuid4().hex[:6]}",
                "model": "GPT-4",
                "status": "active"
            }
        )
        assert machine_response.status_code == status.HTTP_201_CREATED
        machine_id = machine_response.json()["id"]
        
        # 4. Make prediction
        prediction_response = client.post(
            f"/api/predictions/{machine_id}",
            headers=headers,
            json={
                "input_data": {"text": "E2E test prediction"},
                "parameters": {"temperature": 0.7}
            }
        )
        assert prediction_response.status_code == status.HTTP_200_OK
        prediction_data = prediction_response.json()
        prediction_id = prediction_data["id"]
        
        # 5. Submit feedback
        feedback_response = client.post(
            f"/api/predictions/{prediction_id}/feedback",
            headers=headers,
            json={
                "rating": 5,
                "feedback_text": "Great job!",
                "correct_answer": "Expected output"
            }
        )
        assert feedback_response.status_code == status.HTTP_200_OK
        
        # 6. Check prediction history
        history_response = client.get(
            f"/api/predictions?machine_id={machine_id}",
            headers=headers
        )
        assert history_response.status_code == status.HTTP_200_OK
        assert len(history_response.json()["items"]) >= 1
    
    def test_billing_integration_workflow(self, client, db_session, mock_razorpay, mock_email_service):
        """Test complete billing workflow
        SOLVES: No billing/payment testing
        """
        # 1. Create user
        user_email = f"billing_{uuid.uuid4()}@example.com"
        client.post("/auth/register", json={
            "email": user_email,
            "password": "SecurePass123!",
            "name": "Billing User"
        })
        
        login_response = client.post("/auth/login", json={
            "email": user_email,
            "password": "SecurePass123!"
        })
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Create subscription
        subscription_response = client.post(
            "/api/billing/subscriptions",
            headers=headers,
            json={
                "plan": "pro",
                "billing_cycle": "monthly",
                "payment_method": "card",
                "auto_renew": True
            }
        )
        assert subscription_response.status_code == status.HTTP_201_CREATED
        subscription_id = subscription_response.json()["id"]
        
        # 3. Process payment
        payment_response = client.post(
            "/api/billing/payments/process",
            headers=headers,
            json={
                "payment_id": "pay_test_123",
                "amount": 10000,
                "currency": "USD"
            }
        )
        assert payment_response.status_code == status.HTTP_200_OK
        
        # 4. Verify subscription updated
        subscription_detail_response = client.get(
            f"/api/billing/subscriptions/{subscription_id}",
            headers=headers
        )
        assert subscription_detail_response.status_code == status.HTTP_200_OK
        assert subscription_detail_response.json()["status"] == "active"
        
        # 5. Check invoice generated
        invoice_response = client.get(
            "/api/billing/invoices",
            headers=headers
        )
        assert invoice_response.status_code == status.HTTP_200_OK
        assert len(invoice_response.json()["items"]) >= 1
    
    def test_alert_webhook_integration(self, client, db_session, mock_email_service, mock_webhook_server):
        """Test alert and webhook integration
        SOLVES: No alert system testing
        SOLVES: No webhook testing
        """
        # Create user and get token
        user_email = f"alert_{uuid.uuid4()}@example.com"
        client.post("/auth/register", json={
            "email": user_email,
            "password": "SecurePass123!",
            "name": "Alert User"
        })
        
        login_response = client.post("/auth/login", json={
            "email": user_email,
            "password": "SecurePass123!"
        })
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create webhook
        webhook_response = client.post(
            "/api/webhooks",
            headers=headers,
            json={
                "url": "https://webhook.test/alerts",
                "events": ["alert.triggered"],
                "secret": "test_secret"
            }
        )
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        # Create machine
        machine_response = client.post(
            "/api/machines",
            headers=headers,
            json={
                "name": f"Alert Machine {uuid.uuid4().hex[:6]}",
                "model": "GPT-4"
            }
        )
        machine_id = machine_response.json()["id"]
        
        # Trigger alert via threshold
        with patch('app.services.webhook.httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = mock_webhook_server
            
            # Create alert
            alert_response = client.post(
                "/api/alerts",
                headers=headers,
                json={
                    "machine_id": machine_id,
                    "type": "performance",
                    "severity": "critical",
                    "message": "Model performance degraded"
                }
            )
            assert alert_response.status_code == status.HTTP_201_CREATED
            
            # Verify notification sent
            mock_email_service.send_alert_email.assert_called_once()
            mock_post.assert_called_once()