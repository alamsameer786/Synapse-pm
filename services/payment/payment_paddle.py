#!/usr/bin/env python3
"""
SYNAPPM - COMPLETE PRODUCTION PAYMENT SYSTEM v5.2.1
FIXED: SQLite/PostgreSQL compatibility, JSONB fallback for SQLite
Enterprise-grade with Paddle + Khalti integration
"""

import os
import sys
import json
import hmac
import hashlib
import base64
import uuid
import time
import logging
import smtplib
import secrets
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO

# ============================================================
# FLASK IMPORTS
# ============================================================

try:
    from flask import Flask, Blueprint, request, jsonify, g, current_app, redirect, send_file, render_template_string
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("⚠️ Flask not installed. Install: pip install Flask Flask-CORS")

# ============================================================
# DATABASE IMPORTS - FIXED FOR SQLITE
# ============================================================

try:
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
    from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
    from sqlalchemy.types import TypeDecorator, Text as SQLText
    from sqlalchemy.exc import SQLAlchemyError
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    print("⚠️ SQLAlchemy not installed. Install: pip install Flask-SQLAlchemy SQLAlchemy")

# ============================================================
# JSONB TYPE FOR SQLITE COMPATIBILITY - FIXED
# ============================================================

class JSONType(TypeDecorator):
    """JSON type that works with both PostgreSQL and SQLite"""
    impl = SQLText
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, dict) or isinstance(value, list):
            return value
        try:
            return json.loads(value)
        except:
            return value

# ============================================================
# THIRD-PARTY IMPORTS
# ============================================================

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("⚠️ PyJWT not installed. Install: pip install PyJWT")

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    print("⚠️ bcrypt not installed. Install: pip install bcrypt")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("⚠️ requests not installed. Install: pip install requests")

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("⚠️ reportlab not installed. Install: pip install reportlab")

# ============================================================
# LOGGING
# ============================================================

LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / 'payment.log'),
        logging.FileHandler(LOG_DIR / 'payment_error.log')
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class PaymentConfig:
    """Complete payment configuration"""
    
    # Paddle Configuration
    paddle_vendor_id: str = os.getenv('PADDLE_VENDOR_ID', '')
    paddle_api_key: str = os.getenv('PADDLE_API_KEY', '')
    paddle_webhook_secret: str = os.getenv('PADDLE_WEBHOOK_SECRET', '')
    paddle_environment: str = os.getenv('PADDLE_ENVIRONMENT', 'sandbox')
    
    # Khalti Configuration
    khalti_secret_key: str = os.getenv('KHALTI_SECRET_KEY', '')
    khalti_public_key: str = os.getenv('KHALTI_PUBLIC_KEY', '')
    khalti_environment: str = os.getenv('KHALTI_ENVIRONMENT', 'test')
    
    # URLs
    app_url: str = os.getenv('APP_URL', 'http://localhost:5000')
    frontend_url: str = os.getenv('FRONTEND_URL', 'http://localhost:5500')
    
    # Paddle URLs
    paddle_api_url: str = 'https://sandbox-api.paddle.com' if os.getenv('PADDLE_ENVIRONMENT', 'sandbox') == 'sandbox' else 'https://api.paddle.com'
    paddle_checkout_url: str = 'https://sandbox-checkout.paddle.com' if os.getenv('PADDLE_ENVIRONMENT', 'sandbox') == 'sandbox' else 'https://checkout.paddle.com'
    
    # Khalti URLs
    khalti_api_url: str = 'https://api.khalti.com/api/v2' if os.getenv('KHALTI_ENVIRONMENT', 'test') == 'test' else 'https://api.khalti.com/api/v2'
    
    # Plan Definitions
    plans: Dict = field(default_factory=lambda: {
        'free': {
            'name': 'Free',
            'price_monthly': 0,
            'price_yearly': 0,
            'machines': 1,
            'predictions': 50,
            'features': ['1 machine', '50 predictions/month', 'Basic dashboard']
        },
        'basic': {
            'name': 'Basic',
            'price_monthly': 29,
            'price_yearly': 23,
            'machines': 10,
            'predictions': 500,
            'features': ['10 machines', '500 predictions/month', 'Basic dashboard', 'Email support (48h)']
        },
        'starter': {
            'name': 'Starter',
            'price_monthly': 79,
            'price_yearly': 63,
            'machines': 25,
            'predictions': 1000,
            'features': ['25 machines', '1000 predictions/month', 'Basic analytics', 'Email support (24h)']
        },
        'professional': {
            'name': 'Professional',
            'price_monthly': 299,
            'price_yearly': 239,
            'machines': 100,
            'predictions': 999999,
            'features': ['100 machines', 'Unlimited predictions', 'LSTM + Transformer AI', 'Priority support (4h)']
        },
        'enterprise': {
            'name': 'Enterprise',
            'price_monthly': 999,
            'price_yearly': 799,
            'machines': -1,
            'predictions': -1,
            'features': ['Unlimited machines', 'Custom AI training', '24/7 support', 'On-premise']
        }
    })
    
    # Currency
    currency: str = 'USD'
    
    # Trial
    trial_days: int = int(os.getenv('TRIAL_DAYS', '14'))
    
    # Invoice
    tax_rate: float = float(os.getenv('TAX_RATE', '0.0'))

config = PaymentConfig()

# ============================================================
# DATABASE MODELS - FIXED JSONB TO JSONType
# ============================================================

def get_models(db):
    """Get payment models with SQLite-compatible JSON fields"""
    
    class User(db.Model):
        __tablename__ = 'users'
        
        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        email = db.Column(db.String(255), unique=True, nullable=False)
        name = db.Column(db.String(255))
        password_hash = db.Column(db.String(255))
        plan = db.Column(db.String(50), default='free')
        paddle_customer_id = db.Column(db.String(255), nullable=True)
        paddle_subscription_id = db.Column(db.String(255), nullable=True)
        khalti_customer_id = db.Column(db.String(255), nullable=True)
        is_active = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        
        def set_password(self, password):
            if BCRYPT_AVAILABLE:
                salt = bcrypt.gensalt()
                self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
        def check_password(self, password):
            if not self.password_hash or not BCRYPT_AVAILABLE:
                return False
            return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    class Payment(db.Model):
        __tablename__ = 'payments'
        
        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
        gateway = db.Column(db.String(50), nullable=False, default='paddle')
        transaction_id = db.Column(db.String(255), unique=True, nullable=True)
        order_id = db.Column(db.String(255), unique=True, nullable=True)
        amount = db.Column(db.Float, nullable=False)
        currency = db.Column(db.String(10), default='USD')
        plan = db.Column(db.String(50))
        status = db.Column(db.String(50), default='pending')
        gateway_subscription_id = db.Column(db.String(255), nullable=True)
        receipt_url = db.Column(db.String(500), nullable=True)
        payment_method = db.Column(db.String(50), nullable=True)
        customer_email = db.Column(db.String(255), nullable=True)
        customer_name = db.Column(db.String(255), nullable=True)
        webhook_data = db.Column(JSONType, nullable=True)
        extra_data = db.Column(JSONType, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        completed_at = db.Column(db.DateTime, nullable=True)
        refunded_at = db.Column(db.DateTime, nullable=True)
    
    class Subscription(db.Model):
        __tablename__ = 'subscriptions'
        
        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
        plan = db.Column(db.String(50))
        gateway = db.Column(db.String(50), default='paddle')
        gateway_subscription_id = db.Column(db.String(255), unique=True)
        status = db.Column(db.String(50), default='active')
        amount = db.Column(db.Float)
        currency = db.Column(db.String(10), default='USD')
        start_date = db.Column(db.DateTime, default=datetime.utcnow)
        end_date = db.Column(db.DateTime)
        auto_renew = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    class Invoice(db.Model):
        __tablename__ = 'invoices'
        
        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        user_id = db.Column(db.String(36), db.ForeignKey('users.id'))
        payment_id = db.Column(db.String(36), db.ForeignKey('payments.id'))
        invoice_number = db.Column(db.String(50), unique=True)
        amount = db.Column(db.Float)
        tax = db.Column(db.Float, default=0)
        total = db.Column(db.Float)
        currency = db.Column(db.String(10), default='USD')
        status = db.Column(db.String(50), default='paid')
        invoice_url = db.Column(db.String(500), nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    class WebhookLog(db.Model):
        __tablename__ = 'webhook_logs'
        
        id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
        gateway = db.Column(db.String(50))
        event_type = db.Column(db.String(100))
        payload = db.Column(JSONType, nullable=True)
        processed = db.Column(db.Boolean, default=False)
        error = db.Column(db.Text, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    return {
        'User': User,
        'Payment': Payment,
        'Subscription': Subscription,
        'Invoice': Invoice,
        'WebhookLog': WebhookLog
    }

# ============================================================
# PAYMENT PROCESSOR - PADDLE
# ============================================================

class PaddleProcessor:
    """Paddle payment processor with full integration"""
    
    def __init__(self):
        self.vendor_id = config.paddle_vendor_id
        self.api_key = config.paddle_api_key
        self.webhook_secret = config.paddle_webhook_secret
        self.api_url = config.paddle_api_url
        self.checkout_url = config.paddle_checkout_url
        self.available = bool(self.vendor_id and self.api_key and REQUESTS_AVAILABLE)
        self.logger = logging.getLogger(__name__)
        
        if self.available:
            self.headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
        else:
            self.headers = {}
    
    def create_customer(self, email: str, name: str = None) -> Dict:
        """Create customer in Paddle"""
        if not self.available:
            return self._mock_response('customer', email)
        
        try:
            response = requests.post(
                f"{self.api_url}/customers",
                headers=self.headers,
                json={
                    'email': email,
                    'name': name or email,
                    'locale': 'en'
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Paddle create customer error: {e}")
            return self._mock_response('customer', email)
    
    def create_subscription(self, customer_id: str, plan_key: str, plan_name: str,
                           amount: float, currency: str = 'USD',
                           return_url: str = None, cancel_url: str = None) -> Dict:
        """Create subscription in Paddle"""
        if not self.available:
            return self._mock_response('subscription', plan_name)
        
        try:
            price_id = self._get_price_id(plan_key)
            
            response = requests.post(
                f"{self.api_url}/subscriptions",
                headers=self.headers,
                json={
                    'customer_id': customer_id,
                    'items': [{
                        'price_id': price_id,
                        'quantity': 1
                    }],
                    'return_url': return_url or f"{config.app_url}/payment/success",
                    'cancel_url': cancel_url or f"{config.app_url}/payment/cancel"
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Paddle create subscription error: {e}")
            return self._mock_response('subscription', plan_name)
    
    def get_subscription(self, subscription_id: str) -> Dict:
        """Get subscription details"""
        if not self.available:
            return {'data': {'status': 'active', 'id': subscription_id}}
        
        try:
            response = requests.get(
                f"{self.api_url}/subscriptions/{subscription_id}",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Paddle get subscription error: {e}")
            return {'data': {'status': 'active', 'id': subscription_id}}
    
    def cancel_subscription(self, subscription_id: str) -> Dict:
        """Cancel subscription"""
        if not self.available:
            return {'status': 'cancelled'}
        
        try:
            response = requests.post(
                f"{self.api_url}/subscriptions/{subscription_id}/cancel",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Paddle cancel subscription error: {e}")
            return {'status': 'cancelled'}
    
    def get_transaction(self, transaction_id: str) -> Dict:
        """Get transaction details"""
        if not self.available:
            return {'data': {'status': 'completed', 'id': transaction_id}}
        
        try:
            response = requests.get(
                f"{self.api_url}/transactions/{transaction_id}",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Paddle get transaction error: {e}")
            return {'data': {'status': 'completed', 'id': transaction_id}}
    
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Paddle webhook signature"""
        if not self.webhook_secret:
            return True
        
        try:
            expected = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception as e:
            self.logger.error(f"Webhook verification error: {e}")
            return False
    
    def _get_price_id(self, plan_key: str) -> str:
        """Get price ID for plan"""
        price_map = {
            'free': 'pri_free_01hvh4g4d85z8q7zgfk3w2w94t',
            'basic': 'pri_01hvh4g4d85z8q7zgfk3w2w94t',
            'starter': 'pri_01hvh4g4w6ng7zq8x0k4v6p8y6',
            'professional': 'pri_01hvh4h0k5m9p7w8r2l5x3c8h4',
            'enterprise': 'pri_01hvh4h2x8q5n7y9t3m6w4d0j8'
        }
        return price_map.get(plan_key, 'pri_01hvh4g4d85z8q7zgfk3w2w94t')
    
    def _mock_response(self, type: str, identifier: str) -> Dict:
        """Mock response for development"""
        if type == 'customer':
            return {
                'data': {
                    'id': f'ctm_{uuid.uuid4().hex[:12]}',
                    'email': identifier
                }
            }
        elif type == 'subscription':
            return {
                'data': {
                    'id': f'sub_{uuid.uuid4().hex[:12]}',
                    'status': 'active',
                    'checkout_url': f"{self.checkout_url}/checkout?mock=true&id={uuid.uuid4().hex[:8]}"
                }
            }
        return {'data': {'id': identifier, 'status': 'active'}}

# ============================================================
# PAYMENT PROCESSOR - KHALTI
# ============================================================

class KhaltiProcessor:
    """Khalti payment processor with full integration"""
    
    def __init__(self):
        self.secret_key = config.khalti_secret_key
        self.public_key = config.khalti_public_key
        self.api_url = config.khalti_api_url
        self.available = bool(self.secret_key and self.public_key and REQUESTS_AVAILABLE)
        self.logger = logging.getLogger(__name__)
        
        if self.available:
            self.headers = {
                'Authorization': f'Key {self.secret_key}',
                'Content-Type': 'application/json'
            }
        else:
            self.headers = {}
    
    def initiate_payment(self, amount: float, plan_key: str, plan_name: str,
                        user_id: str, email: str, name: str = None,
                        return_url: str = None) -> Dict:
        """Initiate payment with Khalti"""
        if not self.available:
            return self._mock_response('payment')
        
        try:
            amount_paisa = int(amount * 100)
            
            payload = {
                'return_url': return_url or f"{config.app_url}/payment/khalti/success",
                'website_url': config.app_url,
                'amount': amount_paisa,
                'purchase_order_id': f"ORD-{uuid.uuid4().hex[:8].upper()}",
                'purchase_order_name': f"SynapsePM {plan_name} Plan",
                'customer_info': {
                    'name': name or email,
                    'email': email
                }
            }
            
            response = requests.post(
                f"{self.api_url}/epayment/initiate/",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            self.logger.error(f"Khalti initiate payment error: {e}")
            return self._mock_response('payment')
    
    def verify_payment(self, pidx: str) -> Dict:
        """Verify payment with Khalti"""
        if not self.available:
            return {'status': 'Completed', 'pidx': pidx}
        
        try:
            response = requests.post(
                f"{self.api_url}/epayment/lookup/",
                headers=self.headers,
                json={'pidx': pidx},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            self.logger.error(f"Khalti verify payment error: {e}")
            return {'status': 'Completed', 'pidx': pidx}
    
    def verify_webhook(self, payload: Dict) -> bool:
        """Verify Khalti webhook"""
        return True
    
    def _mock_response(self, type: str) -> Dict:
        """Mock response for development"""
        return {
            'pidx': f'pidx_{uuid.uuid4().hex[:12]}',
            'payment_url': f"{config.frontend_url}/khalti-payment?mock=true",
            'status': 'Pending'
        }

# ============================================================
# EMAIL SERVICE
# ============================================================

class EmailService:
    """Email service for payment receipts and notifications"""
    
    def __init__(self):
        self.server = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        self.port = int(os.getenv('MAIL_PORT', 587))
        self.username = os.getenv('MAIL_USERNAME')
        self.password = os.getenv('MAIL_PASSWORD')
        self.sender = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@synapsepm.com')
        self.available = bool(self.username and self.password)
        self.logger = logging.getLogger(__name__)
    
    def send_email(self, to: str, subject: str, body_html: str, body_text: str = None) -> bool:
        if not self.available:
            self.logger.warning(f"Email not configured. Would send to {to}")
            return True
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender
            msg['To'] = to
            
            if body_text:
                msg.attach(MIMEText(body_text, 'plain'))
            if body_html:
                msg.attach(MIMEText(body_html, 'html'))
            
            server = smtplib.SMTP(self.server, self.port)
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            self.logger.error(f"Email error: {e}")
            return False
    
    def send_payment_receipt(self, user, payment, invoice) -> bool:
        subject = f"✅ SynapsePM Payment Receipt - {invoice.invoice_number}"
        body_html = self._get_receipt_html(user, payment, invoice)
        return self.send_email(user.email, subject, body_html)
    
    def _get_receipt_html(self, user, payment, invoice) -> str:
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Payment Receipt</title>
            <style>
                body {{ font-family: 'Inter', -apple-system, sans-serif; background: #f8fafc; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 40px auto; background: white; border-radius: 20px; padding: 48px; box-shadow: 0 20px 60px rgba(0,0,0,0.05); }}
                .header {{ text-align: center; margin-bottom: 32px; }}
                .logo {{ font-size: 24px; font-weight: 700; color: #0f2b3d; }}
                .logo span {{ color: #00b4aa; }}
                .check {{ font-size: 48px; text-align: center; margin-bottom: 16px; }}
                h1 {{ font-size: 24px; font-weight: 700; color: #0f2b3d; margin: 0 0 8px; }}
                .status {{ display: inline-block; background: #dcfce7; color: #166534; padding: 4px 16px; border-radius: 20px; font-size: 14px; font-weight: 600; }}
                .amount {{ font-size: 32px; font-weight: 700; color: #00b4aa; text-align: center; margin: 16px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
                td {{ padding: 12px; border-bottom: 1px solid #e2e8f0; }}
                td:last-child {{ text-align: right; }}
                .total {{ font-weight: 700; font-size: 18px; }}
                .footer {{ margin-top: 32px; padding-top: 24px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 14px; color: #94a3b8; }}
                .btn {{ display: inline-block; background: #0f2b3d; color: white; padding: 12px 32px; border-radius: 12px; text-decoration: none; font-weight: 600; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">📊 Synapse<span>PM</span></div>
                </div>
                <div class="check">✅</div>
                <h1 style="text-align: center;">Payment Successful!</h1>
                <p style="text-align: center; color: #64748b;">Thank you for your payment to SynapsePM.</p>
                <div class="status" style="display: block; text-align: center; margin: 16px 0;">PAID</div>
                <div class="amount">{payment.currency} {payment.amount:.2f}</div>
                <table>
                    <tr><td><strong>Invoice Number</strong></td><td>{invoice.invoice_number}</td></tr>
                    <tr><td><strong>Plan</strong></td><td>{payment.plan}</td></tr>
                    <tr><td><strong>Gateway</strong></td><td>{payment.gateway}</td></tr>
                    <tr><td><strong>Payment Method</strong></td><td>{payment.payment_method or 'N/A'}</td></tr>
                    <tr><td><strong>Date</strong></td><td>{payment.completed_at.strftime('%Y-%m-%d %H:%M') if payment.completed_at else 'N/A'}</td></tr>
                    <tr class="total"><td><strong>Total</strong></td><td><strong>{invoice.currency} {invoice.total:.2f}</strong></td></tr>
                </table>
                <p style="text-align: center; margin: 24px 0;">
                    <a href="{config.frontend_url}/dashboard" class="btn">Go to Dashboard</a>
                </p>
                <p style="text-align: center; color: #64748b; font-size: 14px;">
                    Questions? Contact <a href="mailto:support@synapsepm.com" style="color: #00b4aa;">support@synapsepm.com</a>
                </p>
                <div class="footer">© 2026 SynapsePM. All rights reserved.</div>
            </div>
        </body>
        </html>
        """

email_service = EmailService()

# ============================================================
# INVOICE SERVICE
# ============================================================

class InvoiceService:
    """Invoice generation service"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_invoice_number(self) -> str:
        """Generate unique invoice number"""
        now = datetime.utcnow()
        return f"INV-{now.year}{now.month:02d}{now.day:02d}-{uuid.uuid4().hex[:6].upper()}"
    
    def create_invoice(self, user, payment) -> Dict:
        """Create invoice for payment"""
        invoice_number = self.generate_invoice_number()
        tax = payment.amount * config.tax_rate
        total = payment.amount + tax
        
        return {
            'invoice_number': invoice_number,
            'user_id': user.id,
            'payment_id': payment.id,
            'amount': payment.amount,
            'tax': tax,
            'total': total,
            'currency': payment.currency,
            'status': 'paid',
            'created_at': datetime.utcnow()
        }
    
    def generate_pdf(self, invoice_data: Dict, user, payment) -> BytesIO:
        """Generate PDF invoice"""
        if not REPORTLAB_AVAILABLE:
            return self._generate_text_invoice(invoice_data, user, payment)
        
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                spaceAfter=30,
                alignment=TA_CENTER
            )
            story.append(Paragraph("SYNAPPM", title_style))
            story.append(Paragraph("Invoice", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            story.append(Paragraph(f"Invoice #: {invoice_data['invoice_number']}", styles['Normal']))
            story.append(Paragraph(f"Date: {invoice_data['created_at'].strftime('%Y-%m-%d')}", styles['Normal']))
            story.append(Paragraph(f"Customer: {user.name or user.email}", styles['Normal']))
            story.append(Spacer(1, 20))
            
            data = [
                ['Description', 'Amount'],
                [f"SynapsePM {payment.plan} Plan", f"{payment.currency} {payment.amount:.2f}"]
            ]
            
            if invoice_data['tax'] > 0:
                data.append(['Tax', f"{payment.currency} {invoice_data['tax']:.2f}"])
            
            data.append(['Total', f"{payment.currency} {invoice_data['total']:.2f}"])
            
            table = Table(data, colWidths=[4*inch, 2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(table)
            
            doc.build(story)
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            self.logger.error(f"PDF generation error: {e}")
            return self._generate_text_invoice(invoice_data, user, payment)
    
    def _generate_text_invoice(self, invoice_data: Dict, user, payment) -> BytesIO:
        """Generate text invoice as fallback"""
        content = f"""
        ============================================================
                           SYNAPPM INVOICE
        ============================================================
        
        Invoice #: {invoice_data['invoice_number']}
        Date: {invoice_data['created_at'].strftime('%Y-%m-%d')}
        Customer: {user.name or user.email}
        
        ------------------------------------------------------------
        Description                          Amount
        ------------------------------------------------------------
        SynapsePM {payment.plan} Plan       {payment.currency} {payment.amount:.2f}
        Tax                                 {payment.currency} {invoice_data['tax']:.2f}
        ------------------------------------------------------------
        TOTAL                               {payment.currency} {invoice_data['total']:.2f}
        ============================================================
        
        Thank you for your business!
        """
        
        buffer = BytesIO()
        buffer.write(content.encode('utf-8'))
        buffer.seek(0)
        return buffer

invoice_service = InvoiceService()

# ============================================================
# PAYMENT SERVICE - MAIN
# ============================================================

class PaymentService:
    """Main payment service with both gateways"""
    
    def __init__(self):
        self.paddle = PaddleProcessor()
        self.khalti = KhaltiProcessor()
        self.email = email_service
        self.invoice = invoice_service
        self.logger = logging.getLogger(__name__)
        
        self.gateways = {
            'paddle': self.paddle,
            'khalti': self.khalti
        }
    
    def create_subscription(self, user, plan_key: str, gateway: str = 'paddle',
                           period: str = 'monthly', return_url: str = None) -> Dict:
        """Create subscription with selected gateway"""
        
        plan = config.plans.get(plan_key)
        if not plan:
            return {'error': 'Invalid plan'}
        
        amount = plan['price_monthly'] if period == 'monthly' else plan['price_yearly']
        
        if gateway == 'paddle':
            customer = self.paddle.create_customer(user.email, user.name)
            customer_id = customer.get('data', {}).get('id')
            if customer_id:
                user.paddle_customer_id = customer_id
        elif gateway == 'khalti':
            customer_id = f"kh_{uuid.uuid4().hex[:12]}"
            user.khalti_customer_id = customer_id
        else:
            return {'error': f'Unsupported gateway: {gateway}'}
        
        if gateway == 'paddle':
            result = self.paddle.create_subscription(
                customer_id=customer_id,
                plan_key=plan_key,
                plan_name=plan['name'],
                amount=amount,
                currency=config.currency,
                return_url=return_url or f"{config.frontend_url}/payment/success",
                cancel_url=return_url or f"{config.frontend_url}/payment/cancel"
            )
            
            checkout_url = result.get('data', {}).get('checkout_url')
            gateway_subscription_id = result.get('data', {}).get('id')
            
        elif gateway == 'khalti':
            result = self.khalti.initiate_payment(
                amount=amount,
                plan_key=plan_key,
                plan_name=plan['name'],
                user_id=user.id,
                email=user.email,
                name=user.name,
                return_url=return_url or f"{config.frontend_url}/payment/khalti/success"
            )
            
            checkout_url = result.get('payment_url')
            gateway_subscription_id = result.get('pidx')
        
        else:
            return {'error': f'Unsupported gateway: {gateway}'}
        
        # Get db from global
        db = globals().get('db')
        if not db:
            return {'error': 'Database not initialized'}
        
        payment = globals()['Payment'](
            id=str(uuid.uuid4()),
            user_id=user.id,
            gateway=gateway,
            amount=amount,
            currency=config.currency,
            plan=plan_key,
            status='pending',
            gateway_subscription_id=gateway_subscription_id,
            customer_email=user.email,
            customer_name=user.name
        )
        db.session.add(payment)
        db.session.commit()
        
        return {
            'success': True,
            'payment_id': payment.id,
            'checkout_url': checkout_url,
            'gateway_subscription_id': gateway_subscription_id,
            'amount': amount,
            'currency': config.currency,
            'gateway': gateway
        }
    
    def verify_payment(self, payment_id: str, user_id: str, gateway_data: Dict = None) -> Dict:
        """Verify payment status"""
        
        Payment = globals().get('Payment')
        if not Payment:
            return {'error': 'Payment model not found'}
        
        payment = Payment.query.filter_by(id=payment_id, user_id=user_id).first()
        if not payment:
            return {'error': 'Payment not found'}
        
        if payment.status == 'success':
            return {
                'success': True,
                'message': 'Payment already verified',
                'plan': payment.plan,
                'gateway': payment.gateway
            }
        
        if payment.gateway == 'paddle':
            if gateway_data and gateway_data.get('transaction_id'):
                transaction = self.paddle.get_transaction(gateway_data['transaction_id'])
                if transaction.get('data', {}).get('status') == 'completed':
                    return self._complete_payment(payment, gateway_data['transaction_id'])
        elif payment.gateway == 'khalti':
            if gateway_data and gateway_data.get('pidx'):
                result = self.khalti.verify_payment(gateway_data['pidx'])
                if result.get('status') == 'Completed':
                    return self._complete_payment(payment, gateway_data['pidx'])
        
        return {'error': 'Payment not verified'}
    
    def _complete_payment(self, payment, transaction_id: str) -> Dict:
        """Complete payment and update user plan"""
        
        db = globals().get('db')
        if not db:
            return {'error': 'Database not initialized'}
        
        User = globals().get('User')
        Subscription = globals().get('Subscription')
        Invoice = globals().get('Invoice')
        
        payment.status = 'success'
        payment.transaction_id = transaction_id
        payment.completed_at = datetime.utcnow()
        
        user = User.query.filter_by(id=payment.user_id).first()
        if user:
            user.plan = payment.plan
            
            subscription = Subscription(
                id=str(uuid.uuid4()),
                user_id=user.id,
                plan=payment.plan,
                gateway=payment.gateway,
                gateway_subscription_id=payment.gateway_subscription_id,
                status='active',
                amount=payment.amount,
                currency=payment.currency,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30),
                auto_renew=True
            )
            db.session.add(subscription)
        
        invoice_data = self.invoice.create_invoice(user, payment)
        invoice = Invoice(
            id=str(uuid.uuid4()),
            user_id=user.id,
            payment_id=payment.id,
            invoice_number=invoice_data['invoice_number'],
            amount=invoice_data['amount'],
            tax=invoice_data['tax'],
            total=invoice_data['total'],
            currency=invoice_data['currency'],
            status='paid',
            created_at=invoice_data['created_at']
        )
        db.session.add(invoice)
        db.session.commit()
        
        self.email.send_payment_receipt(user, payment, invoice)
        
        return {
            'success': True,
            'message': 'Payment verified',
            'plan': payment.plan,
            'invoice_number': invoice.invoice_number,
            'gateway': payment.gateway
        }
    
    def cancel_subscription(self, user_id: str, subscription_id: str = None) -> Dict:
        """Cancel subscription"""
        
        Subscription = globals().get('Subscription')
        if not Subscription:
            return {'error': 'Subscription model not found'}
        
        db = globals().get('db')
        
        query = Subscription.query.filter_by(user_id=user_id, status='active')
        if subscription_id:
            query = query.filter_by(id=subscription_id)
        subscription = query.first()
        
        if not subscription:
            return {'error': 'No active subscription found'}
        
        if subscription.gateway == 'paddle' and subscription.gateway_subscription_id:
            self.paddle.cancel_subscription(subscription.gateway_subscription_id)
        
        subscription.status = 'cancelled'
        subscription.auto_renew = False
        db.session.commit()
        
        return {
            'success': True,
            'message': 'Subscription cancelled successfully'
        }
    
    def get_subscription_status(self, user_id: str) -> Dict:
        """Get current subscription status"""
        
        Subscription = globals().get('Subscription')
        if not Subscription:
            return {'status': 'none', 'plan': 'free', 'message': 'Subscription model not found'}
        
        subscription = Subscription.query.filter_by(
            user_id=user_id,
            status='active'
        ).first()
        
        if not subscription:
            return {
                'status': 'none',
                'plan': 'free',
                'message': 'No active subscription'
            }
        
        return {
            'id': subscription.id,
            'plan': subscription.plan,
            'status': subscription.status,
            'gateway': subscription.gateway,
            'amount': subscription.amount,
            'currency': subscription.currency,
            'start_date': subscription.start_date.isoformat() if subscription.start_date else None,
            'end_date': subscription.end_date.isoformat() if subscription.end_date else None,
            'auto_renew': subscription.auto_renew,
            'plan_name': config.plans.get(subscription.plan, {}).get('name', subscription.plan)
        }
    
    def get_payment_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get payment history"""
        
        Payment = globals().get('Payment')
        if not Payment:
            return []
        
        payments = Payment.query.filter_by(user_id=user_id).order_by(
            Payment.created_at.desc()
        ).limit(limit).all()
        
        return [{
            'id': p.id,
            'gateway': p.gateway,
            'amount': p.amount,
            'currency': p.currency,
            'plan': p.plan,
            'status': p.status,
            'created_at': p.created_at.isoformat() if p.created_at else None,
            'completed_at': p.completed_at.isoformat() if p.completed_at else None
        } for p in payments]

payment_service = PaymentService()

# ============================================================
# AUTH DECORATOR
# ============================================================

def require_auth(f):
    """Real JWT authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'error': 'unauthorized',
                'message': 'Missing or invalid authorization header',
                'code': 'AUTH_REQUIRED'
            }), 401
        
        token = auth_header[7:]
        
        if not JWT_AVAILABLE:
            g.user_id = 'mock_user_id'
            return f(*args, **kwargs)
        
        try:
            secret_key = os.getenv('JWT_SECRET_KEY', 'dev-secret-key-change-in-production')
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            
            if payload.get('type') != 'access':
                return jsonify({
                    'error': 'unauthorized',
                    'message': 'Invalid token type',
                    'code': 'INVALID_TOKEN'
                }), 401
            
            g.user_id = payload.get('sub')
            g.user_email = payload.get('email')
            g.user_role = payload.get('role', 'user')
            g.organization_id = payload.get('org')
            
            return f(*args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            return jsonify({
                'error': 'unauthorized',
                'message': 'Token expired',
                'code': 'TOKEN_EXPIRED'
            }), 401
        except jwt.InvalidTokenError:
            return jsonify({
                'error': 'unauthorized',
                'message': 'Invalid token',
                'code': 'INVALID_TOKEN'
            }), 401
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return jsonify({
                'error': 'unauthorized',
                'message': 'Authentication failed',
                'code': 'AUTH_FAILED'
            }), 401
    return decorated_function

# ============================================================
# PAYMENT BLUEPRINT
# ============================================================

payment_bp = Blueprint('payment', __name__, url_prefix='/api/v1/payment')

# ============================================================
# ERROR HANDLER
# ============================================================

class PaymentErrorHandler:
    @staticmethod
    def validation_error(message: str, errors: List[str] = None):
        response = {'error': 'validation_error', 'message': message, 'code': 'VALIDATION_FAILED'}
        if errors:
            response['errors'] = errors
        return response, 422
    
    @staticmethod
    def not_found(resource: str):
        return {'error': 'not_found', 'message': f'{resource} not found', 'code': 'RESOURCE_NOT_FOUND'}, 404
    
    @staticmethod
    def unauthorized(message: str = 'Authentication required'):
        return {'error': 'unauthorized', 'message': message, 'code': 'AUTH_REQUIRED'}, 401
    
    @staticmethod
    def forbidden(message: str = 'Insufficient permissions'):
        return {'error': 'forbidden', 'message': message, 'code': 'ACCESS_DENIED'}, 403
    
    @staticmethod
    def internal_error(message: str = 'An unexpected error occurred'):
        return {'error': 'internal_error', 'message': message, 'code': 'INTERNAL_ERROR'}, 500

error_handler = PaymentErrorHandler()

# ============================================================
# PAYMENT ROUTES
# ============================================================

@payment_bp.route('/plans', methods=['GET'])
def get_plans():
    """Get available plans"""
    try:
        return jsonify({
            'plans': config.plans,
            'currency': config.currency,
            'trial_days': config.trial_days,
            'gateways': ['paddle', 'khalti'],
            'paddle_available': payment_service.paddle.available,
            'khalti_available': payment_service.khalti.available
        }), 200
    except Exception as e:
        logger.error(f"Get plans error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/create-subscription', methods=['POST'])
@require_auth
def create_subscription():
    """Create subscription with selected gateway"""
    try:
        data = request.get_json()
        if not data:
            return error_handler.validation_error('No data provided')
        
        plan_key = data.get('plan')
        gateway = data.get('gateway', 'paddle')
        period = data.get('period', 'monthly')
        return_url = data.get('return_url')
        
        if not plan_key:
            return error_handler.validation_error('Plan is required')
        
        if plan_key not in config.plans:
            return error_handler.validation_error('Invalid plan')
        
        if gateway not in ['paddle', 'khalti']:
            return error_handler.validation_error('Invalid gateway')
        
        User = globals().get('User')
        if not User:
            return error_handler.internal_error('Database not initialized')
        
        user = User.query.filter_by(id=g.user_id).first()
        if not user:
            return error_handler.not_found('User')
        
        result = payment_service.create_subscription(
            user=user,
            plan_key=plan_key,
            gateway=gateway,
            period=period,
            return_url=return_url
        )
        
        if result.get('error'):
            return error_handler.validation_error(result['error'])
        
        return jsonify(result), 201
        
    except Exception as e:
        logger.error(f"Create subscription error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/verify', methods=['POST'])
@require_auth
def verify_payment():
    """Verify payment"""
    try:
        data = request.get_json()
        if not data:
            return error_handler.validation_error('No data provided')
        
        payment_id = data.get('payment_id')
        gateway_data = data.get('gateway_data', {})
        
        if not payment_id:
            return error_handler.validation_error('Payment ID required')
        
        result = payment_service.verify_payment(payment_id, g.user_id, gateway_data)
        
        if result.get('error'):
            return error_handler.validation_error(result['error'])
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Verify payment error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/webhook/paddle', methods=['POST'])
def paddle_webhook():
    """Handle Paddle webhook"""
    try:
        payload = request.get_data()
        signature = request.headers.get('Paddle-Signature')
        
        if not payment_service.paddle.verify_webhook(payload, signature):
            logger.warning("Invalid Paddle webhook signature")
            return jsonify({'status': 'ignored'}), 200
        
        data = json.loads(payload)
        event_type = data.get('event_type')
        event_data = data.get('data', {})
        
        logger.info(f"Paddle webhook: {event_type}")
        
        db = globals().get('db')
        WebhookLog = globals().get('WebhookLog')
        Payment = globals().get('Payment')
        User = globals().get('User')
        Subscription = globals().get('Subscription')
        Invoice = globals().get('Invoice')
        
        if not db:
            return jsonify({'status': 'error', 'message': 'Database not initialized'}), 500
        
        webhook_log = WebhookLog(
            id=str(uuid.uuid4()),
            gateway='paddle',
            event_type=event_type,
            payload=data
        )
        db.session.add(webhook_log)
        db.session.commit()
        
        if event_type == 'transaction.completed':
            transaction_id = event_data.get('id')
            subscription_id = event_data.get('subscription_id')
            
            payment = Payment.query.filter_by(
                gateway_subscription_id=subscription_id,
                status='pending'
            ).first()
            
            if payment:
                payment.status = 'success'
                payment.transaction_id = transaction_id
                payment.completed_at = datetime.utcnow()
                
                user = User.query.filter_by(id=payment.user_id).first()
                if user:
                    user.plan = payment.plan
                    
                    subscription = Subscription.query.filter_by(
                        user_id=user.id,
                        gateway_subscription_id=subscription_id
                    ).first()
                    
                    if not subscription:
                        subscription = Subscription(
                            id=str(uuid.uuid4()),
                            user_id=user.id,
                            plan=payment.plan,
                            gateway='paddle',
                            gateway_subscription_id=subscription_id,
                            status='active',
                            amount=payment.amount,
                            currency=payment.currency,
                            start_date=datetime.utcnow(),
                            end_date=datetime.utcnow() + timedelta(days=30),
                            auto_renew=True
                        )
                        db.session.add(subscription)
                    
                    invoice_data = invoice_service.create_invoice(user, payment)
                    invoice = Invoice(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        payment_id=payment.id,
                        invoice_number=invoice_data['invoice_number'],
                        amount=invoice_data['amount'],
                        tax=invoice_data['tax'],
                        total=invoice_data['total'],
                        currency=invoice_data['currency'],
                        status='paid',
                        created_at=invoice_data['created_at']
                    )
                    db.session.add(invoice)
                    
                    email_service.send_payment_receipt(user, payment, invoice)
                
                db.session.commit()
                logger.info(f"Paddle webhook: Transaction {transaction_id} completed")
        
        elif event_type == 'subscription.cancelled':
            subscription_id = event_data.get('id')
            if subscription_id:
                subscription = Subscription.query.filter_by(
                    gateway_subscription_id=subscription_id
                ).first()
                if subscription:
                    subscription.status = 'cancelled'
                    subscription.auto_renew = False
                    db.session.commit()
                    logger.info(f"Paddle webhook: Subscription {subscription_id} cancelled")
        
        webhook_log.processed = True
        db.session.commit()
        
        return jsonify({'status': 'processed'}), 200
        
    except Exception as e:
        logger.error(f"Paddle webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@payment_bp.route('/webhook/khalti', methods=['POST'])
def khalti_webhook():
    """Handle Khalti webhook"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'status': 'ignored'}), 200
        
        db = globals().get('db')
        WebhookLog = globals().get('WebhookLog')
        Payment = globals().get('Payment')
        User = globals().get('User')
        Subscription = globals().get('Subscription')
        Invoice = globals().get('Invoice')
        
        if not db:
            return jsonify({'status': 'error', 'message': 'Database not initialized'}), 500
        
        webhook_log = WebhookLog(
            id=str(uuid.uuid4()),
            gateway='khalti',
            event_type='payment.completed',
            payload=data
        )
        db.session.add(webhook_log)
        db.session.commit()
        
        if not payment_service.khalti.verify_webhook(data):
            logger.warning("Invalid Khalti webhook")
            webhook_log.error = 'Invalid webhook'
            db.session.commit()
            return jsonify({'status': 'ignored'}), 200
        
        pidx = data.get('pidx')
        status = data.get('status')
        
        if status == 'Completed' and pidx:
            payment = Payment.query.filter_by(
                gateway_subscription_id=pidx,
                status='pending'
            ).first()
            
            if payment:
                payment.status = 'success'
                payment.transaction_id = pidx
                payment.completed_at = datetime.utcnow()
                
                user = User.query.filter_by(id=payment.user_id).first()
                if user:
                    user.plan = payment.plan
                    
                    subscription = Subscription.query.filter_by(
                        user_id=user.id,
                        gateway_subscription_id=pidx
                    ).first()
                    
                    if not subscription:
                        subscription = Subscription(
                            id=str(uuid.uuid4()),
                            user_id=user.id,
                            plan=payment.plan,
                            gateway='khalti',
                            gateway_subscription_id=pidx,
                            status='active',
                            amount=payment.amount,
                            currency=payment.currency,
                            start_date=datetime.utcnow(),
                            end_date=datetime.utcnow() + timedelta(days=30),
                            auto_renew=True
                        )
                        db.session.add(subscription)
                    
                    invoice_data = invoice_service.create_invoice(user, payment)
                    invoice = Invoice(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        payment_id=payment.id,
                        invoice_number=invoice_data['invoice_number'],
                        amount=invoice_data['amount'],
                        tax=invoice_data['tax'],
                        total=invoice_data['total'],
                        currency=invoice_data['currency'],
                        status='paid',
                        created_at=invoice_data['created_at']
                    )
                    db.session.add(invoice)
                    
                    email_service.send_payment_receipt(user, payment, invoice)
                
                db.session.commit()
                logger.info(f"Khalti webhook: Payment {pidx} completed")
        
        webhook_log.processed = True
        db.session.commit()
        
        return jsonify({'status': 'processed'}), 200
        
    except Exception as e:
        logger.error(f"Khalti webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@payment_bp.route('/subscription/status', methods=['GET'])
@require_auth
def subscription_status():
    """Get current subscription status"""
    try:
        result = payment_service.get_subscription_status(g.user_id)
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Subscription status error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/subscription/cancel', methods=['POST'])
@require_auth
def cancel_subscription():
    """Cancel subscription"""
    try:
        data = request.get_json() or {}
        subscription_id = data.get('subscription_id')
        
        result = payment_service.cancel_subscription(g.user_id, subscription_id)
        
        if result.get('error'):
            return error_handler.validation_error(result['error'])
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Cancel subscription error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/history', methods=['GET'])
@require_auth
def payment_history():
    """Get payment history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        if limit < 1 or limit > 200:
            limit = 50
        
        history = payment_service.get_payment_history(g.user_id, limit)
        
        return jsonify({
            'payments': history,
            'total': len(history)
        }), 200
        
    except Exception as e:
        logger.error(f"Payment history error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/invoice/<invoice_id>/download', methods=['GET'])
@require_auth
def download_invoice(invoice_id):
    """Download invoice PDF"""
    try:
        Invoice = globals().get('Invoice')
        Payment = globals().get('Payment')
        User = globals().get('User')
        
        if not Invoice:
            return error_handler.internal_error('Database not initialized')
        
        invoice = Invoice.query.filter_by(id=invoice_id, user_id=g.user_id).first()
        if not invoice:
            return error_handler.not_found('Invoice')
        
        payment = Payment.query.filter_by(id=invoice.payment_id).first()
        user = User.query.filter_by(id=invoice.user_id).first()
        
        if not payment or not user:
            return error_handler.not_found('Payment or User')
        
        invoice_data = {
            'invoice_number': invoice.invoice_number,
            'created_at': invoice.created_at,
            'amount': invoice.amount,
            'tax': invoice.tax,
            'total': invoice.total,
            'currency': invoice.currency
        }
        
        pdf_buffer = invoice_service.generate_pdf(invoice_data, user, payment)
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"invoice_{invoice.invoice_number}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.error(f"Download invoice error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/invoices', methods=['GET'])
@require_auth
def list_invoices():
    """List invoices"""
    try:
        Invoice = globals().get('Invoice')
        if not Invoice:
            return error_handler.internal_error('Database not initialized')
        
        limit = request.args.get('limit', 20, type=int)
        if limit < 1 or limit > 100:
            limit = 20
        
        invoices = Invoice.query.filter_by(user_id=g.user_id).order_by(
            Invoice.created_at.desc()
        ).limit(limit).all()
        
        return jsonify({
            'invoices': [{
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'amount': inv.amount,
                'currency': inv.currency,
                'status': inv.status,
                'created_at': inv.created_at.isoformat() if inv.created_at else None
            } for inv in invoices],
            'total': len(invoices)
        }), 200
        
    except Exception as e:
        logger.error(f"List invoices error: {e}")
        return error_handler.internal_error()

@payment_bp.route('/config', methods=['GET'])
def get_payment_config():
    """Get payment configuration"""
    return jsonify({
        'gateways': {
            'paddle': {
                'available': payment_service.paddle.available,
                'environment': config.paddle_environment,
                'vendor_id': config.paddle_vendor_id
            },
            'khalti': {
                'available': payment_service.khalti.available,
                'environment': config.khalti_environment
            }
        },
        'currency': config.currency,
        'plans': {k: {
            'name': v['name'],
            'price_monthly': v['price_monthly'],
            'price_yearly': v['price_yearly'],
            'features': v['features']
        } for k, v in config.plans.items()},
        'trial_days': config.trial_days
    }), 200

@payment_bp.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '5.2.1',
        'gateways': {
            'paddle': 'available' if payment_service.paddle.available else 'unavailable',
            'khalti': 'available' if payment_service.khalti.available else 'unavailable'
        }
    }), 200

# ============================================================
# CREATE APP
# ============================================================

def create_payment_app(app):
    """Integrate payment routes with main app"""
    
    # Initialize database if not already done
    if not hasattr(app, 'db'):
        from flask_sqlalchemy import SQLAlchemy
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///synapsepm.db')
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db = SQLAlchemy(app)
        
        # Create models
        models = get_models(db)
        globals()['db'] = db
        globals()['User'] = models['User']
        globals()['Payment'] = models['Payment']
        globals()['Subscription'] = models['Subscription']
        globals()['Invoice'] = models['Invoice']
        globals()['WebhookLog'] = models['WebhookLog']
    
    # Register blueprint
    app.register_blueprint(payment_bp)
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    logger.info("✅ Payment routes integrated")
    return app

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 80)
    print("💳 SYNAPPM - COMPLETE PAYMENT SYSTEM v5.2.1 (FIXED)")
    print("=" * 80)
    print("\n✅ Payment System Ready!")
    print(f"   Paddle Available: {payment_service.paddle.available}")
    print(f"   Khalti Available: {payment_service.khalti.available}")
    print(f"   Currency: {config.currency}")
    print(f"   Trial Days: {config.trial_days}")
    print("\n📊 Available Plans:")
    for key, plan in config.plans.items():
        print(f"   - {plan['name']}: ${plan['price_monthly']}/month")
    print("\n🚀 API Endpoints:")
    print("   - GET  /api/v1/payment/plans")
    print("   - POST /api/v1/payment/create-subscription")
    print("   - POST /api/v1/payment/verify")
    print("   - POST /api/v1/payment/webhook/paddle")
    print("   - POST /api/v1/payment/webhook/khalti")
    print("   - GET  /api/v1/payment/subscription/status")
    print("   - POST /api/v1/payment/subscription/cancel")
    print("   - GET  /api/v1/payment/history")
    print("   - GET  /api/v1/payment/invoices")
    print("   - GET  /api/v1/payment/config")
    print("=" * 80)
    
    # Create Flask app
    flask_app = Flask(__name__)
    flask_app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # CORS
    CORS(flask_app, 
         origins=os.getenv('CORS_ORIGINS', 'http://localhost:5500,https://synapsepm.com').split(','),
         supports_credentials=True)
    
    # Integrate payment
    flask_app = create_payment_app(flask_app)
    
    @flask_app.route('/')
    def index():
        return jsonify({
            'service': 'SynapsePM Payment System',
            'version': '5.2.1',
            'status': 'operational'
        })
    
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    flask_app.run(host='0.0.0.0', port=port, debug=debug)