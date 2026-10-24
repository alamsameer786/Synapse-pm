#!/usr/bin/env python3
"""
SYNAPSEPM v27.1.0 — PRIVATE HF MODEL RELEASE FIX
====================================================
Preserves the existing SaaS, auth, IoT, billing, admin, reporting and frontend APIs while adding the v23/v25 trustworthy-ML contract and global-production hardening:

FIXED IN v17.1.0:
  ✅ FIXED: g.start_time crash on 429 — every request returned 500
  ✅ FIXED: Rate limiter was per-IP and 2000/day — killed dashboards
           Now: per-user key, no global limit, sensitive endpoints only
  ✅ FIXED: TooManyRequests handler returns JSON, not HTML
  ✅ FIXED: machine_type native PG ENUM rejected free-form strings
           (see migrate_enum_to_varchar() below)
  ✅ FIXED: Paddle API key validation — warns if wrong key format
  ✅ FIXED: WS auth now enforces session (sid) revocation
  ✅ FIXED: WS closes with code 1008 on auth failure (frontend stops retry)
  ✅ FIXED: /alerts/mark-all-read bulk endpoint added
  ✅ FIXED: /payments/verify/<uuid> endpoint for post-checkout verification
  ✅ ADDED: machine_type sanitization in create_machine
  ✅ ADDED: /health exposes full payment gateway status
  ✅ ADDED: Paddle key-type startup validation
  ✅ ADDED: RATE_LIMIT_AI raised to 2000/hr (was 5000/hr combined)
  ✅ PRESERVED: Every single feature from v17.0.0

PRESERVED FROM v17.0.0:
  ✅ Real MQTT subscriber
  ✅ Real TCP socket verification on /machines/<id>/connect
  ✅ Per-machine device keys (MachineAPIKey + CRUD)
  ✅ X-Device-Key auth on /sensor-data
  ✅ /api/v1/payments/paddle-config
  ✅ Risk score derived from real model output; heuristic prediction fallback removed
  ✅ /datasets/analyze returns full profile
  ✅ /datasets list endpoint
  ✅ Khalti optional
  ✅ All admin, reports, billing, careers, contact, enterprise
  ✅ MFA, OAuth, sessions, audit, cleanup, Prometheus

ADDITIONAL FIXES IN v20.0.0:
  ✅ FIXED: legacy PostgreSQL predictions.risk_score NUMERIC(5,4) overflow
  ✅ FIXED: champion selection now prioritizes live-sensor-compatible feature sets
  ✅ FIXED: model compatibility fallback logs the exact available numeric features
  ✅ FIXED: sensor and simulation values are clamped before persistence
  ✅ FIXED: machine-limit response includes plan and limit metadata
  ✅ FIXED: Paddle server API-key validation accepts only server-key prefixes

  FEATURE-CONTRACT / HETEROGENEOUS-DATA FIXES IN v20.0.0:
  ✅ FIXED: model/scaler feature-count mismatches are rejected before transform
  ✅ FIXED: model-specific feature names/order are enforced when available
  ✅ ADDED: scaler/model feature-contract discovery from trained artifacts
  ✅ ADDED: safe feature aliases without unsafe unit substitution
  ✅ ADDED: heterogeneous CSV/TXT/XLSX/JSON ingestion with malformed single-column XLSX recovery
  ✅ ADDED: explicit compatibility diagnostics (missing/extra/mapped/expected features)
  ✅ FIXED: prediction organization_id is populated for dataset, machine and batch predictions
  ✅ FIXED: legacy predictions.organization_id schema is added automatically when missing
  ✅ FIXED: all Prediction writes are tenant-scoped
  ⚠️  IMPORTANT: no incompatible 54-feature model is forced onto 7/8-feature data; a real compatible
      trained artifact is required for trained-model inference. Incompatible inputs abstain; no heuristic prediction fallback exists.
"""

# ============================================================================
# v20.0.0 PRODUCTION FIX CHECKLIST — IMPLEMENTED IN THIS FILE
# ============================================================================
# [x] Prevent RobustScaler/model feature-count mismatch before transform.
# [x] Enforce trained-model feature names and exact training order when present.
# [x] Discover n_features_in_, feature_names_in_ and serialized ModelArtifact.feature_names.
# [x] Support heterogeneous feature counts and row counts without padding/truncation.
# [x] Use safe semantic aliases; never silently convert incompatible units.
# [x] Reject incompatible models with actionable missing/available-feature details.
# [x] Removed diagnostic/heuristic fallback: no trained model means abstention.
# [x] Recover malformed single-column XLSX files containing embedded CSV data.
# [x] Persist Prediction.organization_id for machine, dataset, manual and batch writes.
# [x] Add legacy predictions.organization_id automatically when missing.
# [x] Keep existing model-selection, schema, sensor-clamping and Paddle hardening.
# [x] Keep existing routes/features; changes are additive and compatibility-focused.
# [x] Validate Python syntax with py_compile.
# [x] Validate original v19 code path was patched rather than rewritten.
# [NOTE] A real 7/8-feature trained model must still exist in the model registry;
#        application code cannot truthfully manufacture a trained model artifact.
# ============================================================================

import os
import sys
import json
import hashlib
import hmac
import logging
import uuid
import secrets
import shutil
import random
import math
import time
import queue as _queue
import re
import signal
import socket
import traceback
import threading
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from functools import wraps
from pathlib import Path
from collections import OrderedDict
from urllib.parse import urlencode, urlparse
import zipfile
from logging.handlers import RotatingFileHandler

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ============================================================
# TIMEZONE / JSON SAFETY
# ============================================================

def ensure_aware(dt):
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def utcnow():
    return datetime.now(timezone.utc)


def json_safe(obj):
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, memoryview):
        try:
            return obj.tobytes().decode('utf-8', errors='replace')
        except Exception:
            return str(obj)
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode('utf-8', errors='replace')
        except Exception:
            return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [json_safe(v) for v in obj]
    return str(obj)


# ============================================================
# IMPORTS
# ============================================================

from dotenv import load_dotenv
from cryptography.fernet import Fernet
import jwt
import redis
from flask import (
    Flask, jsonify, Blueprint, request, g,
    send_file, Response, redirect
)
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_compress import Compress
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import TooManyRequests
from sqlalchemy import (
    or_, func, text, inspect, Index, UniqueConstraint,
    DateTime, CHAR
)
from sqlalchemy.exc import IntegrityError

try:
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
    PG_UUID_AVAILABLE = True
except ImportError:
    PG_UUID_AVAILABLE = False
    PG_UUID = None

try:
    from flask_sock import Sock
    FLASK_SOCK_AVAILABLE = True
except ImportError:
    FLASK_SOCK_AVAILABLE = False
    Sock = None

try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

try:
    import torch
    import numpy as np
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    torch = None
    np = None

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False
    joblib = None

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False
    pyotp = None

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    sentry_sdk = None
    FlaskIntegration = None
    SENTRY_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    pd = None

try:
    import tensorflow as tf
    TENSORFLOW_AVAILABLE = True
except Exception:
    TENSORFLOW_AVAILABLE = False
    tf = None

try:
    import onnxruntime as ort
    ONNXRUNTIME_AVAILABLE = True
except Exception:
    ONNXRUNTIME_AVAILABLE = False
    ort = None

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False
    Image = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerificationError, InvalidHash
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    PasswordHasher = None
    VerificationError = None
    InvalidHash = None

try:
    import paho.mqtt.client as mqtt_client_lib
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    mqtt_client_lib = None


# ============================================================
# LOAD .env
# ============================================================

current_file = Path(__file__).resolve()
project_root = current_file.parent

for env_path in [project_root / '.env', project_root.parent / '.env',
                 Path(os.environ.get('ENV_FILE', '.env'))]:
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"✅ Loaded .env from: {env_path}")
        break


def generate_fernet_key():
    return Fernet.generate_key().decode()


# ============================================================
# CONFIG
# ============================================================

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    JWT_REFRESH_SECRET = os.environ.get('JWT_REFRESH_SECRET')
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')

    ENV = os.environ.get('FLASK_ENV', 'development')
    DEBUG = ENV == 'development'
    IS_PRODUCTION = ENV == 'production'

    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))

    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///synapsepm.db')
    DB_AUTO_CREATE = os.environ.get('DB_AUTO_CREATE', 'false').lower() == 'true'
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    _db_opts = {'pool_pre_ping': True}
    if not DATABASE_URL.startswith('sqlite'):
        _db_opts.update({
            'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
            'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW', 20)),
            'pool_recycle': int(os.environ.get('DB_POOL_RECYCLE', 3600)),
            'pool_timeout': int(os.environ.get('DB_POOL_TIMEOUT', 30)),
        })
    SQLALCHEMY_ENGINE_OPTIONS = _db_opts

    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CORS_ORIGINS = os.environ.get(
        'CORS_ORIGINS',
        'http://localhost:5500,http://127.0.0.1:5500,http://localhost:5000,'
        'http://localhost:3000,http://127.0.0.1:5000,http://localhost:8080,'
        'http://127.0.0.1:8080,http://localhost:8000,http://127.0.0.1:8000'
    ).split(',')
    CORS_ORIGINS = [origin.strip().rstrip('/') for origin in CORS_ORIGINS if origin.strip()]

    JWT_ACCESS_EXPIRY_MINUTES = int(os.environ.get('JWT_ACCESS_EXPIRY_MINUTES', 600))
    JWT_REFRESH_EXPIRY_DAYS = int(os.environ.get('JWT_REFRESH_EXPIRY_DAYS', 30))
    JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
    JWT_ISSUER = os.environ.get('JWT_ISSUER', 'synapsepm')
    JWT_AUDIENCE = os.environ.get('JWT_AUDIENCE', 'synapsepm-api')

    PASSWORD_EXPIRY_DAYS = int(os.environ.get('PASSWORD_EXPIRY_DAYS', 90))
    MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', 5))
    LOCKOUT_DURATION_MINUTES = int(os.environ.get('LOCKOUT_DURATION_MINUTES', 15))
    PASSWORD_RESET_MAX_ATTEMPTS = int(os.environ.get('PASSWORD_RESET_MAX_ATTEMPTS', 5))
    PASSWORD_RESET_LOCKOUT_MINUTES = int(os.environ.get('PASSWORD_RESET_LOCKOUT_MINUTES', 15))

    FRONTEND_FOLDER = os.environ.get(
        'FRONTEND_FOLDER',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
    )
    APP_NAME = os.environ.get('APP_NAME', 'SynapsePM')
    APP_VERSION = os.environ.get('APP_VERSION', '33.0.0')
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5000')

    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@synapsepm.com')
    MAIL_SUPPRESS_SEND = os.environ.get(
        'MAIL_SUPPRESS_SEND',
        'true' if not os.environ.get('MAIL_USERNAME') else 'false'
    ).lower() == 'true'

    # ==========================================================
    # PADDLE (primary — worldwide)
    # ==========================================================
    PADDLE_API_KEY = os.environ.get('PADDLE_API_KEY')
    PADDLE_PUBLIC_KEY = os.environ.get('PADDLE_PUBLIC_KEY')
    PADDLE_ENV = os.environ.get('PADDLE_ENV', 'sandbox')
    PADDLE_WEBHOOK_SECRET = os.environ.get('PADDLE_WEBHOOK_SECRET')
    PADDLE_CLIENT_TOKEN = os.environ.get('PADDLE_CLIENT_TOKEN', '')

    try:
        PADDLE_PRICE_IDS = json.loads(os.environ.get('PADDLE_PRICE_IDS_JSON', '{}'))
    except Exception:
        PADDLE_PRICE_IDS = {}

    # ==========================================================
    # MQTT (real IoT device ingestion)
    # ==========================================================
    ENABLE_MQTT = os.environ.get('ENABLE_MQTT', 'false').lower() == 'true'
    MQTT_BROKER = os.environ.get('MQTT_BROKER', 'localhost')
    MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))
    MQTT_USERNAME = os.environ.get('MQTT_USERNAME') or None
    MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD') or None
    MQTT_TOPIC_PREFIX = os.environ.get('MQTT_TOPIC_PREFIX', 'synapsepm')
    MQTT_QOS = int(os.environ.get('MQTT_QOS', 1))

    PLANS = {
        'free': {
            'id': 'free', 'name': 'Free', 'price': 0, 'price_display': 'Free',
            'currency': 'USD',
            'features': ['1 machine', '50 predictions/month', 'Basic dashboard'],
            'max_users': 1, 'max_machines': 1, 'max_api_calls': 100,
            'max_predictions': 50, 'prediction_period': 'month', 'max_storage_gb': 0.1,
        },
        'starter': {
            'id': 'starter', 'name': 'Starter', 'price': 2900,
            'price_display': '$29', 'currency': 'USD',
            'features': ['5 machines', '500 predictions/day', 'Basic analytics', 'Email support'],
            'max_users': 5, 'max_machines': 5, 'max_api_calls': 5000,
            'max_predictions': 500, 'prediction_period': 'day', 'max_storage_gb': 1,
        },
        'professional': {
            'id': 'professional', 'name': 'Professional', 'price': 7900,
            'price_display': '$79', 'currency': 'USD',
            'features': ['10 machines', '1000 predictions/day', 'Advanced analytics', 'Priority support'],
            'max_users': 10, 'max_machines': 10, 'max_api_calls': 10000,
            'max_predictions': 1000, 'prediction_period': 'day', 'max_storage_gb': 5,
        },
        'business': {
            'id': 'business', 'name': 'Business', 'price': 29900,
            'price_display': '$299', 'currency': 'USD',
            'features': ['50 machines', 'Unlimited predictions', 'All AI models', 'Priority support'],
            'max_users': 50, 'max_machines': 50, 'max_api_calls': 100000,
            'max_predictions': None, 'prediction_period': 'unlimited', 'max_storage_gb': 50,
        },
        'enterprise': {
            'id': 'enterprise', 'name': 'Enterprise', 'price': None,
            'price_display': 'Custom', 'currency': 'USD',
            'features': ['Unlimited machines', 'Unlimited predictions', 'Custom models',
                         'Dedicated support', 'On-premise'],
            'max_users': 999, 'max_machines': 999, 'max_api_calls': 999999,
            'max_predictions': None, 'prediction_period': 'unlimited',
            'max_storage_gb': 999, 'is_custom': True,
        }
    }

    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', f'{APP_URL}/api/v1/auth/google/callback')
    GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID')
    GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET')
    GITHUB_REDIRECT_URI = os.environ.get('GITHUB_REDIRECT_URI', f'{APP_URL}/api/v1/auth/github/callback')
    LINKEDIN_CLIENT_ID = os.environ.get('LINKEDIN_CLIENT_ID')
    LINKEDIN_CLIENT_SECRET = os.environ.get('LINKEDIN_CLIENT_SECRET')
    LINKEDIN_REDIRECT_URI = os.environ.get('LINKEDIN_REDIRECT_URI', f'{APP_URL}/api/v1/auth/linkedin/callback')

    ENABLE_MFA = os.environ.get('ENABLE_MFA', 'true').lower() == 'true'
    ENABLE_SOCIAL_LOGIN = os.environ.get('ENABLE_SOCIAL_LOGIN', 'true').lower() == 'true'
    ENABLE_API_KEYS = os.environ.get('ENABLE_API_KEYS', 'true').lower() == 'true'
    ENABLE_AUDIT_LOGGING = os.environ.get('ENABLE_AUDIT_LOGGING', 'true').lower() == 'true'
    ENABLE_RATE_LIMITING = os.environ.get('ENABLE_RATE_LIMITING', 'true').lower() == 'true'

    # ---- FIX: much more generous limits, no global default ----
    # Per-endpoint limits only. Read endpoints are unlimited.
    RATE_LIMIT_LOGIN = int(os.environ.get('RATE_LIMIT_LOGIN', 20))
    RATE_LIMIT_AI = int(os.environ.get('RATE_LIMIT_AI', 2000))
    RATE_LIMIT_CAREER = int(os.environ.get('RATE_LIMIT_CAREER', 10))
    RATE_LIMIT_CONTACT = int(os.environ.get('RATE_LIMIT_CONTACT', 10))

    # ==========================================================
    # PWA — Progressive Web App (free native install, no certs)
    # ==========================================================
    ENABLE_PWA = os.environ.get('ENABLE_PWA', 'true').lower() == 'true'
    PWA_SHORT_NAME = os.environ.get('PWA_SHORT_NAME', 'SynapsePM')
    PWA_THEME_COLOR = os.environ.get('PWA_THEME_COLOR', '#00b4aa')
    PWA_BG_COLOR = os.environ.get('PWA_BG_COLOR', '#0f2b3d')

    TRIAL_DAYS = int(os.environ.get('TRIAL_DAYS', 14))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 100 * 1024 * 1024))

    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    )
    DOWNLOAD_FOLDER = os.environ.get(
        'DOWNLOAD_FOLDER',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
    )
    DATASET_EXTENSIONS = set(
        os.environ.get('DATASET_EXTENSIONS', 'csv,txt,dat,xlsx,json').split(',')
    )
    RESUME_EXTENSIONS = set(
        os.environ.get('RESUME_EXTENSIONS', 'pdf,doc,docx,txt').split(',')
    )

    DESKTOP_RELEASES_FOLDER = os.environ.get(
        'DESKTOP_RELEASES_FOLDER',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'releases', 'desktop')
    )
    MOBILE_RELEASES_FOLDER = os.environ.get(
        'MOBILE_RELEASES_FOLDER',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'releases', 'mobile')
    )
    DESKTOP_WINDOWS_FILE = os.environ.get('DESKTOP_WINDOWS_FILE', 'SynapsePM-Setup-Windows.exe')
    DESKTOP_MACOS_FILE = os.environ.get('DESKTOP_MACOS_FILE', 'SynapsePM-macOS.dmg')
    DESKTOP_LINUX_FILE = os.environ.get('DESKTOP_LINUX_FILE', 'SynapsePM-Linux.AppImage')
    MOBILE_ANDROID_FILE = os.environ.get('MOBILE_ANDROID_FILE', 'SynapsePM-Android.apk')
    MOBILE_IOS_FILE = os.environ.get('MOBILE_IOS_FILE', 'SynapsePM-iOS.ipa')

    # Local ZIP path. In Render, a private Hugging Face release can be downloaded
    # here at startup by setting HF_MODEL_REPO, HF_MODEL_FILENAME and HF_TOKEN.
    MODEL_RELEASE_ZIP = os.environ.get(
        'MODEL_RELEASE_ZIP',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trained_model.zip')
    )
    MODEL_MAX_PRODUCTION = min(7, max(1, int(os.environ.get('MODEL_MAX_PRODUCTION', 7))))
    MODEL_REQUIRE_VALIDATED = os.environ.get('MODEL_REQUIRE_VALIDATED', 'false').lower() == 'true'
    PRODUCTION_READINESS_ENFORCE = os.environ.get('PRODUCTION_READINESS_ENFORCE', 'true' if IS_PRODUCTION else 'false').lower() == 'true'
    MODEL_CACHE_SIZE = max(1, int(os.environ.get('MODEL_CACHE_SIZE', 50)))
    MODEL_CHECKSUM_REQUIRED = os.environ.get('MODEL_CHECKSUM_REQUIRED', 'false').lower() == 'true'
    PREDICTION_SCHEMA_VERSION = os.environ.get('PREDICTION_SCHEMA_VERSION', '1.0')
    MIN_SENSOR_QUALITY = float(os.environ.get('MIN_SENSOR_QUALITY', '0.30'))
    FAMILY_AMBIGUITY_MARGIN = float(os.environ.get('FAMILY_AMBIGUITY_MARGIN', '0.10'))
    OOD_P01_P99 = os.environ.get('OOD_P01_P99', 'true').lower() == 'true'
    # Diagnostic/heuristic prediction fallback intentionally removed: all predictions require a real trained model.
    MAX_MODEL_FILE_MB = int(os.environ.get('MAX_MODEL_FILE_MB', 2048))
    MODEL_RUNTIME_MODULE = os.environ.get('MODEL_RUNTIME_MODULE', '').strip()
    MODEL_RUNTIME_CLASSES = tuple(x.strip() for x in os.environ.get('MODEL_RUNTIME_CLASSES', 'FastPreprocessor,SelfLearningEnsemble').split(',') if x.strip())
    ALLOWED_EXTENSIONS = set(
        os.environ.get(
            'ALLOWED_EXTENSIONS',
            'txt,pdf,png,jpg,jpeg,gif,csv,json,xml,zip,xlsx,onnx,h5,py,pkl,doc,docx'
        ).split(',')
    )

    ML_MODEL_PATH = os.environ.get(
        'ML_MODEL_PATH',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
    )
    # Recover automatically when a stale .env points at a missing model root.
    _ml_root = os.environ.get('ML_MODEL_PATH', '')
    _app_dir = os.path.dirname(os.path.abspath(__file__))
    if _ml_root and os.path.isdir(_ml_root):
        pass
    else:
        _candidate = os.path.join(_app_dir, 'models', 'models')
        if os.path.isdir(_candidate):
            ML_MODEL_PATH = _candidate
        elif os.path.isdir(os.path.join(_app_dir, 'models')):
            ML_MODEL_PATH = os.path.join(_app_dir, 'models')
    ML_USE_GPU = os.environ.get('ML_USE_GPU', 'true').lower() == 'true'

    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 10 * 1024 * 1024))
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 10))
    LOG_FORMAT = os.environ.get(
        'LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    CRON_API_KEY = os.environ.get('CRON_API_KEY')
    DESKTOP_APP_VERSION = os.environ.get('DESKTOP_APP_VERSION', '1.0.0')
    MOBILE_APP_VERSION = os.environ.get('MOBILE_APP_VERSION', '1.0.0')

    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    ADMIN_FIRST_NAME = os.environ.get('ADMIN_FIRST_NAME', 'Super')
    ADMIN_LAST_NAME = os.environ.get('ADMIN_LAST_NAME', 'Admin')
    ADMIN_ROLE = os.environ.get('ADMIN_ROLE', 'super_admin')
    ADMIN_FORCE_RESET = os.environ.get('ADMIN_FORCE_RESET', 'true').lower() == 'true'

    MAX_PAGE_SIZE = int(os.environ.get('MAX_PAGE_SIZE', 100))
    CACHE_TTL = int(os.environ.get('CACHE_TTL', 3600))
    SESSION_CACHE_TTL = int(os.environ.get('SESSION_CACHE_TTL', 300))

    AUDIT_RETENTION_DAYS = int(os.environ.get('AUDIT_RETENTION_DAYS', 90))
    REPORT_RETENTION_DAYS = int(os.environ.get('REPORT_RETENTION_DAYS', 30))
    DOWNLOAD_RETENTION_DAYS = int(os.environ.get('DOWNLOAD_RETENTION_DAYS', 30))
    CLEANUP_INTERVAL_SECONDS = int(os.environ.get('CLEANUP_INTERVAL_SECONDS', 3600))
    ENABLE_CLEANUP_THREAD = os.environ.get('ENABLE_CLEANUP_THREAD', 'true').lower() == 'true'
    ENABLE_METRICS = os.environ.get('ENABLE_METRICS', 'true').lower() == 'true'
    SCHEMA_AUTO_PATCH = os.environ.get('SCHEMA_AUTO_PATCH', 'true').lower() == 'true'
    ORG_DAILY_AI_CAP = int(os.environ.get('ORG_DAILY_AI_CAP', 10000))
    SENTRY_DSN = os.environ.get('SENTRY_DSN')


config = Config()

# Render ephemeral filesystem safety: /data is persistent only when a disk is
# explicitly mounted in the Render service settings. Never assume it exists.
if os.environ.get('RENDER'):
    for _var in ('MODEL_RELEASE_ZIP', 'ML_MODEL_PATH', 'UPLOAD_FOLDER', 'DOWNLOAD_FOLDER'):
        _value = os.environ.get(_var, '').strip()
        if _value.startswith('/data/') and not Path('/data').exists():
            logger.warning('%s=%s points to /data, but /data is not mounted; configure a Render Persistent Disk or use an ephemeral path.', _var, _value)


def validate_config():
    if config.IS_PRODUCTION:
        required = {
            'SECRET_KEY': config.SECRET_KEY,
            'JWT_SECRET_KEY': config.JWT_SECRET_KEY,
            'JWT_REFRESH_SECRET': config.JWT_REFRESH_SECRET,
            'ENCRYPTION_KEY': config.ENCRYPTION_KEY,
            'DATABASE_URL': config.DATABASE_URL,
            'APP_URL': config.APP_URL,
            'FRONTEND_URL': config.FRONTEND_URL,
            'ADMIN_PASSWORD': config.ADMIN_PASSWORD,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError('Missing production config: ' + ', '.join(missing))
    else:
        config.SECRET_KEY = config.SECRET_KEY or secrets.token_urlsafe(48)
        config.JWT_SECRET_KEY = config.JWT_SECRET_KEY or secrets.token_urlsafe(48)
        config.JWT_REFRESH_SECRET = config.JWT_REFRESH_SECRET or secrets.token_urlsafe(48)
        config.ENCRYPTION_KEY = config.ENCRYPTION_KEY or generate_fernet_key()

    # ---- FIX: strict Paddle server-key format validation ----
    if config.PADDLE_API_KEY:
        valid_prefixes = ('pdl_live_apikey_', 'pdl_sdbx_apikey_')
        if not config.PADDLE_API_KEY.startswith(valid_prefixes):
            print("⚠️  WARNING: PADDLE_API_KEY does not start with "
                  "'pdl_live_apikey_' or 'pdl_sdbx_apikey_'.")
            print(f"   Got prefix: {config.PADDLE_API_KEY[:20]}...")
            print("   Server API keys are found in Paddle → Developer Tools → "
                  "Authentication, NOT the client-side tokens.")

    # ---- Production warning: validation requirement has been relaxed ----
    if config.IS_PRODUCTION and not config.MODEL_REQUIRE_VALIDATED:
        print("⚠️  WARNING: MODEL_REQUIRE_VALIDATED=false in PRODUCTION.")
        print("   Unvalidated model artifacts will be allowed to serve live")
        print("   predictions. This is acceptable only for a controlled beta.")
        print("   Set MODEL_REQUIRE_VALIDATED=true before general availability.")


validate_config()

for folder in [
    config.ML_MODEL_PATH,
    config.UPLOAD_FOLDER,
    os.path.join(config.UPLOAD_FOLDER, 'avatars'),
    os.path.join(config.UPLOAD_FOLDER, 'resumes'),
    config.DOWNLOAD_FOLDER,
    os.path.join(config.DOWNLOAD_FOLDER, 'reports'),
    config.DESKTOP_RELEASES_FOLDER,
    config.MOBILE_RELEASES_FOLDER,
    'logs',
]:
    os.makedirs(folder, exist_ok=True)

print(f"\n{'='*70}")
print(f" 🚀 {config.APP_NAME} v{config.APP_VERSION}")
print(f"{'='*70}")
print(f" Environment: {config.ENV}")
print(f" Database: {config.DATABASE_URL}")
print(f" Schema auto-patch: {'ON' if config.SCHEMA_AUTO_PATCH else 'OFF'}")
print(f" Admin force-reset: {'ON' if config.ADMIN_FORCE_RESET else 'OFF'}")
print(f" Flask-Sock: {'YES' if FLASK_SOCK_AVAILABLE else 'NO'}")
print(f" Prometheus: {'YES' if PROMETHEUS_AVAILABLE else 'NO'}")
print(f" MQTT: {'YES' if MQTT_AVAILABLE else 'NO'}")
print(f"{'='*70}\n")


# ============================================================
# LOGGING
# ============================================================

os.makedirs('logs', exist_ok=True)

_fh = RotatingFileHandler(
    config.LOG_FILE, maxBytes=config.LOG_MAX_BYTES,
    backupCount=config.LOG_BACKUP_COUNT, encoding='utf-8'
)
_fh.setFormatter(logging.Formatter(config.LOG_FORMAT))

_ah = RotatingFileHandler(
    'logs/audit.log', maxBytes=config.LOG_MAX_BYTES,
    backupCount=config.LOG_BACKUP_COUNT, encoding='utf-8'
)
_ah.setFormatter(logging.Formatter(config.LOG_FORMAT))

_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter(config.LOG_FORMAT))

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format=config.LOG_FORMAT,
    handlers=[_fh, _ah, _sh]
)
logger = logging.getLogger(__name__)


# ============================================================
# PROMETHEUS
# ============================================================

if PROMETHEUS_AVAILABLE and config.ENABLE_METRICS:
    REQUEST_COUNT = Counter(
        'synapsepm_requests_total', 'Total requests',
        ['method', 'endpoint', 'status']
    )
    REQUEST_LATENCY = Histogram(
        'synapsepm_request_duration_seconds', 'Latency',
        ['method', 'endpoint']
    )
    ML_PREDICTIONS = Counter(
        'synapsepm_predictions_total', 'Predictions',
        ['status', 'model_type', 'dataset_family']
    )
    ML_PREDICTIONS_ABSTAINED = Counter(
        'synapsepm_predictions_abstained_total', 'Prediction abstentions', ['reason']
    )
    MODEL_LOADS = Counter(
        'synapsepm_model_loads_total', 'Model load attempts', ['family', 'status']
    )
    MODEL_CACHE_HITS = Counter(
        'synapsepm_model_cache_hits_total', 'Model cache hits'
    )
    MODEL_CACHE_MISSES = Counter(
        'synapsepm_model_cache_misses_total', 'Model cache misses'
    )
    MODEL_CACHE_EVICTIONS = Counter(
        'synapsepm_model_cache_evictions_total', 'Model cache evictions'
    )
    PAYMENTS = Counter(
        'synapsepm_payments_total', 'Payments',
        ['gateway', 'status']
    )
    CAREER_SUBMISSIONS = Counter(
        'synapsepm_career_submissions_total', 'Career submissions', ['status']
    )
    CONTACT_SUBMISSIONS = Counter(
        'synapsepm_contact_submissions_total', 'Contact submissions', ['status']
    )
else:
    REQUEST_COUNT = REQUEST_LATENCY = ML_PREDICTIONS = ML_PREDICTIONS_ABSTAINED = MODEL_LOADS = MODEL_CACHE_HITS = MODEL_CACHE_MISSES = MODEL_CACHE_EVICTIONS = PAYMENTS = None
    CAREER_SUBMISSIONS = CONTACT_SUBMISSIONS = None


# ============================================================
# EXTENSIONS
# ============================================================

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
compress = Compress()


# ---- FIX: per-user rate limit key + NO global default ----
def _rate_limit_key():
    """Authenticated users get a per-user bucket; anonymous get per-IP."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        try:
            payload = jwt.decode(
                auth.split(' ', 1)[1].strip(),
                config.JWT_SECRET_KEY,
                algorithms=[config.JWT_ALGORITHM],
                options={'verify_iss': False, 'verify_aud': False,
                         'verify_exp': False},
            )
            uid = payload.get('user_id')
            if uid:
                return f"user:{uid}:ip:{get_remote_address()}"
        except Exception:
            pass
    return f"ip:{get_remote_address()}"


limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[],   # FIX: no global limit
    storage_uri=config.REDIS_URL,
    strategy="moving-window",
    headers_enabled=True,
)


def get_redis():
    if not config.REDIS_URL:
        return None
    try:
        c = redis.Redis.from_url(
            config.REDIS_URL, decode_responses=True,
            socket_timeout=5, socket_connect_timeout=5,
            retry_on_timeout=True, health_check_interval=30
        )
        c.ping()
        return c
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None


redis_client = get_redis()

if not redis_client:
    # Redis is preferred for multi-process realtime, distributed rate limits,
    # revocation state and shared sessions.  The realtime layer below also has
    # an in-process fallback so a single-process deployment remains usable.
    config.ENABLE_RATE_LIMITING = False
    logger.warning("Redis not available — using in-process realtime fallback; distributed rate limiting/session state is disabled.")


# ============================================================
# REAL-TIME BROADCAST HELPERS
# ============================================================
# Redis is the preferred cross-process pub/sub backend.  When it is not
# available, these in-process queues keep realtime working for single-process
# deployments (the common local/dev configuration).
_LOCAL_SUBSCRIBERS = {'admin_events': [], 'user_events': []}
_LOCAL_SUB_LOCK = threading.RLock()


def _local_publish(channel, message_str):
    with _LOCAL_SUB_LOCK:
        subscribers = list(_LOCAL_SUBSCRIBERS.get(channel, []))
    for q in subscribers:
        try:
            q.put_nowait(message_str)
        except _queue.Full:
            # Drop the oldest queued event so one slow browser cannot block
            # publishers or consume unbounded memory.
            try:
                q.get_nowait()
                q.put_nowait(message_str)
            except Exception:
                pass
        except Exception:
            with _LOCAL_SUB_LOCK:
                try:
                    _LOCAL_SUBSCRIBERS.get(channel, []).remove(q)
                except (ValueError, KeyError):
                    pass


def _local_subscribe(channel):
    q = _queue.Queue(maxsize=200)
    with _LOCAL_SUB_LOCK:
        _LOCAL_SUBSCRIBERS.setdefault(channel, []).append(q)
    return q


def _local_unsubscribe(channel, q):
    with _LOCAL_SUB_LOCK:
        try:
            _LOCAL_SUBSCRIBERS.get(channel, []).remove(q)
        except (ValueError, KeyError):
            pass


def _event_message(event_type, payload=None, org_id=None):
    data = {
        'type': event_type,
        **(payload or {}),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    if org_id:
        data['org_id'] = str(org_id)
    return json.dumps(data, default=str)


def publish_admin_event(event_type, payload=None):
    msg = _event_message(event_type, payload)
    try:
        if redis_client:
            redis_client.publish('admin_events', msg)
        else:
            _local_publish('admin_events', msg)
    except Exception as e:
        logger.debug(f'publish_admin_event failed: {e}')
        _local_publish('admin_events', msg)


def publish_user_event(org_id, event_type, payload=None):
    if not org_id:
        return
    msg = _event_message(event_type, payload, org_id=org_id)
    try:
        if redis_client:
            redis_client.publish(f'user_events:{org_id}', msg)
            redis_client.publish('user_events', msg)
            # Mirror user activity to the admin stream so admin dashboards
            # receive machine/prediction/alert/report/billing activity live.
            redis_client.publish('admin_events', msg)
        else:
            _local_publish('user_events', msg)
            _local_publish('admin_events', msg)
    except Exception as e:
        logger.debug(f'publish_user_event failed: {e}')
        _local_publish('user_events', msg)
        _local_publish('admin_events', msg)


def broadcast_both(event_type, payload=None, org_id=None):
    publish_admin_event(event_type, payload)
    if org_id:
        publish_user_event(org_id, event_type, payload)
    else:
        msg = _event_message(event_type, payload)
        try:
            if redis_client:
                redis_client.publish('user_events', msg)
            else:
                _local_publish('user_events', msg)
        except Exception:
            _local_publish('user_events', msg)


# ============================================================
# ENCRYPTION
# ============================================================

class EncryptionService:
    def __init__(self):
        self.fernet = Fernet(config.ENCRYPTION_KEY.encode())
        logger.info("✅ Encryption service initialized")

    def encrypt(self, data):
        return self.fernet.encrypt(data.encode()).decode() if data else data

    def decrypt(self, enc):
        if not enc:
            return enc
        try:
            return self.fernet.decrypt(enc.encode()).decode()
        except Exception as e:
            logger.error(f"Decrypt failed: {e}")
            raise ValueError("Decryption failed")


encryption_service = EncryptionService()


# ============================================================
# UUID / JSON TYPES
# ============================================================

class UUIDType(db.TypeDecorator):
    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql' and PG_UUID_AVAILABLE:
            return dialect.type_descriptor(PG_UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return str(value) if value is not None else None


class JSONType(db.TypeDecorator):
    impl = db.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, default=str)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, memoryview):
            try:
                value = value.tobytes()
            except Exception:
                value = bytes(value)
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode('utf-8')
            except Exception:
                value = value.decode('utf-8', errors='replace')
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            try:
                return json.loads(s)
            except Exception:
                return value
        return value


# ============================================================
# PASSWORD SERVICE
# ============================================================

class PasswordService:
    def __init__(self):
        if ARGON2_AVAILABLE:
            self.hasher = PasswordHasher()
            logger.info("✅ Argon2id initialized")
        else:
            self.hasher = None
            if config.IS_PRODUCTION:
                raise RuntimeError('argon2-cffi required in production')
            logger.warning("⚠️ Argon2 unavailable — dev PBKDF2 fallback")

    def hash_password(self, pwd):
        if self.hasher:
            return self.hasher.hash(pwd), True
        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt.encode(), 100000).hex()
        return f"pbkdf2_sha256$100000${salt}${h}", False

    def verify_password(self, pwd, hashed):
        if self.hasher and hashed and not hashed.startswith('pbkdf2_sha256$'):
            try:
                self.hasher.verify(hashed, pwd)
                if self.hasher.check_needs_rehash(hashed):
                    return True, True
                return True, False
            except (VerificationError, InvalidHash):
                return False, False
        try:
            parts = hashed.split('$')
            if len(parts) == 4 and parts[0] == 'pbkdf2_sha256':
                _, _, salt, hv = parts
                computed = hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt.encode(), 100000).hex()
                return hmac.compare_digest(computed, hv), False
        except Exception:
            pass
        return False, False


password_service = PasswordService()


# ============================================================
# MODELS
# ============================================================

class TimestampMixin:
    created_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True
    )
    updated_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )


class SoftDeleteMixin:
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(DateTime(timezone=True), nullable=True)
    deleted_by = db.Column(db.String(36), nullable=True)

    def soft_delete(self, by=None):
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.deleted_by = by


class Organization(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = 'organizations'

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    logo_url = db.Column(db.String(500), nullable=True)
    website = db.Column(db.String(500), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    primary_email = db.Column(db.String(255), nullable=False, default='admin@synapsepm.com')
    primary_phone = db.Column(db.String(50), nullable=True)
    plan = db.Column(db.String(50), nullable=False, default='FREE', index=True)
    subscription_status = db.Column(db.String(50), nullable=False, default='trialing', index=True)
    subscription_id = db.Column(db.String(200), nullable=True)
    trial_ends_at = db.Column(DateTime(timezone=True), nullable=True, index=True)
    trial_reminder_sent = db.Column(db.Boolean, default=False)
    trial_expired_notified = db.Column(db.Boolean, default=False)
    billing_email = db.Column(db.String(255), nullable=True)
    billing_address = db.Column(JSONType, nullable=True)
    max_users = db.Column(db.Integer, default=5)
    max_machines = db.Column(db.Integer, default=10)
    max_api_calls = db.Column(db.Integer, default=1000)
    max_storage_gb = db.Column(db.Numeric(10, 2), default=1.0)
    settings = db.Column(JSONType, default=dict)
    feature_flags = db.Column(JSONType, default=dict)
    is_suspended = db.Column(db.Boolean, default=False, nullable=False, index=True)
    suspended_at = db.Column(DateTime(timezone=True), nullable=True)
    suspension_reason = db.Column(db.String(500), nullable=True)
    white_label = db.Column(JSONType, nullable=True)
    custom_domain = db.Column(db.String(200), nullable=True)

    users = db.relationship('User', backref='organization_ref', lazy='dynamic')
    machines = db.relationship('Machine', backref='organization_ref', lazy='dynamic')

    @property
    def is_trial_active(self):
        if not self.trial_ends_at:
            return False
        return datetime.now(timezone.utc) < ensure_aware(self.trial_ends_at)

    @property
    def trial_days_remaining(self):
        if not self.trial_ends_at:
            return 0
        delta = ensure_aware(self.trial_ends_at) - datetime.now(timezone.utc)
        return max(0, delta.days)

    def is_trial_expired(self):
        if not self.trial_ends_at:
            return True
        return datetime.now(timezone.utc) >= ensure_aware(self.trial_ends_at)

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'name': self.name, 'slug': self.slug,
            'logo_url': self.logo_url, 'website': self.website, 'industry': self.industry,
            'primary_email': self.primary_email, 'primary_phone': self.primary_phone,
            'plan': self.plan, 'subscription_status': self.subscription_status,
            'trial_ends_at': self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            'trial_days_remaining': self.trial_days_remaining,
            'is_trial_active': self.is_trial_active,
            'is_trial_expired': self.is_trial_expired(),
            'is_suspended': self.is_suspended,
            'max_users': self.max_users, 'max_machines': self.max_machines,
            'max_api_calls': self.max_api_calls,
            'max_storage_gb': float(self.max_storage_gb) if self.max_storage_gb else 0,
            'settings': self.settings or {}, 'feature_flags': self.feature_flags or {},
            'white_label': self.white_label, 'custom_domain': self.custom_domain,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class User(TimestampMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        UniqueConstraint('email', name='uq_user_email'),
        UniqueConstraint('username', name='uq_user_username'),
        Index('idx_user_org', 'organization_id'),
    )

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    mfa_secret = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(100), nullable=True)
    password_changed_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    password_expires_at = db.Column(DateTime(timezone=True), nullable=True)
    password_history = db.Column(JSONType, default=list)
    sso_id = db.Column(db.String(255), nullable=True, index=True)
    sso_provider = db.Column(db.String(50), nullable=True)
    is_sso_user = db.Column(db.Boolean, default=False, nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    display_name = db.Column(db.String(200), nullable=True)
    job_title = db.Column(db.String(100), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    role = db.Column(db.String(50), nullable=False, default='viewer', index=True)
    permissions = db.Column(JSONType, default=dict)
    plan = db.Column(db.String(50), nullable=False, default='free')
    status = db.Column(db.String(50), nullable=False, default='active', index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_locked = db.Column(db.Boolean, default=False, nullable=False)
    is_mfa_enabled = db.Column(db.Boolean, default=False, nullable=False)
    mfa_backup_codes = db.Column(db.String(500), nullable=True)
    login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(DateTime(timezone=True), nullable=True)
    login_count = db.Column(db.Integer, default=0, nullable=False)
    verification_token = db.Column(db.String(256), nullable=True, index=True)
    verification_token_expires_at = db.Column(DateTime(timezone=True), nullable=True)
    reset_otp_hash = db.Column(db.String(128), nullable=True)
    reset_otp_expires_at = db.Column(DateTime(timezone=True), nullable=True)
    reset_otp_attempts = db.Column(db.Integer, default=0)
    reset_locked_until = db.Column(DateTime(timezone=True), nullable=True)
    password_reset_token = db.Column(db.String(256), nullable=True, index=True)
    password_reset_expires_at = db.Column(DateTime(timezone=True), nullable=True)
    login_history = db.Column(JSONType, default=list)
    last_login_at = db.Column(DateTime(timezone=True), nullable=True, index=True)
    last_login_ip = db.Column(db.String(50), nullable=True)
    last_activity_at = db.Column(DateTime(timezone=True), nullable=True)
    language = db.Column(db.String(10), nullable=False, default='en')
    timezone = db.Column(db.String(100), nullable=False, default='UTC')
    notification_preferences = db.Column(JSONType, default=dict)
    ui_preferences = db.Column(JSONType, default=dict)
    user_metadata = db.Column(JSONType, default=dict)
    deactivated_at = db.Column(DateTime(timezone=True), nullable=True)

    def set_password(self, pwd):
        hashed, _ = password_service.hash_password(pwd)
        self.password_hash = hashed
        self.password_changed_at = datetime.now(timezone.utc)
        self.password_expires_at = datetime.now(timezone.utc) + timedelta(days=config.PASSWORD_EXPIRY_DAYS)
        history = self.password_history or []
        if not isinstance(history, list):
            history = []
        history.append({
            'changed_at': datetime.now(timezone.utc).isoformat(),
            'hash_preview': hashed[:20]
        })
        self.password_history = history[-5:]

    def check_password(self, pwd):
        if not self.password_hash:
            return False
        valid, needs_rehash = password_service.verify_password(pwd, self.password_hash)
        if valid and needs_rehash:
            new_hash, _ = password_service.hash_password(pwd)
            self.password_hash = new_hash
            db.session.commit()
        return valid

    def is_password_expired(self):
        if not self.password_expires_at:
            return False
        return datetime.now(timezone.utc) > ensure_aware(self.password_expires_at)

    def generate_auth_token(self, expires_in=None, session_jti=None):
        if expires_in is None:
            expires_in = config.JWT_ACCESS_EXPIRY_MINUTES * 60
        now = datetime.now(timezone.utc)
        payload = {
            'user_id': str(self.id),
            'uuid': str(self.uuid),
            'email': str(self.email),
            'username': str(self.username),
            'role': str(self.role),
            'org_id': str(self.organization_id),
            'exp': int((now + timedelta(seconds=expires_in)).timestamp()),
            'iat': int(now.timestamp()),
            'nbf': int(now.timestamp()),
            'jti': str(uuid.uuid4()),
            'sid': str(session_jti) if session_jti else None,
            'iss': config.JWT_ISSUER,
            'aud': config.JWT_AUDIENCE,
            'type': 'access'
        }
        return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)

    def generate_refresh_token(self):
        jti = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        payload = {
            'user_id': str(self.id),
            'type': 'refresh',
            'exp': int((now + timedelta(days=config.JWT_REFRESH_EXPIRY_DAYS)).timestamp()),
            'iat': int(now.timestamp()),
            'jti': jti,
            'iss': config.JWT_ISSUER,
            'aud': config.JWT_AUDIENCE,
        }
        token = jwt.encode(payload, config.JWT_REFRESH_SECRET, algorithm=config.JWT_ALGORITHM)
        return token, jti

    def generate_mfa_backup_codes(self, count=10):
        codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]
        self.mfa_backup_codes = json.dumps(codes)
        return codes

    def add_login_history(self, ip, ua, success):
        try:
            h = self.login_history or []
            if not isinstance(h, list):
                h = []
            h.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'ip': ip, 'user_agent': ua, 'success': success
            })
            self.login_history = h[-50:]
        except Exception:
            pass

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'organization_id': self.organization_id,
            'username': self.username, 'email': self.email,
            'first_name': self.first_name, 'last_name': self.last_name,
            'display_name': self.display_name,
            'full_name': f"{self.first_name or ''} {self.last_name or ''}".strip(),
            'job_title': self.job_title, 'department': self.department, 'phone': self.phone,
            'avatar_url': (
              self.avatar_url if (self.avatar_url or '').startswith(('http://', 'https://'))
              else (f"{config.APP_URL.rstrip('/')}{self.avatar_url}" if self.avatar_url else None)
            ),
            'permissions': self.permissions or {}, 'plan': self.plan, 'status': self.status,
            'is_active': self.is_active, 'is_verified': self.is_verified,
            'is_locked': self.is_locked, 'is_mfa_enabled': self.is_mfa_enabled,
            'language': self.language, 'timezone': self.timezone,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'last_login_ip': self.last_login_ip,
            'login_count': self.login_count or 0,
            'login_history': self.login_history or [],
            'last_activity_at': self.last_activity_at.isoformat() if self.last_activity_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'notification_preferences': self.notification_preferences or {},
            'ui_preferences': self.ui_preferences or {},
            'user_metadata': self.user_metadata or {}
        })


class OAuthAccount(db.Model):
    __tablename__ = 'oauth_accounts'
    __table_args__ = (
        UniqueConstraint('provider', 'provider_subject', name='uq_oauth_provider_subject'),
    )

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    provider = db.Column(db.String(50), nullable=False)
    provider_subject = db.Column(db.String(255), nullable=False)
    provider_email = db.Column(db.String(255), nullable=True)
    provider_name = db.Column(db.String(200), nullable=True)
    provider_picture = db.Column(db.String(500), nullable=True)
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(DateTime(timezone=True), nullable=True)
    extra_data = db.Column(JSONType, nullable=True)
    created_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'provider': self.provider,
            'provider_email': self.provider_email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    __table_args__ = (
        Index('idx_session_user_jti', 'user_id', 'jti'),
        Index('idx_session_jti', 'jti'),
        Index('idx_session_expires', 'expires_at'),
    )

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    jti = db.Column(db.String(36), nullable=False, unique=True)
    token_hash = db.Column(db.String(255), nullable=True)
    device_id = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at = db.Column(DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(DateTime(timezone=True), nullable=True)
    last_activity_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def is_active(self):
        if self.revoked_at:
            return False
        exp = ensure_aware(self.expires_at)
        if exp is None:
            return True
        return datetime.now(timezone.utc) <= exp

    def to_dict(self):
        return json_safe({
            'id': self.id, 'device_id': self.device_id, 'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_activity_at': self.last_activity_at.isoformat() if self.last_activity_at else None,
            'is_active': self.is_active()
        })


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    __table_args__ = (
        Index('idx_audit_user_action', 'user_id', 'action'),
        Index('idx_audit_org_created', 'organization_id', 'created_at'),
        Index('idx_audit_created', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True
    )
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=True, index=True
    )
    action = db.Column(db.String(100), nullable=False, index=True)
    resource_type = db.Column(db.String(100), nullable=False)
    resource_id = db.Column(db.String(100), nullable=True)
    changes = db.Column(JSONType, default=dict)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    request_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='success')
    error_message = db.Column(db.Text, nullable=True)
    hash_chain = db.Column(db.String(255), nullable=True)
    previous_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'user_id': self.user_id, 'action': self.action,
            'resource_type': self.resource_type, 'resource_id': self.resource_id,
            'changes': self.changes or {}, 'ip_address': self.ip_address,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class Machine(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = 'machines'
    __table_args__ = (
        Index('idx_machine_org_status', 'organization_id', 'status'),
        Index('idx_machine_org_created', 'organization_id', 'created_at'),
    )

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False)
    machine_type = db.Column(db.String(100), nullable=False)
    manufacturer = db.Column(db.String(200), nullable=True)
    model = db.Column(db.String(200), nullable=True)
    serial_number = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(500), nullable=True)
    floor = db.Column(db.String(50), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), nullable=False, default='offline', index=True)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False, index=True)
    blocked_at = db.Column(DateTime(timezone=True), nullable=True)
    blocked_by = db.Column(UUIDType, nullable=True)
    health = db.Column(db.Integer, default=100, nullable=False)
    temperature = db.Column(db.Float, default=0)
    vibration = db.Column(db.Float, default=0)
    pressure = db.Column(db.Float, default=0)
    asset_id = db.Column(db.String(100), nullable=True)
    purchase_date = db.Column(DateTime(timezone=True), nullable=True)
    warranty_expiry = db.Column(DateTime(timezone=True), nullable=True)
    last_maintenance_at = db.Column(DateTime(timezone=True), nullable=True)
    next_maintenance_at = db.Column(DateTime(timezone=True), nullable=True)
    maintenance_interval_days = db.Column(db.Integer, default=30)
    notes = db.Column(db.Text, nullable=True)
    machine_data = db.Column(JSONType, default=dict)
    last_activity_at = db.Column(DateTime(timezone=True), nullable=True, index=True)
    owner_id = db.Column(UUIDType, db.ForeignKey('users.id'), nullable=True)
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )

    sensor_data = db.relationship(
        'SensorData', backref='machine', lazy='dynamic',
        cascade='all, delete-orphan'
    )
    predictions = db.relationship(
        'Prediction', backref='machine', lazy='dynamic',
        cascade='all, delete-orphan'
    )
    alerts = db.relationship(
        'Alert', backref='machine', lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'name': self.name,
            'type': self.machine_type, 'machine_type': self.machine_type,
            'manufacturer': self.manufacturer, 'model': self.model,
            'serial_number': self.serial_number, 'location': self.location,
            'floor': self.floor, 'department': self.department, 'status': self.status,
            'is_blocked': bool(getattr(self, 'is_blocked', False)),
            'blocked_at': self.blocked_at.isoformat() if self.blocked_at else None,
            'blocked_by': self.blocked_by,
            'health': self.health, 'temperature': self.temperature,
            'vibration': self.vibration, 'pressure': self.pressure,
            'asset_id': self.asset_id,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'warranty_expiry': self.warranty_expiry.isoformat() if self.warranty_expiry else None,
            'last_maintenance_at': self.last_maintenance_at.isoformat() if self.last_maintenance_at else None,
            'next_maintenance_at': self.next_maintenance_at.isoformat() if self.next_maintenance_at else None,
            'maintenance_interval_days': self.maintenance_interval_days,
            'notes': self.notes, 'machine_data': self.machine_data or {},
            'dataset_family': (self.machine_data or {}).get('dataset_family'),
            'last_activity_at': self.last_activity_at.isoformat() if self.last_activity_at else None,
            'owner_id': self.owner_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class MachineAPIKey(TimestampMixin, SoftDeleteMixin, db.Model):
    """Per-machine device API key (for hardware auth without user login)."""
    __tablename__ = 'machine_api_keys'
    __table_args__ = (
        Index('idx_machinekey_machine', 'machine_id'),
        Index('idx_machinekey_org', 'organization_id'),
    )

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    machine_id = db.Column(
        UUIDType, db.ForeignKey('machines.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False, default='Device key')
    key_hash = db.Column(db.String(255), nullable=False, unique=True, index=True)
    key_prefix = db.Column(db.String(20), nullable=False)
    last_used_at = db.Column(DateTime(timezone=True), nullable=True)
    usage_count = db.Column(db.Integer, default=0, nullable=False)
    revoked_at = db.Column(DateTime(timezone=True), nullable=True)

    def generate_key(self):
        key = f"spm_dev_{secrets.token_urlsafe(32)}"
        self.key_hash = hashlib.sha256(key.encode()).hexdigest()
        self.key_prefix = key[:12]
        return key

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'name': self.name,
            'machine_id': self.machine_id,
            'key_prefix': self.key_prefix,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'usage_count': self.usage_count,
            'revoked_at': self.revoked_at.isoformat() if self.revoked_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        })


class SensorData(TimestampMixin, db.Model):
    __tablename__ = 'sensor_data'
    __table_args__ = (
        Index('idx_sensor_machine_created', 'machine_id', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(
        UUIDType, db.ForeignKey('machines.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    temperature = db.Column(db.Float, nullable=True)
    vibration = db.Column(db.Float, nullable=True)
    pressure = db.Column(db.Float, nullable=True)
    readings = db.Column(JSONType, default=dict)
    is_anomaly = db.Column(db.Boolean, default=False, nullable=False, index=True)
    anomaly_score = db.Column(db.Float, nullable=True)
    anomaly_type = db.Column(db.String(50), nullable=True)
    source = db.Column(db.String(50), nullable=True)

    def to_dict(self):
        return json_safe({
            'id': self.id, 'machine_id': self.machine_id,
            'temperature': self.temperature, 'vibration': self.vibration,
            'pressure': self.pressure, 'readings': self.readings or {},
            'is_anomaly': self.is_anomaly, 'anomaly_score': self.anomaly_score,
            'anomaly_type': self.anomaly_type, 'source': self.source,
            'timestamp': self.created_at.isoformat() if self.created_at else None
        })


class Prediction(TimestampMixin, db.Model):
    """Prediction persisted after a successful inference.

    `risk_score`, `rul_hours`, `confidence`, and `processing_time_ms` are
    SQLAlchemy Float columns; confidence is nullable because calibrated confidence
    is not guaranteed by every production model bundle and therefore map to DOUBLE PRECISION on
    PostgreSQL. Older databases may still contain NUMERIC(5,4);
    auto_patch_schema() migrates the legacy risk_score column at startup.
    """
    __tablename__ = 'predictions'
    __table_args__ = (
        Index('idx_pred_machine_created', 'machine_id', 'created_at'),
        Index('idx_pred_status', 'status'),
        Index('idx_pred_source', 'source'),
        Index('idx_pred_user', 'user_id'),
        UniqueConstraint('organization_id', 'request_id', name='uq_pred_org_request'),
    )

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    request_id = db.Column(db.String(64), nullable=False, index=True)
    schema_version = db.Column(db.String(20), nullable=False, default='1.0')
    feature_provenance = db.Column(JSONType, nullable=True)
    ood_flags = db.Column(JSONType, default=list)
    sensor_quality = db.Column(db.Float, nullable=True)
    prediction_trust = db.Column(db.String(20), nullable=True)
    uncertainty_lower = db.Column(db.Float, nullable=True)
    uncertainty_upper = db.Column(db.Float, nullable=True)
    model_selection_audit = db.Column(JSONType, nullable=True)
    source = db.Column(db.String(50), nullable=True)
    source_filename = db.Column(db.String(255), nullable=True)
    user_id = db.Column(UUIDType, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    machine_id = db.Column(
        UUIDType, db.ForeignKey('machines.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )
    rul_hours = db.Column(db.Float, nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='healthy', index=True)
    model_type = db.Column(db.String(50), nullable=False, default='lstm')
    model_version = db.Column(db.String(50), nullable=True)
    risk_level = db.Column(db.String(50), nullable=True)
    risk_score = db.Column(db.Float, nullable=True)
    feature_importance = db.Column(JSONType, nullable=True)
    recommendations = db.Column(JSONType, default=list)
    data_window = db.Column(db.Integer, nullable=True)
    data_points = db.Column(db.Integer, nullable=True)
    processing_time_ms = db.Column(db.Float, nullable=True)
    model_input = db.Column(JSONType, nullable=True)
    model_output = db.Column(JSONType, nullable=True)
    prediction_data = db.Column(JSONType, default=dict)

    def to_dict(self, include_audit=False):
        payload = {
            'id': self.id, 'uuid': self.uuid, 'request_id': self.request_id,
            'schema_version': self.schema_version, 'machine_id': self.machine_id,
            'organization_id': self.organization_id, 'user_id': self.user_id,
            'source': self.source, 'source_filename': self.source_filename,
            'machine_name': ('Dataset prediction' if self.machine and self.machine.name == '__dataset__' else (self.machine.name if self.machine else None)),
            'rul_hours': self.rul_hours, 'confidence': self.confidence,
            'status': self.status, 'model_type': self.model_type,
            'model_id': (self.model_output or {}).get('model_id') if isinstance(self.model_output, dict) else None,
            'model_version': self.model_version,
            'risk_level': ('critical' if str(self.risk_level or '').lower() == 'high' else ('warning' if str(self.risk_level or '').lower() == 'medium' else self.risk_level)),
            'risk_score': self.risk_score,
            'feature_provenance': self.feature_provenance or {},
            'ood_flags': self.ood_flags or [], 'sensor_quality': self.sensor_quality,
            'prediction_trust': self.prediction_trust,
            'uncertainty_lower': self.uncertainty_lower, 'uncertainty_upper': self.uncertainty_upper,
            'recommendations': self.recommendations or [],
            'data_window': self.data_window, 'data_points': self.data_points,
            'processing_time_ms': self.processing_time_ms,
            'prediction_data': self.prediction_data or {},
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_audit:
            payload['model_selection_audit'] = self.model_selection_audit or {}
        return json_safe(payload)


class Alert(TimestampMixin, db.Model):
    __tablename__ = 'alerts'
    __table_args__ = (
        Index('idx_alert_machine_status', 'machine_id', 'status'),
        Index('idx_alert_severity_created', 'severity', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    machine_id = db.Column(
        UUIDType, db.ForeignKey('machines.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    # Tenant boundary: alerts are organization-scoped just like machines,
    # predictions and notifications. Older app versions omitted this ORM
    # field even though the production PostgreSQL table already required it.
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(50), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)
    source = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), nullable=False, default='active', index=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    acknowledged_at = db.Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    resolved_at = db.Column(DateTime(timezone=True), nullable=True)
    resolved_by = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )
    resolution_notes = db.Column(db.Text, nullable=True)
    escalation_level = db.Column(db.Integer, default=0)
    escalated_at = db.Column(DateTime(timezone=True), nullable=True)
    prediction_id = db.Column(db.Integer, db.ForeignKey('predictions.id'), nullable=True)
    incident_id = db.Column(db.String(100), nullable=True)
    email_status = db.Column(JSONType, nullable=True)

    def to_dict(self):
        try:
            _machine = db.session.get(Machine, self.machine_id) if self.machine_id else None
            _machine_name = _machine.name if _machine else None
        except Exception:
            _machine_name = None
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'machine_id': self.machine_id,
            'machine_name': _machine_name,
            'organization_id': self.organization_id,
            'title': self.title, 'message': self.message, 'severity': self.severity,
            'category': self.category, 'source': self.source, 'status': self.status,
            'is_read': self.is_read,
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution_notes': self.resolution_notes,
            'escalation_level': self.escalation_level, 'incident_id': self.incident_id,
            'email_status': self.email_status or {},
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class Notification(TimestampMixin, db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    alert_id = db.Column(db.Integer, db.ForeignKey('alerts.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    is_sent = db.Column(db.Boolean, default=False, nullable=False)
    sent_at = db.Column(DateTime(timezone=True), nullable=True)
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'user_id': self.user_id,
            'title': self.title, 'message': self.message, 'type': self.type,
            'is_read': self.is_read, 'is_sent': self.is_sent,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class Payment(TimestampMixin, db.Model):
    __tablename__ = 'payments'

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )
    gateway = db.Column(db.String(50), nullable=False)
    gateway_payment_id = db.Column(db.String(200), nullable=True)
    gateway_order_id = db.Column(db.String(200), nullable=True, index=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='USD')
    plan_id = db.Column(db.String(50), nullable=False)
    plan_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='pending', index=True)
    customer_email = db.Column(db.String(255), nullable=True)
    customer_name = db.Column(db.String(200), nullable=True)
    invoice_number = db.Column(db.String(100), nullable=True)
    webhook_data = db.Column(JSONType, nullable=True)
    webhook_received_at = db.Column(DateTime(timezone=True), nullable=True)
    payment_data = db.Column(JSONType, nullable=True)

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'organization_id': self.organization_id,
            'gateway': self.gateway, 'gateway_payment_id': self.gateway_payment_id,
            'gateway_order_id': self.gateway_order_id,
            'amount': self.amount, 'currency': self.currency,
            'plan_id': self.plan_id, 'plan_name': self.plan_name,
            'status': self.status, 'customer_email': self.customer_email,
            'customer_name': self.customer_name,
            'invoice_number': self.invoice_number,
            'payment_data': self.payment_data or {},
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class PaymentIdempotency(db.Model):
    __tablename__ = 'payment_idempotency'
    key = db.Column(db.String(160), primary_key=True)
    user_id = db.Column(UUIDType, nullable=False, index=True)
    request_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='processing')
    response_payload = db.Column(JSONType, nullable=True)
    status_code = db.Column(db.Integer, nullable=True)
    created_at = db.Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class WebhookEvent(db.Model):
    __tablename__ = 'webhook_events'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(200), nullable=False, unique=True, index=True)
    gateway = db.Column(db.String(50), nullable=False)
    received_at = db.Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True
    )
    payload = db.Column(JSONType, nullable=True)


class APIKey(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = 'api_keys'

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False)
    key_hash = db.Column(db.String(255), nullable=False, unique=True, index=True)
    key_prefix = db.Column(db.String(20), nullable=False)
    permissions = db.Column(JSONType, default=list)
    rate_limit = db.Column(db.Integer, default=100)
    last_used_at = db.Column(DateTime(timezone=True), nullable=True)
    usage_count = db.Column(db.Integer, default=0, nullable=False)
    expires_at = db.Column(DateTime(timezone=True), nullable=True)
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )

    def generate_key(self):
        key = f"spm_{secrets.token_urlsafe(32)}"
        self.key_hash = hashlib.sha256(key.encode()).hexdigest()
        self.key_prefix = key[:8]
        return key

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'name': self.name,
            'key_prefix': self.key_prefix, 'permissions': self.permissions or [],
            'rate_limit': self.rate_limit,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'usage_count': self.usage_count,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class Report(TimestampMixin, db.Model):
    __tablename__ = 'reports'

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    format = db.Column(db.String(20), nullable=False, default='pdf')
    parameters = db.Column(JSONType, nullable=True)
    file_path = db.Column(db.String(500), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), default='generating')
    generated_at = db.Column(DateTime(timezone=True), nullable=True)
    download_count = db.Column(db.Integer, default=0)
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'user_id': self.user_id,
            'name': self.name, 'type': self.type, 'format': self.format,
            'parameters': self.parameters or {}, 'file_path': self.file_path,
            'file_size': self.file_size, 'status': self.status,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'download_count': self.download_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class Download(TimestampMixin, db.Model):
    __tablename__ = 'downloads'

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    version = db.Column(db.String(50), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=True)
    checksum = db.Column(db.String(100), nullable=True)
    download_count = db.Column(db.Integer, default=0)
    platform = db.Column(db.String(50), nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    metadata_json = db.Column('metadata', JSONType, nullable=True)
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False, index=True
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid, 'user_id': self.user_id,
            'name': self.name, 'type': self.type, 'version': self.version,
            'file_path': self.file_path, 'file_size': self.file_size,
            'download_count': self.download_count, 'platform': self.platform,
            'metadata': self.metadata_json or {},
            'organization_id': self.organization_id, 'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


class CareerSubmission(TimestampMixin, db.Model):
    __tablename__ = 'career_submissions'

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=True, index=True
    )
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    position = db.Column(db.String(100), nullable=False)
    experience = db.Column(db.Text, nullable=True)
    cover_letter = db.Column(db.Text, nullable=True)
    resume_path = db.Column(db.String(500), nullable=True)
    resume_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), default='pending', nullable=False, index=True)
    review_notes = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(DateTime(timezone=True), nullable=True)
    reviewed_by = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid,
            'organization_id': self.organization_id,
            'full_name': self.full_name, 'email': self.email,
            'phone': self.phone, 'position': self.position,
            'experience': self.experience, 'cover_letter': self.cover_letter,
            'resume_path': self.resume_path,
            'resume_filename': self.resume_filename,
            'status': self.status, 'review_notes': self.review_notes,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'reviewed_by': self.reviewed_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        })


class ContactSubmission(TimestampMixin, db.Model):
    __tablename__ = 'contact_submissions'

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=True, index=True
    )
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='pending', nullable=False, index=True)
    response = db.Column(db.Text, nullable=True)
    responded_at = db.Column(DateTime(timezone=True), nullable=True)
    responded_by = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True
    )

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid,
            'organization_id': self.organization_id,
            'full_name': self.full_name, 'email': self.email,
            'phone': self.phone, 'subject': self.subject,
            'message': self.message, 'status': self.status,
            'response': self.response,
            'responded_at': self.responded_at.isoformat() if self.responded_at else None,
            'responded_by': self.responded_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        })


class EnterpriseRequest(TimestampMixin, db.Model):
    __tablename__ = 'enterprise_requests'

    id = db.Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    uuid = db.Column(UUIDType, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(
        UUIDType, db.ForeignKey('organizations.id', ondelete='SET NULL'),
        nullable=True, index=True
    )
    user_id = db.Column(
        UUIDType, db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True, index=True
    )
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    machines = db.Column(db.String(50), nullable=True)
    requirements = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='pending', nullable=False, index=True)
    admin_notes = db.Column(db.Text, nullable=True)
    contacted_at = db.Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return json_safe({
            'id': self.id, 'uuid': self.uuid,
            'organization_id': self.organization_id, 'user_id': self.user_id,
            'full_name': self.full_name, 'email': self.email,
            'company': self.company, 'phone': self.phone,
            'machines': self.machines, 'requirements': self.requirements,
            'status': self.status, 'admin_notes': self.admin_notes,
            'contacted_at': self.contacted_at.isoformat() if self.contacted_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        })


# ============================================================
# SCHEMA AUTO-PATCH
# ============================================================

def auto_patch_schema():
    """Idempotent schema fixer — runs on every startup."""
    if not config.SCHEMA_AUTO_PATCH:
        return
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    # ---- Launch hardening columns: machine block metadata + download metadata ----
    try:
        dialect = db.engine.dialect.name
        with db.engine.begin() as conn:
            tables_now = set(inspect(db.engine).get_table_names())
            if 'machines' in tables_now:
                cols = {c['name'] for c in inspect(db.engine).get_columns('machines')}
                if 'is_blocked' not in cols:
                    conn.execute(text("ALTER TABLE machines ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT FALSE" if dialect == 'postgresql' else "ALTER TABLE machines ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT 0"))
                if 'blocked_at' not in cols:
                    conn.execute(text("ALTER TABLE machines ADD COLUMN blocked_at TIMESTAMP WITH TIME ZONE" if dialect == 'postgresql' else "ALTER TABLE machines ADD COLUMN blocked_at DATETIME"))
                if 'blocked_by' not in cols:
                    conn.execute(text("ALTER TABLE machines ADD COLUMN blocked_by UUID" if dialect == 'postgresql' else "ALTER TABLE machines ADD COLUMN blocked_by VARCHAR(36)"))
            if 'downloads' in tables_now:
                cols = {c['name'] for c in inspect(db.engine).get_columns('downloads')}
                if 'metadata' not in cols:
                    conn.execute(text("ALTER TABLE downloads ADD COLUMN metadata JSONB" if dialect == 'postgresql' else "ALTER TABLE downloads ADD COLUMN metadata JSON"))
        logger.info('Launch schema patch checked machine block and download metadata columns')
    except Exception:
        logger.exception('Launch schema patch failed for machine/download columns')

    # ---- Prediction provenance/idempotency schema migration -----------------
    try:
        if 'predictions' in set(inspect(db.engine).get_table_names()):
            dialect = db.engine.dialect.name
            cols = {c['name'] for c in inspect(db.engine).get_columns('predictions')}
            with db.engine.begin() as conn:
                if 'source' not in cols:
                    conn.execute(text('ALTER TABLE predictions ADD COLUMN source VARCHAR(50)'))
                if 'source_filename' not in cols:
                    conn.execute(text('ALTER TABLE predictions ADD COLUMN source_filename VARCHAR(255)'))
                if 'user_id' not in cols:
                    user_type = 'UUID' if dialect == 'postgresql' else 'VARCHAR(36)'
                    conn.execute(text(f'ALTER TABLE predictions ADD COLUMN user_id {user_type}'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS idx_pred_source ON predictions (source)'))
                conn.execute(text('CREATE INDEX IF NOT EXISTS idx_pred_user ON predictions (user_id)'))
                # Only create the unique index if legacy data has no duplicate request IDs.
                duplicates = conn.execute(text('SELECT 1 FROM predictions GROUP BY organization_id, request_id HAVING COUNT(*) > 1 LIMIT 1')).first()
                if not duplicates:
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_pred_org_request ON predictions (organization_id, request_id)'))
                else:
                    logger.warning('Legacy duplicate prediction request IDs found; unique index skipped until duplicates are reconciled.')
        logger.info('Prediction provenance/idempotency schema patch checked')
    except Exception:
        logger.exception('Prediction provenance/idempotency schema patch failed')

    # ---- FIX: convert Postgres native ENUM prediction_model_type → VARCHAR ----
    # Legacy enum compatibility only; current ML inference never emits a heuristic result and the enum
    # wouldn't accept that string, causing every prediction to 500.
    try:
        if db.engine.dialect.name == 'postgresql' and 'predictions' in existing_tables:
            with db.engine.begin() as conn:
                r = conn.execute(text("""
                    SELECT data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'predictions' AND column_name = 'model_type'
                """)).fetchone()
                if r and r[0] == 'USER-DEFINED':
                    logger.warning(
                        "predictions.model_type is a native ENUM — converting to VARCHAR(50)"
                    )
                    conn.execute(text(
                        "ALTER TABLE predictions ALTER COLUMN model_type TYPE VARCHAR(50) "
                        "USING model_type::text"
                    ))
                    conn.execute(text("DROP TYPE IF EXISTS prediction_model_type CASCADE"))
                    logger.info("✅ predictions.model_type converted to VARCHAR(50)")
    except Exception as e:
        logger.warning(f"prediction_model_type enum conversion skipped: {e}")

    # ---- FIX: legacy PostgreSQL alerts.severity ENUM -----------------------
    # Older SynapsePM databases created alerts.severity as the native
    # PostgreSQL enum `alert_severity`. The current application deliberately
    # uses VARCHAR because it has to support the complete alert vocabulary
    # used by the ML and sensor alert paths. If the old enum is left in place,
    # a real high-RUL prediction succeeds but the follow-up alert INSERT fails
    # on `warning`, which then poisons the SQLAlchemy session and turns a valid
    # prediction into HTTP 503.
    try:
        if db.engine.dialect.name == 'postgresql' and 'alerts' in existing_tables:
            with db.engine.begin() as conn:
                r = conn.execute(text("""
                    SELECT data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'alerts'
                      AND column_name = 'severity'
                """)).fetchone()
                if r and r[0] == 'USER-DEFINED' and str(r[1]) == 'alert_severity':
                    logger.warning(
                        "alerts.severity is legacy PostgreSQL ENUM alert_severity — converting to VARCHAR(50)"
                    )
                    conn.execute(text(
                        "ALTER TABLE alerts ALTER COLUMN severity TYPE VARCHAR(50) "
                        "USING severity::text"
                    ))
                    # Keep the now-unused PostgreSQL type. Dropping it is not
                    # necessary for correctness and can fail if an older object
                    # still references it; the column itself is what matters.
                    logger.info("✅ alerts.severity converted to VARCHAR(50)")
    except Exception as e:
        logger.exception("Could not patch alerts.severity enum: %s", e)

    # ---- FIX: alerts.organization_id tenant column -----------------------
    # The production DB can contain this NOT NULL column even when an older
    # ORM model did not declare it. Ensure new installations and upgraded
    # installations both have the same tenant boundary.
    try:
        if db.engine.dialect.name == 'postgresql' and 'alerts' in existing_tables:
            with db.engine.begin() as conn:
                r = conn.execute(text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='alerts'
                      AND column_name='organization_id'
                """)).fetchone()
                if not r:
                    logger.warning('alerts.organization_id is missing — adding tenant column')
                    conn.execute(text("ALTER TABLE alerts ADD COLUMN organization_id UUID"))
                    conn.execute(text("""
                        UPDATE alerts a
                        SET organization_id = m.organization_id
                        FROM machines m
                        WHERE a.machine_id = m.id
                          AND a.organization_id IS NULL
                    """))
                    missing = conn.execute(text("SELECT COUNT(*) FROM alerts WHERE organization_id IS NULL")).scalar()
                    if int(missing or 0) > 0:
                        raise RuntimeError(f'Cannot enforce alerts.organization_id: {missing} existing rows cannot be mapped to a machine organization')
                    conn.execute(text("ALTER TABLE alerts ALTER COLUMN organization_id SET NOT NULL"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_alert_org_status ON alerts (organization_id, status)"))
                    logger.info('✅ alerts.organization_id added and backfilled')
    except Exception as e:
        logger.exception('Could not patch alerts.organization_id: %s', e)

    # ---- FIX: prediction confidence must be nullable ----------------------
    # A real model may provide RUL without a calibrated confidence value.
    # v31 correctly stopped inventing confidence=0, but the deployed database
    # still had predictions.confidence NOT NULL. That made persistence fail
    # after successful inference. Make the column nullable so missing
    # confidence is represented honestly as NULL.
    try:
        if db.engine.dialect.name == 'postgresql' and 'predictions' in existing_tables:
            with db.engine.begin() as conn:
                r = conn.execute(text("""
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'predictions'
                      AND column_name = 'confidence'
                """)).fetchone()
                if r and str(r[0]).upper() == 'NO':
                    logger.warning(
                        "predictions.confidence is NOT NULL but model confidence is optional — making it nullable"
                    )
                    conn.execute(text(
                        "ALTER TABLE predictions ALTER COLUMN confidence DROP NOT NULL"
                    ))
                    logger.info("✅ predictions.confidence is now nullable")
    except Exception as e:
        logger.exception("Could not patch predictions.confidence nullability: %s", e)

    # ---- FIX: predictions.risk_score was NUMERIC(5,4) in older DBs ----
    # The heuristic/model risk score can legitimately be greater than 9.9999.
    # Convert legacy PostgreSQL NUMERIC columns to DOUBLE PRECISION so inserts
    # cannot fail with NumericValueOutOfRange after inference succeeds.
    try:
        if db.engine.dialect.name == 'postgresql' and 'predictions' in existing_tables:
            with db.engine.begin() as conn:
                r = conn.execute(text("""
                    SELECT data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_name = 'predictions' AND column_name = 'risk_score'
                """)).fetchone()
                if r and r[0] == 'numeric' and r[1] is not None:
                    logger.warning(
                        f"predictions.risk_score is NUMERIC({r[1]},{r[2]}) — converting to DOUBLE PRECISION"
                    )
                    conn.execute(text(
                        "ALTER TABLE predictions ALTER COLUMN risk_score TYPE DOUBLE PRECISION "
                        "USING risk_score::double precision"
                    ))
                    logger.info("✅ predictions.risk_score converted to DOUBLE PRECISION")
    except Exception as e:
        logger.warning(f"risk_score conversion skipped: {e}")

    # Diagnostic: list legacy NUMERIC columns. This is intentionally logged
    # rather than mutated automatically because money/storage fields often
    # require fixed precision and must not be changed blindly.
    try:
        if db.engine.dialect.name == 'postgresql':
            with db.engine.begin() as conn:
                rows = conn.execute(text("""
                    SELECT table_name, column_name, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND data_type = 'numeric'
                    ORDER BY table_name, column_name
                """)).fetchall()
                for row in rows:
                    logger.info(
                        f"NUMERIC column: {row[0]}.{row[1]} = NUMERIC({row[2]},{row[3]})"
                    )
    except Exception:
        pass

    # ---- FIX: predictions.organization_id existed in some deployed databases
    # but was missing from the SQLAlchemy model, so INSERTs omitted it and
    # PostgreSQL rejected the row with NOT NULL violation.
    if 'predictions' in existing_tables:
        try:
            prediction_cols = {c['name'] for c in inspect(db.engine).get_columns('predictions')}
            if 'organization_id' not in prediction_cols and 'organizations' in existing_tables:
                with db.engine.begin() as conn:
                    org_db_type = 'UUID' if db.engine.dialect.name == 'postgresql' else 'VARCHAR(36)'
                    conn.execute(text(
                        f"ALTER TABLE predictions ADD COLUMN organization_id {org_db_type}"
                    ))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS idx_predictions_org ON predictions (organization_id)"
                    ))
                logger.info('✅ Patched predictions.organization_id column')
        except Exception as e:
            logger.warning(f'Could not patch predictions.organization_id: {e}')

    # ---- v25 prediction contract/idempotency columns ----
    if 'predictions' in existing_tables:
        try:
            cols = {c['name'] for c in inspect(db.engine).get_columns('predictions')}
            patches = [
                ('request_id', 'VARCHAR(64)'),
                ('schema_version', "VARCHAR(20) DEFAULT '1.0'"),
                ('feature_provenance', 'TEXT'),
                ('ood_flags', 'TEXT'),
                ('sensor_quality', 'DOUBLE PRECISION'),
                ('prediction_trust', 'VARCHAR(20)'),
                ('uncertainty_lower', 'DOUBLE PRECISION'),
                ('uncertainty_upper', 'DOUBLE PRECISION'),
                ('model_selection_audit', 'TEXT'),
            ]
            for col, typ in patches:
                if col not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE predictions ADD COLUMN {col} {typ}'))
                    logger.info('Patched predictions.%s', col)
            # Backfill before making request_id NOT NULL.
            with db.engine.begin() as conn:
                conn.execute(text(
                    "UPDATE predictions SET request_id = COALESCE(request_id, uuid::text)"
                    if db.engine.dialect.name == 'postgresql'
                    else "UPDATE predictions SET request_id = COALESCE(request_id, uuid)"
                ))
                if db.engine.dialect.name == 'postgresql':
                    conn.execute(text(
                        "ALTER TABLE predictions ALTER COLUMN request_id SET NOT NULL"
                    ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_predictions_org_request "
                    "ON predictions (organization_id, request_id)"
                ))
        except Exception as e:
            logger.warning('Could not patch v25 prediction contract: %s', e)

    if 'users' in existing_tables:
        user_cols = {c['name'] for c in inspector.get_columns('users')}
        user_patches = [
            ('reset_locked_until', 'TIMESTAMP WITH TIME ZONE'),
            ('reset_otp_attempts', 'INTEGER DEFAULT 0'),
            ('phone', 'VARCHAR(100)'),
            ('mfa_secret', 'VARCHAR(100)'),
            ('mfa_backup_codes', 'VARCHAR(500)'),
            ('last_activity_at', 'TIMESTAMP WITH TIME ZONE'),
            ('deactivated_at', 'TIMESTAMP WITH TIME ZONE'),
        ]
        for col, coltype in user_patches:
            if col not in user_cols:
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE users ADD COLUMN {col} {coltype}'))
                    logger.info(f"✅ Patched users.{col}")
                except Exception as e:
                    logger.warning(f"Could not add users.{col}: {e}")

    if 'organizations' in existing_tables:
        org_cols = {c['name'] for c in inspector.get_columns('organizations')}
        org_patches = [
            ('trial_reminder_sent', 'BOOLEAN DEFAULT FALSE'),
            ('trial_expired_notified', 'BOOLEAN DEFAULT FALSE'),
            ('billing_email', 'VARCHAR(255)'),
            ('billing_address', 'TEXT'),
            ('white_label', 'TEXT'),
            ('custom_domain', 'VARCHAR(200)'),
        ]
        for col, coltype in org_patches:
            if col not in org_cols:
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text(f'ALTER TABLE organizations ADD COLUMN {col} {coltype}'))
                    logger.info(f"✅ Patched organizations.{col}")
                except Exception as e:
                    logger.warning(f"Could not add organizations.{col}: {e}")

    if 'machines' in existing_tables:
        machine_cols = {c['name'] for c in inspector.get_columns('machines')}
        if 'last_activity_at' not in machine_cols:
            try:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE machines ADD COLUMN last_activity_at TIMESTAMP WITH TIME ZONE'))
                logger.info('Patched machines.last_activity_at')
            except Exception as e:
                logger.warning(f'Could not add machines.last_activity_at: {e}')

    if 'alerts' in existing_tables:
        alert_cols = {c['name'] for c in inspector.get_columns('alerts')}
        if 'email_status' not in alert_cols:
            try:
                with db.engine.begin() as conn:
                    conn.execute(text('ALTER TABLE alerts ADD COLUMN email_status TEXT'))
                logger.info("✅ Patched alerts.email_status")
            except Exception as e:
                logger.warning(f"Could not add alerts.email_status: {e}")

    for table_name, model in [
        ('webhook_events', WebhookEvent),
        ('career_submissions', CareerSubmission),
        ('contact_submissions', ContactSubmission),
        ('enterprise_requests', EnterpriseRequest),
        ('machine_api_keys', MachineAPIKey),
    ]:
        if table_name not in existing_tables:
            try:
                model.__table__.create(db.engine, checkfirst=True)
                logger.info(f"✅ Created {table_name} table")
            except Exception as e:
                logger.warning(f"Could not create {table_name}: {e}")


# ============================================================
# JWT BLACKLIST + SESSION MANAGER
# ============================================================

class JWTBlacklist:
    def __init__(self, r):
        self.redis = r

    def add(self, jti, expiry):
        if self.redis:
            try:
                self.redis.setex(f"blacklist:{jti}", expiry, "1")
                return True
            except Exception:
                pass
        return False

    def check(self, jti):
        if self.redis:
            try:
                return self.redis.exists(f"blacklist:{jti}") == 1
            except Exception:
                pass
        return False

    def revoke_all_user_tokens(self, uid):
        if self.redis:
            try:
                revoked_at = int(datetime.now(timezone.utc).timestamp())
                self.redis.setex(
                    f"user_revoked:{uid}",
                    config.JWT_REFRESH_EXPIRY_DAYS * 86400,
                    str(revoked_at)
                )
                return True
            except Exception:
                logger.exception("Failed to store all-session revocation timestamp")
        return False


jwt_blacklist = JWTBlacklist(redis_client)


class SessionManager:
    def __init__(self):
        self.redis = redis_client

    def _key(self, jti):
        return f"session:{jti}"

    def create_session(self, user, ip, ua, device_id=None, jti=None, token_hash=None):
        jti = jti or str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_EXPIRY_DAYS)
        s = UserSession(
            user_id=user.id, organization_id=user.organization_id, jti=jti,
            token_hash=token_hash,
            device_id=device_id or f"device_{secrets.token_hex(8)}",
            ip_address=ip,
            user_agent=ua[:500] if ua else None,
            expires_at=expires_at
        )
        db.session.add(s)
        db.session.commit()
        if self.redis:
            try:
                self.redis.setex(
                    self._key(jti), config.SESSION_CACHE_TTL,
                    json.dumps({'active': True, 'expires': expires_at.isoformat()})
                )
            except Exception:
                pass
        return s

    def revoke_session(self, jti):
        s = UserSession.query.filter_by(jti=jti).first()
        if s:
            s.revoked_at = datetime.now(timezone.utc)
            db.session.commit()
        jwt_blacklist.add(jti, config.JWT_REFRESH_EXPIRY_DAYS * 86400)
        if self.redis:
            try:
                self.redis.delete(self._key(jti))
            except Exception:
                pass
        return bool(s)

    def revoke_all_sessions(self, user_id):
        ss = UserSession.query.filter_by(user_id=user_id, revoked_at=None).all()
        for s in ss:
            s.revoked_at = datetime.now(timezone.utc)
            jwt_blacklist.add(s.jti, config.JWT_REFRESH_EXPIRY_DAYS * 86400)
            if self.redis:
                try:
                    self.redis.delete(self._key(s.jti))
                except Exception:
                    pass
        db.session.commit()
        return len(ss)

    def get_active_sessions(self, user_id):
        ss = UserSession.query.filter_by(user_id=user_id, revoked_at=None).all()
        now = datetime.now(timezone.utc)
        return [s for s in ss
                if ensure_aware(s.expires_at) and ensure_aware(s.expires_at) > now]

    def check_session(self, jti):
        if not jti:
            return False
        if jwt_blacklist.check(jti):
            return False
        s = UserSession.query.filter_by(jti=jti).first()
        if not s:
            logger.warning('Session JTI %s not found in DB — rejecting token.', jti)
            return False
        return bool(s.is_active())


session_manager = SessionManager()


# ============================================================
# HELPERS
# ============================================================

def _uuid_or_404(value, field='id'):
    """Validate UUID path parameters before SQLAlchemy/Postgres sees them."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        from werkzeug.exceptions import NotFound
        raise NotFound(description=f'Invalid {field}. Expected a UUID.')


def _prediction_status(rul_hours):
    """Database/UI status: stable semantic health state."""
    try:
        rul = float(rul_hours)
    except (TypeError, ValueError):
        return 'warning'
    if rul < 24:
        return 'critical'
    if rul < 72:
        return 'warning'
    return 'healthy'


def normalize_email(v):
    return str(v or "").strip().lower()


def normalize_name(v):
    return str(v or "").strip()


def make_unique_org_slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "organization"
    base = base[:80].rstrip("-")
    slug = base
    c = 1
    while Organization.query.filter_by(slug=slug).first():
        c += 1
        slug = f"{base}-{c}"
    return slug


def generate_otp(length=6):
    return ''.join([str(secrets.randbelow(10)) for _ in range(length)])


def hash_otp(otp):
    return hashlib.sha256(otp.encode()).hexdigest()


def validate_image_upload(file):
    if not PIL_AVAILABLE:
        return True
    try:
        file.stream.seek(0)
        img = Image.open(file.stream)
        img.verify()
        file.stream.seek(0)
        return True
    except Exception:
        try:
            file.stream.seek(0)
        except Exception:
            pass
        return False


def secure_filename_enhanced(filename):
    name, ext = os.path.splitext(filename)
    ext = ext.lower() if ext else ''
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    rnd = secrets.token_hex(4)
    safe = secure_filename(name) or "file"
    return f"{safe}_{ts}_{rnd}{ext}"


def generate_invoice_number():
    y = datetime.now(timezone.utc).strftime("%Y")
    m = datetime.now(timezone.utc).strftime("%m")
    return f"INV-{y}{m}-{secrets.token_hex(4).upper()}"


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def get_frontend_folder():
    for p in [config.FRONTEND_FOLDER,
              os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend'),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Frontend')]:
        if os.path.isdir(p):
            return p
    return config.FRONTEND_FOLDER


def paginate(query, page=1, per_page=20):
    per_page = min(per_page, config.MAX_PAGE_SIZE)
    p = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [i.to_dict() for i in p.items],
        'total': p.total, 'page': p.page, 'per_page': p.per_page,
        'pages': p.pages, 'has_next': p.has_next, 'has_prev': p.has_prev
    }


def log_audit(action, rtype, rid=None, changes=None, status='success', user_id=None,
              broadcast=True):
    if action in ('register', 'login', 'logout'):
        return None
    try:
        prev = None
        try:
            last = db.session.query(AuditLog).order_by(AuditLog.created_at.desc()).first()
            if last:
                prev = last.hash_chain
        except Exception:
            db.session.rollback()
        hd = f"{action}{rtype}{rid}{datetime.now(timezone.utc).isoformat()}{prev}"
        hc = hashlib.sha256(hd.encode()).hexdigest()
        a = AuditLog(
            user_id=user_id or getattr(g, 'user_id', None),
            organization_id=getattr(getattr(g, 'organization', None), 'id', None) or getattr(g, 'organization_id', None),
            action=action, resource_type=rtype,
            resource_id=str(rid) if rid else None,
            changes=changes or {},
            ip_address=request.remote_addr if hasattr(request, 'remote_addr') else None,
            user_agent=request.headers.get('User-Agent') if hasattr(request, 'headers') else None,
            status=status, previous_hash=prev, hash_chain=hc
        )
        db.session.add(a)
        db.session.commit()
        if broadcast:
            try:
                ad = a.to_dict()
                publish_admin_event('activity_created', {'activity': ad})
                org_id = getattr(getattr(g, 'organization', None), 'id', None) or getattr(g, 'organization_id', None)
                if org_id:
                    publish_user_event(org_id, 'activity_created', {'activity': ad})
            except Exception:
                pass
        return a
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


# ============================================================
# EMAIL HELPERS
# ============================================================

import threading
import requests as _requests

# Sender identity per purpose. All must be on your verified sending domain.
EMAIL_SENDERS = {
    "verification": os.environ.get("MAIL_FROM_VERIFY", "SynapsePM <verify@synapsepm.us.ci>"),
    "security":     os.environ.get("MAIL_FROM_SECURITY", "SynapsePM <security@synapsepm.us.ci>"),
    "billing":      os.environ.get("MAIL_FROM_BILLING", "SynapsePM <billing@synapsepm.us.ci>"),
    "alerts":       os.environ.get("MAIL_FROM_ALERTS", "SynapsePM <alerts@synapsepm.us.ci>"),
    "support":      os.environ.get("MAIL_FROM_SUPPORT", "SynapsePM <support@synapsepm.us.ci>"),
}

def _pick_sender(subject: str, default_purpose: str = "support") -> str:
    """Route an email to the right sender by subject keyword."""
    s = (subject or "").lower()
    if any(k in s for k in ("verify", "verification", "confirm your email")):
        return EMAIL_SENDERS["verification"]
    if any(k in s for k in ("password", "reset", "otp", "security")):
        return EMAIL_SENDERS["security"]
    if any(k in s for k in ("invoice", "payment", "billing", "subscription", "receipt")):
        return EMAIL_SENDERS["billing"]
    if any(k in s for k in ("alert", "critical", "rul", "anomaly")):
        return EMAIL_SENDERS["alerts"]
    return EMAIL_SENDERS.get(default_purpose, EMAIL_SENDERS["support"])

def send_email(to, subject, html, text=None):
    """Send via Send.dev API."""
    def _send():
        try:
            # We renamed the key to SEND_API_KEY in Render
            api_key = os.environ.get("SEND_API_KEY", "").strip()
            if not api_key:
                logger.warning("[EMAIL] SEND_API_KEY missing; skipping send to %s", to)
                return
            
            # Send.dev requires 'from' to be an object
            payload = {
                "from": {"email": "verify@synapsepm.us.ci", "name": "SynapsePM"},
                "to": [to] if isinstance(to, str) else list(to),
                "subject": subject,
                "html": html,
            }
            if text:
                payload["text"] = text
                
            r = requests.post(
                "https://api.do.dev/v1/send/emails/send",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(5, 15),
            )
            if r.status_code >= 300:
                logger.error("[EMAIL] Send.dev failed %s: %s", r.status_code, r.text[:500])
            else:
                logger.info("[EMAIL SENT] %s via Send.dev: %s", to, subject)
        except Exception as e:
            logger.exception("[EMAIL] Send failed for %s", to)

    threading.Thread(target=_send, daemon=True).start()
    return True


def send_verification_email(email, token, user_name='there'):
    """Send a professional verification email without exposing the raw token in the UI."""
    from html import escape as html_escape
    safe_name = html_escape(str(user_name or 'there'))
    verify_url = f"{config.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
    safe_url = html_escape(verify_url, quote=True)
    year = datetime.now(timezone.utc).year
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verify your {html_escape(config.APP_NAME)} account</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f1f5f9;padding:40px 16px;"><tr><td align="center">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;width:100%;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(15,23,42,.08);">
<tr><td style="background:linear-gradient(135deg,#0f2b3d,#1a4a6e);padding:32px 40px;">
<div style="font-size:22px;font-weight:800;color:#fff;">Synapse<span style="color:#00CFE8;">PM</span></div>
<div style="color:#94a3b8;font-size:12px;margin-top:4px;letter-spacing:.08em;text-transform:uppercase;">Industrial AI Platform</div>
</td></tr>
<tr><td style="padding:40px;">
<h1 style="margin:0 0 16px;color:#0f2b3d;font-size:24px;">Verify your email address</h1>
<p style="margin:0 0 16px;color:#475569;font-size:15px;line-height:1.6;">Hi {safe_name},</p>
<p style="margin:0 0 24px;color:#475569;font-size:15px;line-height:1.6;">Thanks for signing up for {html_escape(config.APP_NAME)}. Confirm your email address by clicking the button below. This link is valid for <strong>24 hours</strong>.</p>
<table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr><td style="border-radius:10px;background:#00b4aa;">
<a href="{safe_url}" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#fff;text-decoration:none;border-radius:10px;">Verify Email Address</a>
</td></tr></table>
<p style="margin:24px 0 8px;color:#94a3b8;font-size:13px;line-height:1.6;">If the button doesn't work, copy this link into your browser:</p>
<p style="margin:0;color:#64748b;font-size:12px;line-height:1.6;word-break:break-all;"><a href="{safe_url}" style="color:#009688;">{safe_url}</a></p>
<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0;">
<p style="margin:0;color:#94a3b8;font-size:12px;line-height:1.6;">If you didn't create an account, you can safely ignore this email.</p>
</td></tr>
<tr><td style="background:#f8fafc;padding:20px 40px;text-align:center;"><p style="margin:0;color:#94a3b8;font-size:11px;">© {year} {html_escape(config.APP_NAME)}. All rights reserved.</p></td></tr>
</table></td></tr></table></body></html>"""
    text = (f"Hi {user_name or 'there'},\n\n"
            f"Thanks for signing up for {config.APP_NAME}.\n"
            f"Verify your email address using this link (valid for 24 hours):\n\n{verify_url}\n\n"
            "If you didn't create an account, ignore this email.")
    return send_email(email, f"Verify your {config.APP_NAME} account", html, text=text)


def send_password_reset_email(email, otp):
    return send_email(
        email, f"Reset your {config.APP_NAME} password",
        f"""<h1>Reset Password</h1>
        <div style="background:#f1f5f9;padding:20px;text-align:center;font-size:32px;letter-spacing:8px;font-weight:bold;">{otp}</div>
        <p>Expires in 10 minutes.</p>"""
    )


# ============================================================
# PASSWORD POLICY — enforce server-side for every password write
# ============================================================
def password_policy_error(password):
    password = str(password or '')
    if len(password) < 8:
        return 'Password must be at least 8 characters long.'
    if not re.search(r'[A-Z]', password):
        return 'Password must contain at least one uppercase letter.'
    if not re.search(r'[a-z]', password):
        return 'Password must contain at least one lowercase letter.'
    if not re.search(r'\d', password):
        return 'Password must contain at least one digit.'
    if not re.search(r'[^A-Za-z0-9]', password):
        return 'Password must contain at least one special character.'
    return None


# ============================================================
# AUTH DECORATOR
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key_value = request.headers.get('X-API-Key')
        if api_key_value:
            try:
                kh = hashlib.sha256(api_key_value.encode()).hexdigest()
                ak = APIKey.query.filter_by(key_hash=kh, is_deleted=False).first()
                if not ak or (ak.expires_at and
                              ensure_aware(ak.expires_at) <= datetime.now(timezone.utc)):
                    return jsonify({'success': False, 'error': 'Invalid or expired API key'}), 401
                user = db.session.get(User, ak.user_id)
                org = db.session.get(Organization, ak.organization_id)
                if not user or not user.is_active or not org or org.is_suspended:
                    return jsonify({'success': False, 'error': 'API key account unavailable'}), 403
                needed = 'read' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'write'
                perms = ak.permissions or []
                if needed not in perms and 'admin' not in perms:
                    return jsonify({'success': False, 'error': f'API key lacks {needed}'}), 403
                ak.last_used_at = datetime.now(timezone.utc)
                ak.usage_count = (ak.usage_count or 0) + 1
                db.session.commit()
                g.user = user
                g.organization = org
                g.organization_id = org.id
                g.token_payload = {'type': 'api_key', 'api_key_id': ak.id}
                g.token_jti = None
                return f(*args, **kwargs)
            except Exception:
                db.session.rollback()
                logger.exception('API key auth failed')
                return jsonify({'success': False, 'error': 'API key auth failed'}), 500

        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Missing authorization header'}), 401
        token = auth_header.split(' ', 1)[1].strip()

        try:
            payload = jwt.decode(
                token, config.JWT_SECRET_KEY,
                algorithms=[config.JWT_ALGORITHM],
                options={
                    'require': ['exp', 'iat', 'jti'],
                    'verify_iss': False,
                    'verify_aud': False,
                }
            )
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': 'Token expired'}), 401
        except jwt.InvalidTokenError as e:
            logger.warning(f'JWT invalid: {e}')
            return jsonify({'success': False, 'error': 'Invalid token'}), 401

        try:
            if payload.get('type') not in (None, 'access'):
                return jsonify({'success': False, 'error': 'Invalid token type'}), 401

            jti = payload.get('jti')
            if jti and jwt_blacklist.check(jti):
                return jsonify({'success': False, 'error': 'Token revoked'}), 401

            sid = payload.get('sid')
            if sid and not session_manager.check_session(sid):
                return jsonify({'success': False, 'error': 'Session revoked'}), 401

            if redis_client:
                try:
                    revoked_raw = redis_client.get(
                        f"user_revoked:{payload.get('user_id')}"
                    )
                    if revoked_raw:
                        token_iat = int(payload.get('iat') or 0)
                        try:
                            revoked_at = int(revoked_raw)
                        except (TypeError, ValueError):
                            revoked_at = 0

                        if revoked_at > 0:
                            if token_iat < revoked_at:
                                return jsonify({
                                    'success': False,
                                    'error': 'All sessions revoked'
                                }), 401
                        else:
                            if token_iat > 0:
                                redis_client.setex(
                                    f"user_revoked:{payload.get('user_id')}",
                                    config.JWT_REFRESH_EXPIRY_DAYS * 86400,
                                    str(max(0, token_iat - 1))
                                )
                except Exception:
                    logger.warning(
                        "Could not evaluate user-wide token revocation marker",
                        exc_info=True
                    )

            user = db.session.get(User, payload.get('user_id'))
            if not user or not user.is_active:
                return jsonify({'success': False, 'error': 'User not found or inactive'}), 401

            if user.is_locked and user.locked_until and \
                    datetime.now(timezone.utc) < ensure_aware(user.locked_until):
                return jsonify({'success': False, 'error': 'Account locked'}), 403

            org = db.session.get(Organization, user.organization_id)
            if not org:
                return jsonify({'success': False, 'error': 'Organization not found'}), 401
            if org.is_suspended:
                return jsonify({'success': False, 'error': 'Organization suspended'}), 403

            # Browser dashboards make many authenticated GET/read requests. Do not
            # consume the tenant's API-call quota for ordinary reads, otherwise a
            # dashboard refresh storm can lock the whole account out with 429s.
            # Quota is still enforced on mutating/API-heavy requests below.
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                try:
                    plan = config.PLANS.get(str(org.plan or 'free').lower(), config.PLANS['free'])
                    api_limit = plan.get('max_api_calls')
                    if api_limit is not None and redis_client:
                        k = f"usage:api:guard:{org.id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
                        cur = int(redis_client.get(k) or 0)
                        if cur >= int(api_limit):
                            return jsonify({
                                'success': False, 'error': 'API quota reached',
                                'quota_reached': True
                            }), 429
                        redis_client.incr(k)
                        redis_client.expire(k, 172800)
                except Exception:
                    pass

            g.user = user
            g.organization = org
            g.organization_id = org.id
            g.token_payload = payload
            g.token_jti = jti
            try:
                user.last_activity_at = datetime.now(timezone.utc)
                db.session.commit()
            except Exception:
                db.session.rollback()
        except Exception:
            db.session.rollback()
            logger.exception('login_required inner block failed')
            return jsonify({'success': False, 'error': 'Auth check failed'}), 500

        # Enforce MFA for super-admin sessions without locking the account out of setup.
        # A super-admin without MFA can only reach the MFA enrollment/verification and logout endpoints.
        if getattr(g.user, 'role', None) == 'super_admin' and not getattr(g.user, 'is_mfa_enabled', False):
            allowed_mfa_paths = {
                '/api/v1/auth/mfa/setup', '/api/v1/auth/mfa/verify',
                '/api/v1/auth/mfa/status', '/api/v1/auth/logout',
                '/api/v1/auth/me', '/api/v1/user/2fa/status',
            }
            if request.path not in allowed_mfa_paths:
                return jsonify({'success': False, 'error': 'Super-admin MFA setup is required.',
                                'mfa_setup_required': True}), 403
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Authenticate the request and then enforce an admin role.

    Admin blueprint handlers historically used this decorator without
    ``@login_required``.  That left ``g.user`` unset and made admin APIs
    unreliable.  Keep the existing route signatures, but always authenticate
    here (including API-key authentication where supported by login_required).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        def _admin_only(*inner_args, **inner_kwargs):
            user = getattr(g, 'user', None)
            if user is None:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            if user.role not in ('super_admin', 'org_admin', 'admin'):
                return jsonify({'success': False, 'error': 'Admin privileges required'}), 403
            return f(*inner_args, **inner_kwargs)

        if getattr(g, 'user', None) is None:
            return login_required(_admin_only)(*args, **kwargs)
        return _admin_only(*args, **kwargs)
    return decorated


# ============================================================
# MACHINE IOT AUTH — device key OR user JWT
# ============================================================

def machine_iot_auth(machine_id):
    try:
        machine_id = _uuid_or_404(machine_id, 'machine_id')
    except Exception as e:
        return None, None, None, (jsonify({'success': False, 'error': getattr(e, 'description', 'Invalid machine_id')}), 404)
    device_key = (request.headers.get('X-Device-Key')
                  or request.headers.get('X-API-Key'))
    if device_key:
        try:
            kh = hashlib.sha256(device_key.encode()).hexdigest()
            ak = MachineAPIKey.query.filter_by(key_hash=kh, is_deleted=False).first()
            if not ak or ak.revoked_at:
                return None, None, None, (
                    jsonify({'success': False, 'error': 'Invalid device key'}), 401)
            m = db.session.get(Machine, machine_id)
            if not m or m.id != ak.machine_id or m.is_deleted:
                return None, None, None, (
                    jsonify({'success': False,
                             'error': 'Device key does not match this machine'}), 403)
            if bool(getattr(m, 'is_blocked', False)) or str(m.status or '').lower() == 'blocked':
                return None, None, None, (
                    jsonify({'success': False, 'error': 'Machine is blocked by an administrator'}), 403)
            ak.last_used_at = datetime.now(timezone.utc)
            ak.usage_count = (ak.usage_count or 0) + 1
            db.session.commit()
            org = db.session.get(Organization, m.organization_id)
            return m, None, org, None
        except Exception:
            db.session.rollback()
            logger.exception('Device key auth failed')
            return None, None, None, (
                jsonify({'success': False, 'error': 'Device auth failed'}), 500)

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None, None, None, (
            jsonify({'success': False,
                     'error': 'Missing auth (Bearer or X-Device-Key)'}), 401)
    token = auth_header.split(' ', 1)[1].strip()
    try:
        payload = jwt.decode(
            token, config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
            options={'verify_iss': False, 'verify_aud': False},
        )
        user = db.session.get(User, payload.get('user_id'))
        if not user or not user.is_active:
            return None, None, None, (
                jsonify({'success': False, 'error': 'Invalid user'}), 401)
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=user.organization_id,
            is_deleted=False,
        ).first()
        if not m:
            return None, None, None, (
                jsonify({'success': False, 'error': 'Machine not found'}), 404)
        if bool(getattr(m, 'is_blocked', False)) or str(m.status or '').lower() == 'blocked':
            return None, None, None, (
                jsonify({'success': False, 'error': 'Machine is blocked by an administrator'}), 403)
        org = db.session.get(Organization, user.organization_id)
        return m, user, org, None
    except jwt.ExpiredSignatureError:
        return None, None, None, (
            jsonify({'success': False, 'error': 'Token expired'}), 401)
    except jwt.InvalidTokenError:
        return None, None, None, (
            jsonify({'success': False, 'error': 'Invalid token'}), 401)


# ============================================================
# CLEANUP THREAD
# ============================================================

_cleanup_stop = threading.Event()


def _cleanup_loop(app):
    while not _cleanup_stop.is_set():
        try:
            with app.app_context():
                now = datetime.now(timezone.utc)
                try:
                    cutoff = now - timedelta(days=config.AUDIT_RETENTION_DAYS)
                    deleted = AuditLog.query.filter(
                        AuditLog.created_at < cutoff
                    ).delete(synchronize_session=False)
                except Exception:
                    deleted = 0
                try:
                    rcutoff = now - timedelta(days=config.REPORT_RETENTION_DAYS)
                    old_reports = Report.query.filter(Report.created_at < rcutoff).all()
                    for r in old_reports:
                        if r.file_path and os.path.exists(r.file_path):
                            try:
                                os.remove(r.file_path)
                            except Exception:
                                pass
                        db.session.delete(r)
                except Exception:
                    old_reports = []
                try:
                    dcutoff = now - timedelta(days=config.DOWNLOAD_RETENTION_DAYS)
                    Download.query.filter(
                        Download.created_at < dcutoff
                    ).delete(synchronize_session=False)
                except Exception:
                    pass
                try:
                    UserSession.query.filter(
                        UserSession.expires_at < now
                    ).delete(synchronize_session=False)
                except Exception:
                    pass
                try:
                    deletion_cutoff = now - timedelta(days=30)
                    pending = User.query.filter(User.is_active == False, User.deactivated_at != None, User.deactivated_at < deletion_cutoff).all()
                    for u in pending:
                        uid = u.id
                        # Explicitly remove user-owned rows with CASCADE/SET NULL semantics.
                        OAuthAccount.query.filter_by(user_id=uid).delete(synchronize_session=False)
                        UserSession.query.filter_by(user_id=uid).delete(synchronize_session=False)
                        Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
                        APIKey.query.filter_by(user_id=uid).delete(synchronize_session=False)
                        AuditLog.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
                        Machine.query.filter_by(owner_id=uid).update({'owner_id': None}, synchronize_session=False)
                        Report.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
                        CareerSubmission.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
                        ContactSubmission.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
                        EnterpriseRequest.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
                        db.session.delete(u)
                    db.session.flush()
                except Exception:
                    logger.exception('Hard-delete retention job failed')

                try:
                    insp = inspect(db.engine)
                    if 'webhook_events' in insp.get_table_names():
                        WebhookEvent.query.filter(
                            WebhookEvent.received_at < (now - timedelta(days=30))
                        ).delete(synchronize_session=False)
                except Exception:
                    pass
                db.session.commit()
                logger.info(
                    f"Cleanup: audit={deleted}, "
                    f"reports={len(old_reports) if old_reports else 0}"
                )
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.exception('Cleanup error')
        _cleanup_stop.wait(config.CLEANUP_INTERVAL_SECONDS)


# ============================================================
# MQTT SUBSCRIBER
# ============================================================

_mqtt_client = None


def start_mqtt_subscriber(app):
    global _mqtt_client
    if not MQTT_AVAILABLE:
        logger.info("MQTT subscriber not started (paho-mqtt not installed)")
        return None
    if not config.ENABLE_MQTT:
        logger.info("MQTT subscriber disabled (ENABLE_MQTT != true)")
        return None

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"✅ MQTT connected to {config.MQTT_BROKER}:{config.MQTT_PORT}")
            topic = f"{config.MQTT_TOPIC_PREFIX}/+/sensor"
            client.subscribe(topic, qos=config.MQTT_QOS)
            logger.info(f"📡 MQTT subscribed to {topic} (QoS {config.MQTT_QOS})")
        else:
            logger.error(f"MQTT connect failed: rc={rc}")

    reconnect_lock = threading.Lock()
    reconnect_state = {'scheduled': False}

    def on_disconnect(client, userdata, rc):
        logger.warning(f"MQTT disconnected: rc={rc}")
        if rc == 0:
            return
        # Do not sleep or reconnect inside Paho's callback thread. Schedule one
        # bounded exponential-backoff loop and let Paho's network loop continue.
        with reconnect_lock:
            if reconnect_state['scheduled']:
                return
            reconnect_state['scheduled'] = True

        def _reconnect_with_backoff():
            try:
                for delay in (5, 10, 30, 60, 120, 300):
                    stop_event = globals().get('_cleanup_stop')
                    if stop_event is not None and stop_event.is_set():
                        return
                    time.sleep(delay)
                    try:
                        client.reconnect()
                        logger.info('MQTT reconnect requested after %ss backoff', delay)
                        return
                    except Exception as exc:
                        logger.warning('MQTT reconnect attempt failed after %ss: %s', delay, exc)
                logger.error('MQTT reconnect attempts exhausted; Paho may retry on its own.')
            finally:
                with reconnect_lock:
                    reconnect_state['scheduled'] = False

        threading.Thread(target=_reconnect_with_backoff, name='mqtt-reconnect', daemon=True).start()

    def on_message(client, userdata, msg):
        with app.app_context():
            try:
                topic = msg.topic
                parts = topic.split('/')
                if len(parts) < 3:
                    return
                machine_id = parts[-2]
                payload = json.loads(msg.payload.decode('utf-8'))

                machine = (Machine.query.filter_by(id=machine_id, is_deleted=False).first()
                           or Machine.query.filter_by(uuid=machine_id, is_deleted=False).first())
                if not machine:
                    logger.warning(f"MQTT: unknown machine {machine_id}")
                    return

                readings = payload.get('readings') or {}
                if not isinstance(readings, dict):
                    logger.warning('MQTT: readings must be a JSON object on %s', msg.topic)
                    return
                if not readings:
                    # Accept named numeric sensor fields at the payload root as
                    # well as the preferred {"readings": {...}} envelope.
                    reserved = {'timestamp', 'machine_id', 'device_id', 'sequence', 'source'}
                    readings = {str(k): v for k, v in payload.items() if str(k).lower() not in reserved}
                clean_readings = {}
                for feature_name, raw_value in readings.items():
                    if isinstance(raw_value, bool) or raw_value is None:
                        continue
                    try:
                        numeric_value = float(raw_value)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(numeric_value):
                        clean_readings[str(feature_name)] = numeric_value
                if not clean_readings:
                    logger.warning('MQTT: no finite numeric readings on %s', msg.topic)
                    return
                def _mqtt_value(*names):
                    normalized = {re.sub(r'[^a-z0-9]+', '_', k.lower()).strip('_'): v for k, v in clean_readings.items()}
                    for name in names:
                        if name in normalized:
                            return normalized[name]
                    return None
                temperature = _mqtt_value('temperature', 'temperature_c', 'temp', 'temp_c')
                vibration = _mqtt_value('vibration', 'vibration_rms', 'vibration_mm_s', 'vib')
                pressure = _mqtt_value('pressure', 'pressure_psi', 'pressure_bar', 'pressure_kpa')
                s = SensorData(
                    machine_id=machine.id,
                    temperature=temperature,
                    vibration=vibration,
                    pressure=pressure,
                    readings=clean_readings,
                    source='mqtt',
                )
                db.session.add(s)
                if s.temperature is not None:
                    machine.temperature = max(-50.0, min(500.0, float(s.temperature)))
                if s.vibration is not None:
                    machine.vibration = max(0.0, min(100.0, float(s.vibration)))
                if s.pressure is not None:
                    machine.pressure = max(0.0, min(1000.0, float(s.pressure)))
                machine.status = 'online'
                machine.machine_data = {**(machine.machine_data or {}), 'telemetry_state': 'receiving', 'last_telemetry_at': datetime.now(timezone.utc).isoformat()}
                machine.last_activity_at = datetime.now(timezone.utc)
                db.session.commit()

                try:
                    broadcast_both('sensor_update', {
                        'machine': machine.to_dict(),
                        'sensor_data': s.to_dict(),
                    }, org_id=machine.organization_id)
                except Exception:
                    pass
            except json.JSONDecodeError:
                logger.warning(f"MQTT: invalid JSON on {msg.topic}")
            except Exception:
                logger.exception(f"MQTT message failed on {msg.topic}")
                try:
                    db.session.rollback()
                except Exception:
                    pass

    try:
        client = mqtt_client_lib.Client(
            client_id=f"synapsepm-{secrets.token_hex(4)}",
            clean_session=True,
        )
        if config.MQTT_USERNAME:
            client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.connect_async(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
        client.loop_start()
        _mqtt_client = client
        logger.info(f"✅ MQTT subscriber started (broker={config.MQTT_BROKER}:{config.MQTT_PORT})")
        return client
    except Exception as e:
        logger.error(f"MQTT connect error: {e}")
        return None



# ============================================================
# TRUSTWORTHY PREDICTION CONTRACT HELPERS (v25)
# ============================================================

TARGET_LEAKAGE_COLUMNS = {
    'rul', 'rul_hours', 'remaining_useful_life', 'failure',
    'failure_event', 'failure_probability', 'target', 'label',
    'health_score', 'degradation_stage'
}

# Machine-type sensor fields used by the frontend contract. These describe
# possible telemetry fields; they do not synthesize readings or replace a model.
SENSOR_CATALOG = {
    'pump': ['temperature', 'vibration', 'pressure', 'flow', 'rpm', 'power'],
    'turbine': ['temperature', 'vibration', 'pressure', 'rpm', 'power', 'oil_quality'],
    'compressor': ['temperature', 'vibration', 'pressure', 'flow', 'power'],
    'motor': ['temperature', 'vibration', 'current', 'rpm', 'power'],
    'generator': ['temperature', 'vibration', 'voltage', 'current', 'power'],
    'ct': ['temperature', 'pressure', 'tube_current', 'anode_rotation_speed'],
    'mri': ['temperature', 'pressure', 'helium_level', 'gradient_stability'],
    'xray': ['temperature', 'pressure', 'tube_voltage', 'tube_current'],
    'ultrasound': ['temperature', 'pressure', 'probe_cycles'],
    'ventilator': ['temperature', 'pressure', 'flow', 'tidal_volume'],
    'ecg': ['temperature', 'signal_quality'],
    'laptop': ['temperature', 'fan_rpm', 'cpu_load', 'battery_health'],
    'server': ['temperature', 'fan_rpm', 'cpu_load', 'memory_usage', 'disk_io'],
    'network': ['temperature', 'throughput', 'packet_loss', 'uptime_hours'],
}

def sensor_catalog_for(machine_type):
    return SENSOR_CATALOG.get(
        str(machine_type or '').strip().lower(),
        ['temperature', 'vibration', 'pressure']
    )

UNIT_CONVERSIONS = {
    ('pressure_psi', 'pressure_bar'): 1.0 / 14.5037738,
    ('pressure_psi', 'pressure_kpa'): 6.894757293,
    ('pressure_bar', 'pressure_psi'): 14.5037738,
    ('pressure_bar', 'pressure_kpa'): 100.0,
    ('pressure_kpa', 'pressure_psi'): 1.0 / 6.894757293,
    ('pressure_kpa', 'pressure_bar'): 0.01,
    ('temperature_c', 'temperature_c'): 1.0,
    ('temperature_f', 'temperature_c'): lambda x: (x - 32.0) * 5.0 / 9.0,
    ('temperature_k', 'temperature_c'): lambda x: x - 273.15,
    ('temperature_c', 'temperature_f'): lambda x: x * 9.0 / 5.0 + 32.0,
    ('temperature_c', 'temperature_k'): lambda x: x + 273.15,
}

def _feature_unit(name):
    n = re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')
    for u in ('psi', 'kpa', 'bar', 'celsius', 'fahrenheit', 'kelvin', 'c', 'f', 'k'):
        if n.endswith('_' + u):
            return {'celsius':'c','fahrenheit':'f','kelvin':'k'}.get(u, u)
    return None

def _feature_semantic(name):
    n = re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')
    aliases = {
        'temp':'temperature','temperature':'temperature','temperature_c':'temperature',
        'temp_c':'temperature','temperature_f':'temperature','temp_f':'temperature',
        'temperature_k':'temperature','pressure':'pressure','pressure_psi':'pressure',
        'pressure_bar':'pressure','pressure_kpa':'pressure','vib':'vibration',
        'vibration':'vibration','vibration_rms':'vibration','vibration_mm_s':'vibration',
        'rpm':'rpm','rotational_speed':'rpm','speed_rpm':'rpm'
    }
    return aliases.get(n, n)

def _convert_unit_series(series, source_name, target_name):
    src = _feature_unit(source_name)
    dst = _feature_unit(target_name)
    if src == dst or not src or not dst:
        return series, {'source_column': source_name, 'unit': src or dst, 'conversion': None}
    src_key = f'{_feature_semantic(source_name)}_{src}'
    dst_key = f'{_feature_semantic(target_name)}_{dst}'
    fn = UNIT_CONVERSIONS.get((src_key, dst_key))
    if fn is None:
        raise ModelCompatibilityError(
            f'Unit mismatch for {target_name}: input {source_name} cannot be safely converted.'
        )
    if callable(fn):
        out = series.astype(float).map(fn)
        conversion = f'{src_key}->{dst_key}'
    else:
        out = series.astype(float) * float(fn)
        conversion = f'{src_key}->{dst_key} x {fn}'
    return out, {'source_column': source_name, 'unit': src, 'conversion': conversion}

def assess_sensor_quality(df):
    if df is None or df.empty:
        return 0.0, ['EMPTY_DATASET']
    numeric = df.select_dtypes(include='number')
    if numeric.empty:
        return 0.0, ['NO_NUMERIC_FEATURES']
    missing_ratio = float(numeric.isna().mean().mean())
    constant_ratio = float((numeric.nunique(dropna=True) <= 1).mean())
    usable_ratio = float((numeric.notna().sum().sum()) / max(1, numeric.size))
    score = max(0.0, min(1.0, 0.55 * usable_ratio + 0.30 * (1.0 - missing_ratio) + 0.15 * (1.0 - constant_ratio)))
    flags = []
    if missing_ratio >= 0.90:
        flags.append('HIGH_MISSINGNESS')
    if constant_ratio >= 0.90:
        flags.append('MOSTLY_CONSTANT')
    return score, flags

def check_target_leakage(df):
    found = []
    if df is not None:
        for c in df.columns:
            n = re.sub(r'[^a-z0-9]+', '_', str(c).lower()).strip('_')
            if n in TARGET_LEAKAGE_COLUMNS:
                found.append(str(c))
    return found

def _trust_level(family_score, sensor_quality, ood_count, validation_ok):
    score = 0.0
    score += min(1.0, max(0.0, float(family_score or 0.0))) * 0.30
    score += min(1.0, max(0.0, float(sensor_quality or 0.0))) * 0.30
    score += 0.25 if not ood_count else max(0.0, 0.25 - 0.06 * len(ood_count))
    score += 0.15 if validation_ok else 0.0
    if score >= 0.80:
        return 'HIGH'
    if score >= 0.60:
        return 'MEDIUM'
    return 'LOW'

# ============================================================
# ML ENGINE (unchanged from v17.0.0)
# ============================================================

class ModelCompatibilityError(ValueError):
    """Raised when a real trained artifact cannot safely serve the supplied data."""
    pass


class MLEngine:
    """Production ML registry for SynapsePM's family-bundle model layout.

    Expected family layout:
        <family>/
            metadata.json
            metrics.json
            preprocessor.pkl
            feature_engineer.pkl
            catboost_model.pkl
            xgboost_model.pkl
            lightgbm_model.pkl
            gradient_boosting_model.pkl
            random_forest_model.pkl
            ridge_model.pkl
            ...

    The family is selected from metadata/schema fingerprints.  The shared
    feature-engineer and preprocessor are loaded once per family, then the
    algorithms are ranked from metrics.json.  Failed algorithms are skipped and
    the next real trained algorithm is tried.  No synthetic prediction is used.
    """

    MODEL_SUFFIXES = {
        '.pkl', '.joblib', '.pickle', '.pt', '.pth', '.onnx', '.h5', '.keras'
    }
    DEPENDENCY_FILES = {
        'preprocessor.pkl', 'preprocessor.joblib', 'preprocessor.pickle',
        'feature_engineer.pkl', 'feature_engineer.joblib', 'feature_engineer.pickle',
        'feature_engineering.pkl', 'feature_engineering.joblib',
        'scaler.pkl', 'scaler.joblib', 'transformer.pkl', 'transformer.joblib',
        'encoder.pkl', 'label_encoder.pkl', 'imputer.pkl', 'feature_scaler.pkl',
        'pipeline.pkl', 'column_transformer.pkl', 'target_encoder.pkl',
        'preprocess.pkl', 'preprocessing.pkl', 'artifact_manifest.pkl'
    }
    ALGORITHM_TOKENS = (
        'hist_gradient_boosting', 'gradient_boosting', 'random_forest',
        'extra_trees', 'linear_regression', 'bayesian_ridge', 'elasticnet',
        'xgboost', 'lightgbm', 'catboost', 'randomforest', 'adaboost',
        'ridge', 'lasso', 'svr', 'mlp', 'lstm', 'gru', 'tcn', 'transformer',
        'cnn', 'rf', 'gbm', 'gb', 'xgb', 'lgbm', 'cat'
    )

    def __init__(self):
        self.device = self._detect_device()
        self.models = {}
        self.by_family = {}
        self.all_by_family = {}
        self.production_ids = []
        self.registry_path = Path(config.ML_MODEL_PATH) / 'production_registry.json'
        self._lock = threading.RLock()
        self._model_cache = OrderedDict()
        self._family_cache = {}
        self._discovered_paths = set()
        self._probe_failures = {}
        self.cache_hits = self.cache_misses = self.cache_evictions = 0
        self._init()

    def _detect_device(self):
        if config.ML_USE_GPU and PYTORCH_AVAILABLE and torch.cuda.is_available():
            return 'cuda'
        return 'cpu'

    @staticmethod
    def _norm(name):
        return re.sub(r'[^a-z0-9]+', '_', str(name).strip().lower()).strip('_')

    @classmethod
    def _canonical_feature(cls, name):
        n = cls._norm(name)
        aliases = {
            'temperature': {'temperature', 'temperature_c', 'temp', 'temp_c', 'temp_celsius', 'temperature_celsius'},
            'pressure': {'pressure', 'pressure_psi', 'pressure_bar', 'pressure_kpa'},
            'vibration': {'vibration', 'vibration_rms', 'vibration_mm_s', 'vibration_mms', 'vib', 'vib_rms'},
            'humidity': {'humidity', 'humidity_pct', 'relative_humidity'},
            'voltage': {'voltage', 'voltage_v'},
            'current': {'current', 'motor_current', 'current_a', 'current_amp'},
            'rpm': {'rpm', 'rotational_speed', 'speed_rpm'},
            'power': {'power', 'power_consumption', 'power_kw', 'power_w'},
            'energy': {'energy', 'energy_consumption', 'energy_kwh'},
            'flow': {'flow', 'flow_rate', 'flow_rate_lpm', 'flow_lpm'},
            'oil_quality': {'oil_quality', 'oil_health', 'lubrication_quality'},
            'oil_pressure': {'oil_pressure', 'lubricant_pressure'},
            'oil_temperature': {'oil_temperature', 'lubricant_temperature'},
            'coolant_temperature': {'coolant_temperature', 'coolant_temp'},
            'coolant_flow': {'coolant_flow', 'coolant_flow_rate'},
            'bearing_temperature': {'bearing_temperature', 'bearing_temp'},
            'noise': {'noise', 'acoustic_noise', 'sound_level', 'acoustic_level'},
            'operating_hours': {'operating_hours', 'hours_operated', 'runtime_hours'},
            'load': {'load', 'load_percentage', 'load_percent', 'load_pct'},
            'torque': {'torque', 'torque_nm'},
        }
        for canonical, names in aliases.items():
            if n in {cls._norm(x) for x in names}:
                return canonical
        return n

    @staticmethod
    def _safe_extract(zp, dest):
        dest = Path(dest).resolve()
        with zipfile.ZipFile(zp, 'r') as zf:
            for member in zf.infolist():
                target = (dest / member.filename).resolve()
                if target != dest and not str(target).startswith(str(dest) + os.sep):
                    raise RuntimeError(f'Unsafe archive member: {member.filename}')
            for member in zf.infolist():
                target = dest / member.filename
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, 'r') as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)

    def _release_candidates(self, configured_root):
        values = [
            getattr(config, 'MODEL_RELEASE_ZIP', ''),
            os.environ.get('MODEL_RELEASE_ZIP', ''),
            str(Path.cwd() / 'trained model.zip'),
            str(Path.cwd() / 'trained_model.zip'),
            str(configured_root / 'trained model.zip'),
            str(configured_root / 'trained_model.zip'),
        ]
        result = []
        seen = set()
        for raw in values:
            if not raw:
                continue
            p = Path(raw).expanduser()
            if p.exists() and p.is_file() and p.suffix.lower() == '.zip':
                key = str(p.resolve()).lower()
                if key not in seen:
                    result.append(p)
                    seen.add(key)
        return result

    
    def _download_private_hf_release(self):
        """Download and validate a private Hugging Face model ZIP."""

        import os
        import shutil
        import zipfile
        from pathlib import Path

        repo_id = os.environ.get("HF_MODEL_REPO", "").strip()
        filename = os.environ.get(
            "HF_MODEL_FILENAME", "trained model.zip"
        ).strip()
        token = os.environ.get("HF_TOKEN", "").strip()
        revision = os.environ.get("HF_MODEL_REVISION", "main").strip() or "main"

        # No configured repository means there is no remote download to perform.
        if not repo_id:
            logger.info("No Hugging Face model repository configured; skipping download.")
            return

        if not filename:
            raise RuntimeError("HF_MODEL_FILENAME is empty.")

        if not token:
            raise RuntimeError("HF_TOKEN is required for the private model repository.")

        try:
            from huggingface_hub import hf_hub_download

            release_path = Path(config.MODEL_RELEASE_ZIP).expanduser().resolve()
            release_path.parent.mkdir(parents=True, exist_ok=True)

            max_mb = int(os.environ.get("HF_MODEL_MAX_DOWNLOAD_MB", "2048"))
            if max_mb < 1:
                raise ValueError("HF_MODEL_MAX_DOWNLOAD_MB must be at least 1.")

            logger.info(
                "Downloading private model release "
                "(repo=%s, file=%s, revision=%s)",
                repo_id,
                filename,
                revision,
            )

            # Safe diagnostics: never log the token itself.
            from huggingface_hub import HfApi

            logger.info(
                "HF diagnostic: token_present=%s, token_length=%s, "
                "repo=%r, filename=%r, revision=%r",
                bool(token),
                len(token) if token else 0,
                repo_id,
                filename,
                revision,
            )
            api = HfApi(token=token)
            info = api.model_info(repo_id, revision=revision)
            logger.info("HF repository authentication succeeded: %s", info.id)
            files = api.list_repo_files(repo_id, revision=revision)
            logger.info("HF repository filenames: %r", files)

            # The Hub client handles private-repository authentication and URLs.
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                repo_type="model",
                revision=revision,
                token=token,
            )

            downloaded_path = Path(downloaded_path)

            if not downloaded_path.is_file():
                raise RuntimeError("Hugging Face did not return a model archive file.")

            if downloaded_path.stat().st_size > max_mb * 1024 * 1024:
                raise RuntimeError(
                    f"Model archive exceeds HF_MODEL_MAX_DOWNLOAD_MB ({max_mb} MB)."
                )

            if not zipfile.is_zipfile(downloaded_path):
                raise RuntimeError(
                    "The downloaded Hugging Face file is not a valid ZIP archive."
                )

            # Stage beside the destination so os.replace is atomic on the same filesystem.
            temp_path = release_path.with_name(
                release_path.name + ".download-part"
            )

            try:
                shutil.copyfile(downloaded_path, temp_path)

                if not zipfile.is_zipfile(temp_path):
                    raise RuntimeError("The staged model archive failed ZIP validation.")

                os.replace(str(temp_path), str(release_path))
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

            logger.info(
                "Private model release downloaded and ZIP-validated (%d bytes).",
                release_path.stat().st_size,
            )

        except Exception as exc:
            # Do not log the token or request headers.
            logger.error(
                "Private Hugging Face model download failed (%s): %s",
                type(exc).__name__,
                str(exc)[:300],
            )
            raise RuntimeError(
                "Private model release download failed. Check the deployment logs "
                "for the diagnostic above."
            ) from exc

    def _init(self):
        configured_root = Path(config.ML_MODEL_PATH).expanduser().resolve()
        configured_root.mkdir(parents=True, exist_ok=True)

        # The archive must exist before the normal extraction and discovery logic runs.
        self._download_private_hf_release()

        extracted = False
        for release in self._release_candidates(configured_root):
            try:
                marker = configured_root / '.release_extracted.sha256'
                digest = hashlib.sha256(release.read_bytes()).hexdigest()
                old = marker.read_text(encoding='utf-8').strip() if marker.exists() else ''
                if digest != old:
                    self._safe_extract(release, configured_root)
                    marker.write_text(digest, encoding='utf-8')
                    extracted = True
                    logger.info('ML release extracted: %s -> %s', release, configured_root)
                else:
                    logger.info('ML release already extracted: %s', release)
                break
            except Exception as exc:
                logger.exception('ML release extraction failed for %s: %s', release, exc)

        roots = []
        candidates = [
            configured_root,
            configured_root / 'trained_models',
            configured_root / 'trained_model',
            configured_root / 'extracted_models_v27' / 'trained_models',
            configured_root.parent / 'trained_models',
            configured_root.parent / 'trained_model' / 'trained_models',
            configured_root.parent / 'extracted_models_v27' / 'trained_models',
            project_root / 'trained_models',
            project_root / 'trained_model' / 'trained_models',
            project_root / 'models',
            project_root / 'models' / 'models',
        ]
        seen_roots = set()
        for root in candidates:
            try:
                root = Path(root).expanduser().resolve()
            except Exception:
                continue
            if root.exists() and root.is_dir() and str(root).lower() not in seen_roots:
                roots.append(root)
                seen_roots.add(str(root).lower())

        self.models.clear()
        self.by_family.clear()
        self.all_by_family.clear()
        self.production_ids.clear()
        self._model_cache.clear()
        self._family_cache.clear()
        self._probe_failures.clear()
        self._discovered_paths.clear()

        for root in roots:
            self._discover_family_bundles(root)

        self._load_declared_runtime_classes()
        self._rebuild_indexes()
        self._select_champions()
        self._write_registry_snapshot(extracted=extracted, roots=roots)

        logger.info(
            'ML registry ready: discovered=%d artifacts across %d families; production=%d; '
            'loaded=0 (lazy); cache=%d; extracted=%s',
            len(self.models), len(self.all_by_family), len(self.production_ids),
            config.MODEL_CACHE_SIZE, extracted
        )
        if not self.models:
            msg = (f'NO_TRAINED_MODEL_ARTIFACTS: searched ML_MODEL_PATH={config.ML_MODEL_PATH} '
                   f'and release={getattr(config, "MODEL_RELEASE_ZIP", "")}')
            if config.IS_PRODUCTION:
                raise RuntimeError(msg + ' — refusing to boot in production.')
            logger.error(msg)

    def _detect_framework(self, path):
        ext = Path(path).suffix.lower()
        return {'.pkl': 'pickle', '.pickle': 'pickle', '.joblib': 'pickle', '.pt': 'pytorch', '.pth': 'pytorch', '.onnx': 'onnx', '.h5': 'tensorflow', '.keras': 'tensorflow'}.get(ext, 'unknown')

    def _metadata_from_dir(self, folder):
        folder = Path(folder)
        data = {}
        for name in ('metadata.json', 'info.json', 'model.json', 'manifest.json'):
            p = folder / name
            if not p.exists():
                continue
            try:
                blob = json.loads(p.read_text(encoding='utf-8'))
                if isinstance(blob, dict):
                    data.update(blob)
                break
            except Exception as exc:
                logger.warning('Invalid %s: %s', p, exc)

        metrics_path = folder / 'metrics.json'
        metrics = {}
        if metrics_path.exists():
            try:
                blob = json.loads(metrics_path.read_text(encoding='utf-8'))
                if isinstance(blob, dict):
                    metrics = blob
            except Exception as exc:
                logger.warning('Invalid metrics.json: %s', exc)
        data['_metrics_by_model'] = metrics
        return data

    def _find_family_folder(self, model_path, root):
        cur = model_path.parent
        metadata_names = ('metadata.json', 'metrics.json', 'info.json', 'manifest.json', 'model.json')
        # The closest directory containing metadata is the family bundle.
        probe = cur
        while True:
            if any((probe / n).exists() for n in metadata_names):
                return probe
            if probe == root or probe.parent == probe:
                break
            probe = probe.parent
        # Typical layout: root/<family>/<algorithm>_model.pkl
        return cur

    def _parse_algorithm(self, path):
        stem = self._norm(path.stem)
        for suffix in ('_model', '_regressor', '_classifier', '_estimator', '_predictor', '_artifact'):
            if stem.endswith(suffix):
                stem = stem[:-len(suffix)].rstrip('_')
        for token in sorted(self.ALGORITHM_TOKENS, key=len, reverse=True):
            nt = self._norm(token)
            if stem == nt or stem.endswith('_' + nt):
                return nt
        return stem or 'unknown'

    def _json_features(self, metadata):
        schema = metadata.get('schema') if isinstance(metadata.get('schema'), dict) else {}
        raw = None
        for key in (
            'raw_features', 'raw_feature_names', 'input_features', 'input_feature_names',
            'source_features', 'source_columns', 'feature_names', 'features', 'columns'
        ):
            value = metadata.get(key)
            if value:
                raw = value
                break
            value = schema.get(key)
            if value:
                raw = value
                break
        if isinstance(raw, dict):
            raw = list(raw.keys())
        if isinstance(raw, str):
            raw = [x.strip() for x in re.split(r'[,;|]', raw) if x.strip()]
        if not isinstance(raw, (list, tuple)):
            raw = []
        normalized = []
        for item in raw:
            if isinstance(item, dict):
                item = item.get('name') or item.get('feature') or item.get('column') or item.get('source')
            if item is not None and str(item).strip():
                normalized.append(self._norm(item))
        return normalized

    def _engineered_features(self, metadata):
        schema = metadata.get('schema') if isinstance(metadata.get('schema'), dict) else {}
        raw = metadata.get('engineered_features') or schema.get('engineered_features') or metadata.get('model_features')
        if isinstance(raw, dict):
            raw = list(raw.keys())
        if isinstance(raw, str):
            raw = [x.strip() for x in re.split(r'[,;|]', raw) if x.strip()]
        if not isinstance(raw, (list, tuple)):
            return []
        out = []
        for item in raw:
            if isinstance(item, dict):
                item = item.get('name') or item.get('feature') or item.get('column')
            if item is not None and str(item).strip():
                out.append(self._norm(item))
        return out

    def _metrics_for_algorithm(self, blob, algorithm, stem):
        if not isinstance(blob, dict):
            return {}
        # Some trainers wrap per-model scores under models/results/algorithms.
        for wrapper in ('models', 'results', 'algorithms', 'per_model', 'model_metrics'):
            nested_blob = blob.get(wrapper)
            if isinstance(nested_blob, dict):
                found = self._metrics_for_algorithm(nested_blob, algorithm, stem)
                if found:
                    return found
        scalar = {k: v for k, v in blob.items() if not isinstance(v, dict)}
        nested = {str(k): v for k, v in blob.items() if isinstance(v, dict)}
        candidates = {self._norm(algorithm), self._norm(stem), self._norm(stem.replace('_model', ''))}
        for key, value in nested.items():
            nk = self._norm(key)
            if nk in candidates or any(c and (c in nk or nk in c) for c in candidates):
                return {**scalar, **value}
        # If the entire file is a flat metric record, use it for every algorithm.
        metric_keys = {'mae','rmse','r2','accuracy','f1','precision','recall','mape'}
        if any(k in blob for k in metric_keys):
            return {k: blob[k] for k in blob if k in metric_keys or not isinstance(blob[k], dict)}
        return scalar

    def _resolve_bundle_file(self, folder, names):
        for base in (Path(folder), Path(folder).parent):
            for name in names:
                p = base / name
                if p.exists() and p.is_file():
                    return str(p)
        return None

    def _discover_family_bundles(self, root):
        root = Path(root).resolve()
        if not root.exists():
            return
        files = []
        try:
            iterator = root.rglob('*')
        except Exception as exc:
            logger.warning('Cannot scan model root %s: %s', root, exc)
            return
        for p in iterator:
            try:
                if not p.is_file() or p.suffix.lower() not in self.MODEL_SUFFIXES:
                    continue
                if p.name.lower() in self.DEPENDENCY_FILES:
                    continue
                if any(part.lower() in {'.git', '__pycache__', '__macosx'} for part in p.parts):
                    continue
                files.append(p)
            except OSError:
                continue

        for model_path in sorted(files, key=lambda x: str(x).lower()):
            real = str(model_path.resolve()).lower()
            if real in self._discovered_paths:
                continue
            self._discovered_paths.add(real)
            folder = self._find_family_folder(model_path, root)
            metadata = self._metadata_from_dir(folder)
            schema = metadata.get('schema') if isinstance(metadata.get('schema'), dict) else {}

            family_raw = (
                metadata.get('dataset_family') or metadata.get('family_id') or
                metadata.get('family') or metadata.get('dataset_name') or
                metadata.get('dataset') or folder.name
            )
            family = self._norm(family_raw) or self._norm(folder.name) or 'unknown'
            algorithm = self._parse_algorithm(model_path)
            mid = f'{family}::{algorithm}'
            if mid in self.models:
                mid = f'{family}::{algorithm}::{self._norm(model_path.stem)}'

            features = self._json_features(metadata)
            engineered = self._engineered_features(metadata)
            feature_count = (
                metadata.get('feature_count') or metadata.get('n_features') or
                metadata.get('n_features_in') or schema.get('feature_count') or
                len(engineered) or len(features) or 0
            )
            try:
                feature_count = int(feature_count)
            except Exception:
                feature_count = 0

            sequence_length = metadata.get('sequence_length') or metadata.get('window_size') or metadata.get('lookback') or 1
            try:
                sequence_length = max(1, int(sequence_length))
            except Exception:
                sequence_length = 1

            metrics = self._metrics_for_algorithm(
                metadata.get('_metrics_by_model') or metadata.get('metrics') or {},
                algorithm, model_path.stem
            )
            # IMPORTANT: numeric values in metrics.json are reported training
            # results, not proof of production validation. Never upgrade an
            # artifact to 'validated' merely because MAE/RMSE/R2 exists.
            validation = metadata.get('validation') if isinstance(metadata.get('validation'), dict) else {}
            explicit_validated = bool(
                metadata.get('production_validated') is True or
                metadata.get('validated') is True or
                validation.get('status') == 'passed'
            )
            validation_evidence = {
                'status': validation.get('status'),
                'dataset': validation.get('dataset') or validation.get('test_dataset') or metadata.get('evaluation_dataset'),
                'split': validation.get('split') or metadata.get('test_split'),
                'no_leakage_check': validation.get('no_leakage_check'),
                'evaluated_at': validation.get('evaluated_at'),
                'report_id': validation.get('report_id'),
            }
            validated = explicit_validated
            metric_provenance = 'production_validated' if explicit_validated else 'reported_metrics_only'

            preprocessor_path = self._resolve_bundle_file(
                folder,
                ('preprocessor.pkl', 'preprocessor.joblib', 'preprocessor.pickle',
                 'scaler.pkl', 'scaler.joblib', 'transformer.pkl', 'transformer.joblib')
            )
            feature_engineer_path = self._resolve_bundle_file(
                folder,
                ('feature_engineer.pkl', 'feature_engineer.joblib', 'feature_engineer.pickle',
                 'feature_engineering.pkl', 'feature_engineering.joblib')
            )

            info = {
                'id': mid,
                'family': family,
                'dataset': str(metadata.get('dataset') or metadata.get('dataset_name') or family),
                'algorithm': algorithm,
                'model_type': algorithm,
                'version': str(metadata.get('version') or metadata.get('training_version') or '1.0'),
                'model_path': str(model_path),
                'framework': self._detect_framework(model_path),
                'bundle_path': str(folder),
                'metadata': metadata,
                'features': features,
                'raw_features': features,
                'engineered_features': engineered,
                'feature_count': feature_count,
                'sequence_length': sequence_length,
                'target': str(metadata.get('target') or metadata.get('target_name') or 'RUL_hours'),
                'task_type': str(metadata.get('task') or metadata.get('task_type') or 'regression'),
                'metrics': metrics if isinstance(metrics, dict) else {},
                'validated': validated,
                'metric_provenance': metric_provenance,
                'validation_evidence': validation_evidence,
                'preprocessor_path': preprocessor_path,
                'feature_engineer_path': feature_engineer_path,
                'scaler_path': preprocessor_path,
                'model': None,
                'preprocessor': None,
                'feature_engineer': None,
                'loaded': False,
                'load_status': 'not_loaded',
                'load_error': None,
                'quarantined': False,
                'checksum': None,
                'checksum_status': 'unverified',
                'training_ranges': metadata.get('training_ranges') or metadata.get('feature_ranges') or {},
                'preprocessing_owned_by_model': False,
                'contract_source': 'metadata' if features else 'artifact',
            }
            try:
                if model_path.stat().st_size > config.MAX_MODEL_FILE_MB * 1024 * 1024:
                    info['quarantined'] = True
                    info['load_status'] = 'too_large'
                    info['checksum_status'] = 'too_large'
                else:
                    info['checksum'] = hashlib.sha256(model_path.read_bytes()).hexdigest()
                    info['checksum_status'] = 'discovered'
            except Exception as exc:
                info['checksum_status'] = 'unavailable'
                logger.warning('Checksum unavailable for %s: %s', model_path, exc)

            self.models[mid] = info

        self._rebuild_indexes()
        logger.info(
            'Discovered %d model artifacts across %d families under %s',
            len(self.models), len(self.all_by_family), root
        )

    def _rebuild_indexes(self):
        self.all_by_family = {}
        for mid, info in self.models.items():
            self.all_by_family.setdefault(info.get('family') or 'unknown', []).append(mid)
        self.by_family = {family: list(mids) for family, mids in self.all_by_family.items()}

    def _load_declared_runtime_classes(self):
        """Expose the owner's exact training classes for legacy __main__ pickles.

        This hook only loads real classes supplied by the user/training release.
        It never creates a fake FastPreprocessor/SelfLearningEnsemble replacement.
        """
        module_spec = getattr(config, 'MODEL_RUNTIME_MODULE', '')
        class_names = getattr(config, 'MODEL_RUNTIME_CLASSES', ())
        if not module_spec:
            # Try explicit runtime files commonly shipped beside a release.
            candidates = []
            for base in (Path(config.ML_MODEL_PATH), project_root, Path(config.ML_MODEL_PATH).parent):
                for name in ('model_runtime.py', 'training_runtime.py', 'training.py', 'model_classes.py'):
                    p = base / name
                    if p.exists():
                        candidates.append(str(p))
            if candidates:
                module_spec = candidates[0]
        if not module_spec:
            return
        try:
            import importlib
            import importlib.util
            import sys
            if str(module_spec).lower().endswith('.py') and Path(module_spec).exists():
                path = Path(module_spec).expanduser().resolve()
                spec = importlib.util.spec_from_file_location('synapsepm_model_runtime', str(path))
                if spec is None or spec.loader is None:
                    raise ImportError(f'Cannot import runtime module: {path}')
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
            else:
                module = importlib.import_module(module_spec)
            main_mod = sys.modules.get('__main__')
            loaded, missing = [], []
            for name in class_names:
                obj = getattr(module, name, None)
                if obj is None:
                    missing.append(name)
                else:
                    if main_mod is not None:
                        setattr(main_mod, name, obj)
                    globals()[name] = obj
                    loaded.append(name)
            if loaded:
                logger.info('ML runtime compatibility classes loaded: %s', ', '.join(loaded))
            if missing:
                logger.warning('Runtime module %s does not define: %s', module_spec, ', '.join(missing))
        except Exception as exc:
            logger.warning('ML runtime compatibility module failed: %s', exc)

    def _load_pickle(self, path):
        if not JOBLIB_AVAILABLE:
            raise RuntimeError('joblib is required for pickle model artifacts')
        errors = []
        try:
            return joblib.load(path)
        except Exception as exc:
            errors.append(f'joblib: {type(exc).__name__}: {exc}')
        try:
            import pickle
            with open(path, 'rb') as fh:
                return pickle.load(fh)
        except Exception as exc:
            errors.append(f'pickle: {type(exc).__name__}: {exc}')
        raise RuntimeError(' | '.join(errors))

    def _load_bundle_object(self, path):
        if not path:
            return None
        return self._load_pickle(path)

    def _record_load_failure(self, info, exc):
        msg = f'{type(exc).__name__}: {exc}'
        info['load_error'] = msg[:4000]
        low = msg.lower()
        if '__main__' in low or 'fastpreprocessor' in low or 'selflearningensemble' in low:
            info['load_status'] = 'requires_training_module'
            info['quarantined_reason'] = 'Serialized artifact references a training-only Python class. Supply the exact training module via MODEL_RUNTIME_MODULE or export the model portably.'
        elif 'bitgenerator' in low or 'mt19937' in low or 'numpy.random' in low:
            info['load_status'] = 'requires_compatible_numpy'
            info['quarantined_reason'] = 'Serialized NumPy random state is incompatible with the current runtime.'
        else:
            info['load_status'] = 'deserialization_failed'
            info['quarantined_reason'] = 'Artifact could not be deserialized by the current production runtime.'

    def _artifact_contract(self, info):
        model = info.get('model')
        pre = info.get('preprocessor')
        fe = info.get('feature_engineer')
        metadata = info.get('metadata') or {}

        for obj, source in ((fe, 'feature_engineer'), (pre, 'preprocessor'), (model, 'model')):
            if obj is None:
                continue
            for attr in ('feature_names_in_', 'feature_names', 'input_features', 'columns'):
                names = getattr(obj, attr, None)
                if names is None:
                    continue
                try:
                    vals = [self._norm(x) for x in list(names)]
                except Exception:
                    continue
                if vals:
                    if source == 'feature_engineer' and not info.get('raw_features'):
                        info['raw_features'] = vals
                        info['features'] = vals
                    elif source != 'feature_engineer' and not info.get('features'):
                        info['features'] = vals
                    info['contract_source'] = f'{source}.{attr}'
                    break

        expected = None
        for obj in (pre, model):
            if obj is not None:
                expected = getattr(obj, 'n_features_in_', None)
                if expected is not None:
                    break
        if expected is None:
            expected = metadata.get('feature_count') or len(info.get('engineered_features') or []) or len(info.get('features') or [])
        try:
            info['feature_count'] = int(expected or 0)
        except Exception:
            info['feature_count'] = 0

        # A wrapper with its own scaler/feature_names is expected to transform raw input itself.
        if model is not None and (hasattr(model, 'feature_names') or hasattr(model, 'scaler')):
            if hasattr(model, 'predict') and hasattr(model, 'scaler'):
                info['preprocessing_owned_by_model'] = True
        return info

    def _family_bundle(self, family):
        if family in self._family_cache:
            return self._family_cache[family]
        mids = self.all_by_family.get(family) or []
        if not mids:
            raise ModelCompatibilityError(f'UNKNOWN_DATASET_FAMILY: {family}')
        first = self.models[mids[0]]
        bundle = {
            'preprocessor': None,
            'feature_engineer': None,
            'preprocessor_path': first.get('preprocessor_path'),
            'feature_engineer_path': first.get('feature_engineer_path'),
            'error': None,
        }
        try:
            if bundle['feature_engineer_path']:
                bundle['feature_engineer'] = self._load_bundle_object(bundle['feature_engineer_path'])
            if bundle['preprocessor_path']:
                bundle['preprocessor'] = self._load_bundle_object(bundle['preprocessor_path'])
        except Exception as exc:
            bundle['error'] = f'{type(exc).__name__}: {exc}'
            # Do not cache a broken bundle permanently; another request may run after
            # the runtime module/environment is corrected.
            raise ModelCompatibilityError(
                f'FAMILY_BUNDLE_LOAD_FAILED: family={family}; {bundle["error"]}'
            )
        self._family_cache[family] = bundle
        return bundle

    def load_model(self, mid):
        with self._lock:
            if mid not in self.models:
                raise ModelCompatibilityError(f'MODEL_NOT_REGISTERED: {mid}')
            if mid in self._model_cache:
                self.cache_hits += 1
                self._model_cache.move_to_end(mid)
                return self._model_cache[mid]
            self.cache_misses += 1
            info = self.models[mid]
            path = Path(info['model_path'])
            if not path.exists():
                info['load_status'] = 'missing'
                raise ModelCompatibilityError(f'MODEL_MISSING: {path}')
            if info.get('quarantined'):
                raise ModelCompatibilityError(f'MODEL_QUARANTINED: {mid}: {info.get("load_status")}')
            if path.stat().st_size > config.MAX_MODEL_FILE_MB * 1024 * 1024:
                info['load_status'] = 'too_large'
                raise ModelCompatibilityError(f'MODEL_TOO_LARGE: {path.name}')
            if config.MODEL_CHECKSUM_REQUIRED and info.get('checksum'):
                current = hashlib.sha256(path.read_bytes()).hexdigest()
                if not hmac.compare_digest(current, info['checksum']):
                    info['load_status'] = 'checksum_changed'
                    info['quarantined'] = True
                    raise ModelCompatibilityError(f'MODEL_CHECKSUM_CHANGED: {mid}')

            try:
                family = info['family']
                bundle = self._family_bundle(family)
                if info['framework'] == 'pickle':
                    model = self._load_pickle(path)
                elif info['framework'] == 'pytorch':
                    if not PYTORCH_AVAILABLE:
                        raise RuntimeError('PyTorch unavailable')
                    model = torch.load(path, map_location=self.device, weights_only=False)
                    if hasattr(model, 'eval'):
                        model.eval()
                elif info['framework'] == 'tensorflow':
                    if not TENSORFLOW_AVAILABLE:
                        raise RuntimeError('TensorFlow unavailable')
                    model = tf.keras.models.load_model(path, compile=False)
                elif info['framework'] == 'onnx':
                    if not ONNXRUNTIME_AVAILABLE:
                        raise RuntimeError('onnxruntime unavailable')
                    providers = ['CPUExecutionProvider']
                    if config.ML_USE_GPU and 'CUDAExecutionProvider' in ort.get_available_providers():
                        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                    model = ort.InferenceSession(str(path), providers=providers)
                else:
                    raise RuntimeError(f'Unsupported framework: {info["framework"]}')

                info['model'] = model
                info['feature_engineer'] = bundle.get('feature_engineer')
                info['preprocessor'] = bundle.get('preprocessor')
                self._artifact_contract(info)
                info['loaded'] = True
                info['load_status'] = 'loaded'
                info['checksum_status'] = 'verified' if info.get('checksum') else 'not_provided'
                self._model_cache[mid] = info
                self._model_cache.move_to_end(mid)
                while len(self._model_cache) > config.MODEL_CACHE_SIZE:
                    old_mid, old = self._model_cache.popitem(last=False)
                    old['model'] = None
                    old['preprocessor'] = None
                    old['feature_engineer'] = None
                    old['loaded'] = False
                    self.cache_evictions += 1
                return info
            except ModelCompatibilityError:
                raise
            except Exception as exc:
                self._record_load_failure(info, exc)
                info['model'] = None
                info['loaded'] = False
                raise ModelCompatibilityError(
                    f'MODEL_DESERIALIZATION_FAILED: {info.get("quarantined_reason", str(exc))}; raw={info.get("load_error", str(exc))[:1200]}'
                )

    def _select_champions(self):
        self.production_ids = []
        self.by_family = {}
        for family, mids in self.all_by_family.items():
            scored = [(mid, self._champion_score(self.models[mid])) for mid in mids]
            valid = [(mid, score) for mid, score in scored if score > float('-inf')]
            if not valid:
                logger.warning('Family %s has no production-validated models; prediction will abstain for this family.', family)
                self.by_family[family] = []
                continue
            valid.sort(key=lambda item: item[1], reverse=True)
            self.by_family[family] = [mid for mid, _ in valid[:config.MODEL_MAX_PRODUCTION]]
            self.production_ids.extend(self.by_family[family])
        logger.info('Per-family champion selection: %d families / %d candidate models',
                    len(self.by_family), len(self.production_ids))
        if not self.production_ids and config.MODEL_REQUIRE_VALIDATED:
            logger.error('ZERO production-validated models registered; predictions will abstain until a validated artifact is deployed.')

    def _champion_score(self, info):
        metrics = info.get('metrics') or {}
        # Metrics may be genuine trainer outputs, but they are not independently
        # verified by the serving application. Production selection therefore
        # requires an explicit validation declaration.
        if config.MODEL_REQUIRE_VALIDATED and not info.get('validated'):
            return float('-inf')
        score = 0.0
        has = False
        try:
            if metrics.get('r2') is not None:
                score += float(metrics['r2']) * 100.0
                has = True
        except Exception:
            pass
        for key, weight in (('mae', -0.05), ('rmse', -0.02)):
            try:
                if metrics.get(key) is not None:
                    score += float(metrics[key]) * weight
                    has = True
            except Exception:
                pass
        if metrics.get('accuracy') is not None:
            try:
                score += float(metrics['accuracy']) * 100.0
                has = True
            except Exception:
                pass
        # A production candidate with no reported metrics is NOT eligible.
        # Returning -inf ensures _select_champions() drops it from by_family.
        return score if has else float('-inf')

    def _metric_sort_score(self, info):
        return self._champion_score(info)

    def list_models(self):
        return list(self.production_ids)

    def list_all_registered(self):
        return list(self.models.keys())

    def get_model_info(self, mid):
        return self.models.get(mid)

    def _candidate_numeric_columns(self, df):
        excluded = set(TARGET_LEAKAGE_COLUMNS) | {
            'id', 'row_id', 'machine_id', 'unit_id', 'asset_id', 'engine_id',
            'equipment_id', 'time', 'timestamp', 'datetime', 'date', 'cycle',
            'time_cycles', 'condition', 'condition_label', 'maintenance_event',
        }
        return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and self._norm(c) not in excluded]

    def _fingerprint_score(self, incoming, expected):
        incoming = {self._canonical_feature(x) for x in incoming}
        expected = {self._canonical_feature(x) for x in expected}
        if not expected:
            return 0.0
        overlap = len(incoming & expected)
        coverage = overlap / max(1, len(expected))
        precision = overlap / max(1, len(incoming))
        return 0.70 * coverage + 0.30 * precision

    def _rank_families(self, dataframe, dataset_hint=None):
        if dataframe is None or dataframe.empty:
            return []
        incoming = [c for c in dataframe.columns if self._norm(c) not in TARGET_LEAKAGE_COLUMNS]
        numeric_count = len(self._candidate_numeric_columns(dataframe))
        hint = self._norm(dataset_hint) if dataset_hint else ''
        rows = []
        for family, mids in self.all_by_family.items():
            expected = set()
            counts = []
            for mid in mids:
                info = self.models[mid]
                expected.update(info.get('raw_features') or info.get('features') or [])
                if info.get('feature_count'):
                    counts.append(int(info['feature_count']))
            score = self._fingerprint_score(incoming, expected)
            if hint:
                fn = self._norm(family)
                if fn == hint:
                    score += 1.0
                elif hint in fn or fn in hint:
                    score += 0.60
            if numeric_count and counts:
                if numeric_count in counts:
                    score += 0.10
                else:
                    distance = min(abs(numeric_count - c) for c in counts)
                    if distance == 1:
                        score += 0.02
            rows.append((float(score), family))
        rows.sort(key=lambda x: (x[0], self._norm(x[1])), reverse=True)
        return rows

    def identify_family(self, df, hint=None):
        ranked = self._rank_families(df, hint)
        if not ranked:
            raise ModelCompatibilityError('NO_TRAINED_FAMILIES: no trained model family is registered.')
        if ranked[0][0] <= 0:
            # Do not fail merely because metadata has no feature names. The prediction
            # path will test every real family bundle against the actual transformers.
            return ranked[0][1], 0.0, ranked[:5]
        return ranked[0][1], float(ranked[0][0]), ranked[:5]

    def _df_from_records(self, machine, sensor_data):
        rows = []
        for s in list(sensor_data or []):
            row = dict(getattr(s, 'readings', {}) or {})
            row.update({'temperature': s.temperature, 'vibration': s.vibration, 'pressure': s.pressure})
            rows.append(row)
        if not rows:
            md = getattr(machine, 'machine_data', {}) or {}
            latest = md.get('latest_readings') or md.get('readings') or {}
            row = dict(latest) if isinstance(latest, dict) else {}
            row.setdefault('temperature', getattr(machine, 'temperature', None))
            row.setdefault('vibration', getattr(machine, 'vibration', None))
            row.setdefault('pressure', getattr(machine, 'pressure', None))
            rows.append(row)
        return pd.DataFrame(rows)

    def _map_required(self, df, required):
        lookup = {self._norm(c): c for c in df.columns}
        mapped, provenance, missing = {}, {}, []
        for f in required:
            fn = self._norm(f)
            if fn in lookup and pd.api.types.is_numeric_dtype(df[lookup[fn]]):
                mapped[fn] = lookup[fn]
                provenance[fn] = {'source_column': lookup[fn], 'conversion': None}
                continue
            candidates = []
            sem = self._canonical_feature(fn)
            for c in df.columns:
                if pd.api.types.is_numeric_dtype(df[c]) and self._canonical_feature(c) == sem:
                    candidates.append(c)
            if len(candidates) == 1:
                mapped[fn] = candidates[0]
                provenance[fn] = {'source_column': candidates[0], 'conversion': None}
            elif len(candidates) > 1:
                # Prefer exact normalized name if one exists; otherwise ambiguous.
                exact = [c for c in candidates if self._norm(c) == fn]
                if len(exact) == 1:
                    mapped[fn] = exact[0]
                    provenance[fn] = {'source_column': exact[0], 'conversion': None}
                else:
                    missing.append(f'{fn} (ambiguous={candidates})')
            else:
                missing.append(fn)
        return mapped, provenance, missing

    def _raw_dataframe_for_family(self, df, info):
        raw_features = info.get('raw_features') or []
        if not raw_features:
            return df.copy(), {self._norm(c): c for c in df.columns}
        mapped, provenance, missing = self._map_required(df, raw_features)
        if missing:
            raise ModelCompatibilityError(
                f'RAW_SCHEMA_MISMATCH: family={info.get("family")}; missing={missing}; '
                f'available={[self._norm(c) for c in df.columns]}'
            )
        ordered = []
        for feature in raw_features:
            src = mapped[self._norm(feature)]
            series, prov = _convert_unit_series(df[src], src, feature)
            ordered.append(series.rename(self._norm(feature)))
            provenance[self._norm(feature)] = prov
        out = pd.concat(ordered, axis=1)
        return out, provenance

    def _apply_transform(self, transformer, X, name):
        if transformer is None:
            return X
        if not hasattr(transformer, 'transform'):
            raise ModelCompatibilityError(f'{name}_TRANSFORM_UNAVAILABLE')
        last_error = None
        attempts = []
        # Match the fitted contract to avoid sklearn's feature-name warning and,
        # more importantly, avoid silently changing the training schema.
        if isinstance(X, pd.DataFrame):
            if getattr(transformer, 'feature_names_in_', None) is not None:
                attempts.append(X)
                try:
                    attempts.append(X.to_numpy(dtype='float32'))
                except Exception:
                    pass
            else:
                try:
                    attempts.append(X.to_numpy(dtype='float32'))
                except Exception:
                    pass
                attempts.append(X)
        elif isinstance(X, np.ndarray):
            try:
                attempts.append(pd.DataFrame(X))
            except Exception:
                pass
        for candidate in attempts:
            try:
                out = transformer.transform(candidate)
                if isinstance(out, tuple):
                    out = out[0]
                if hasattr(out, 'toarray'):
                    out = out.toarray()
                return out
            except Exception as exc:
                last_error = exc
        raise ModelCompatibilityError(f'{name}_TRANSFORM_FAILED: {type(last_error).__name__}: {last_error}')

    def _prepare_for_model(self, dataframe, info):
        raw_df, provenance = self._raw_dataframe_for_family(dataframe, info)
        raw_clean = raw_df.replace([np.inf, -np.inf], np.nan).dropna(axis=0, how='any')
        if raw_clean.empty:
            raise ModelCompatibilityError('LOW_SENSOR_QUALITY: no complete numeric rows after cleaning.')
        if len(raw_clean) < int(info.get('sequence_length') or 1):
            raise ModelCompatibilityError(
                f'INSUFFICIENT_HISTORY: sequence_length={int(info.get("sequence_length") or 1)}, rows={len(raw_clean)}'
            )

        # If the model explicitly owns preprocessing, pass its raw schema directly.
        if info.get('preprocessing_owned_by_model'):
            X = raw_clean.to_numpy(dtype='float32')
            return X, [self._norm(c) for c in raw_clean.columns], provenance

        X = raw_clean
        if info.get('feature_engineer') is not None:
            X = self._apply_transform(info['feature_engineer'], X, 'FEATURE_ENGINEER')
        if info.get('preprocessor') is not None:
            X = self._apply_transform(info['preprocessor'], X, 'PREPROCESSOR')
        if hasattr(X, 'toarray'):
            X = X.toarray()
        X = np.asarray(X, dtype='float32')
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if X.ndim != 2:
            raise ModelCompatibilityError(f'FEATURE_MATRIX_INVALID: got shape={X.shape}')

        expected = int(info.get('feature_count') or 0)
        # feature_count in a family bundle often refers to raw features. If the
        # transformed artifact exposes n_features_in_, prefer that exact contract.
        transformed_expected = getattr(info.get('model'), 'n_features_in_', None)
        if transformed_expected is not None:
            expected_model = int(transformed_expected)
            if X.shape[1] != expected_model:
                raise ModelCompatibilityError(
                    f'MODEL_INPUT_MISMATCH: transformed_features={X.shape[1]}, model_requires={expected_model}'
                )
        elif expected and not info.get('feature_engineer') and not info.get('preprocessor') and X.shape[1] != expected:
            raise ModelCompatibilityError(
                f'FEATURE_COUNT_MISMATCH: input={X.shape[1]}, model={expected}; refusing padding/truncation.'
            )
        return X, list(info.get('engineered_features') or info.get('features') or []), provenance

    def _prep_matrix(self, df, info, diagnostics=False):
        X, features, provenance = self._prepare_for_model(df, info)
        if diagnostics:
            return X, features, {
                'expected_features': int(info.get('feature_count') or X.shape[1]),
                'used_features': features,
                'input_columns': [self._norm(c) for c in df.columns],
                'provenance': provenance,
            }
        return X, features

    def _predict_array(self, X, info):
        model = info.get('model')
        if model is None:
            raise ModelCompatibilityError('MODEL_NOT_LOADED')
        seq = max(1, int(info.get('sequence_length') or 1))
        fw = info.get('framework')
        if fw == 'pickle':
            if seq > 1:
                if len(X) < seq:
                    raise ModelCompatibilityError(f'INSUFFICIENT_HISTORY: need {seq} rows')
                pred_input = X[-seq:]
                # sklearn estimators expect 2-D, while sequence models often expose 3-D.
                if getattr(model, 'expects_sequence', False):
                    pred_input = pred_input[None, ...]
            else:
                pred_input = X
            return np.asarray(model.predict(pred_input)).reshape(-1)
        arr = X[-seq:][None, ...] if seq > 1 else X
        if fw == 'pytorch':
            with torch.no_grad():
                out = model(torch.from_numpy(arr.astype('float32')).to(self.device))
                if isinstance(out, (tuple, list)):
                    out = out[0]
                return out.detach().cpu().numpy().reshape(-1)
        if fw == 'tensorflow':
            out = model.predict(arr.astype('float32'), verbose=0)
            if isinstance(out, (tuple, list)):
                out = out[0]
            return np.asarray(out).reshape(-1)
        if fw == 'onnx':
            inputs = model.get_inputs()
            if not inputs:
                raise ModelCompatibilityError('ONNX_NO_INPUTS')
            out = model.run(None, {inputs[0].name: arr.astype('float32')})
            return np.asarray(out[0]).reshape(-1)
        raise ModelCompatibilityError(f'UNSUPPORTED_FRAMEWORK: {fw}')

    def _ood_flags(self, df, info, provenance):
        if not config.OOD_P01_P99:
            return []
        ranges = info.get('training_ranges') or {}
        if not isinstance(ranges, dict):
            return []
        flags = []
        for feature, r in ranges.items():
            if not isinstance(r, dict):
                continue
            src = provenance.get(self._norm(feature), {}).get('source_column') or provenance.get(feature, {}).get('source_column')
            if not src or src not in df.columns:
                continue
            try:
                value = float(pd.to_numeric(df[src], errors='coerce').dropna().iloc[-1])
            except Exception:
                continue
            lo = r.get('p01', r.get('min'))
            hi = r.get('p99', r.get('max'))
            try:
                if lo is not None and value < float(lo): flags.append(f'{self._norm(feature)}_below_training_range')
                if hi is not None and value > float(hi): flags.append(f'{self._norm(feature)}_above_training_range')
            except Exception:
                continue
        return flags

    def _algorithm_rank(self, mids):
        return sorted(
            mids,
            key=lambda mid: (self._metric_sort_score(self.models[mid]), self._norm(self.models[mid].get('algorithm'))),
            reverse=True
        )

    def _prediction_confidence(self, info, family_score, ood):
        metrics = info.get('metrics') or {}
        # Never invent a percentage from the family matcher. Only expose an actual
        # confidence value supplied by the artifact/metadata. Otherwise use null.
        for key in ('confidence', 'confidence_score', 'prediction_confidence'):
            try:
                if metrics.get(key) is not None:
                    return float(metrics[key]), f'metrics.{key}'
            except Exception:
                pass
        md = info.get('metadata') or {}
        for key in ('confidence', 'confidence_score', 'prediction_confidence'):
            try:
                if md.get(key) is not None:
                    return float(md[key]), f'metadata.{key}'
            except Exception:
                pass
        return None, 'not_provided'

    def _risk(self, rul):
        if rul < 24: return 'critical'
        if rul < 72: return 'warning'
        if rul < 168: return 'medium'
        return 'low'

    def _recommend(self, rul):
        if rul < 24:
            return ['Schedule emergency maintenance within 24 hours', 'Reduce machine load to minimum immediately', 'Notify maintenance team and prepare spare parts', 'Isolate machine from critical production line']
        if rul < 72:
            return ['Schedule maintenance within 3 days', 'Increase monitoring frequency to hourly', 'Inspect bearings, belts, and lubrication']
        if rul < 168:
            return ['Plan maintenance within the week', 'Monitor temperature and vibration trends']
        return ['Continue normal operation', 'Maintain standard PM schedule']

    def predict(self, machine, sensor_data, model_type=None, dataframe=None, dataset_hint=None):
        request_id = getattr(g, 'request_id', None) or request.headers.get('X-Request-ID') or str(uuid.uuid4())
        if not self.production_ids:
            raise ModelCompatibilityError('NO_PRODUCTION_MODELS: no production-eligible trained model is deployed.')
        if dataframe is None:
            dataframe = self._df_from_records(machine, sensor_data)
        if dataframe is None or dataframe.empty:
            raise ModelCompatibilityError('EMPTY_DATASET: no sensor readings are available for this machine or dataset. Enter a manual reading or configure real telemetry before running prediction.')
        dataframe = dataframe.copy()

        leakage = check_target_leakage(dataframe)
        if leakage:
            raise ModelCompatibilityError(f'TARGET_LEAKAGE: {leakage}. Remove ground-truth columns before prediction, or use /api/v1/predictions/evaluate to compare against ground truth.')
        quality, quality_flags = assess_sensor_quality(dataframe)
        if quality < config.MIN_SENSOR_QUALITY:
            raise ModelCompatibilityError(f'LOW_SENSOR_QUALITY: score={quality:.3f}; flags={quality_flags}')

        ranked = self._rank_families(dataframe, dataset_hint)
        if not ranked:
            raise ModelCompatibilityError('NO_TRAINED_FAMILIES')
        preferred_family = ranked[0][1]
        family_score = float(ranked[0][0])
        family_candidates = [{'family': f, 'score': float(s)} for s, f in ranked[:10]]

        # Never force a family from a weak fingerprint. Try every family, ordered by
        # fingerprint score, and let the actual feature engineer/preprocessor/model
        # contract decide compatibility.
        family_order = [f for _, f in ranked]
        attempts = []
        compatible = []
        model_type_norm = self._norm(model_type) if model_type else ''

        for family in family_order:
            candidate_ids = self.by_family.get(family, []) if config.MODEL_REQUIRE_VALIDATED else self.all_by_family.get(family, [])
            mids = self._algorithm_rank(candidate_ids)
            if model_type_norm and model_type_norm != 'auto':
                preferred = [m for m in mids if model_type_norm in self._norm(self.models[m].get('algorithm', ''))]
                mids = preferred + [m for m in mids if m not in preferred]
            for mid in mids:
                info = self.models[mid]
                try:
                    loaded = self.load_model(mid)
                    X, used_features, provenance = self._prepare_for_model(dataframe, loaded)
                    ood = self._ood_flags(dataframe, loaded, provenance)
                    compatible.append({
                        'mid': mid, 'info': loaded, 'X': X,
                        'features': used_features, 'provenance': provenance,
                        'ood': ood, 'family': family,
                        'family_score': next((float(s) for s, f in ranked if f == family), 0.0)
                    })
                    attempts.append({'model_id': mid, 'family': family, 'algorithm': info.get('algorithm'), 'status': 'compatible'})
                except Exception as exc:
                    attempts.append({'model_id': mid, 'family': family, 'algorithm': info.get('algorithm'), 'status': 'failed', 'reason': str(exc)[:1200]})

        if not compatible:
            summary = {
                'code': 'NO_COMPATIBLE_MODEL',
                'registered_models': len(self.models),
                'registered_families': len(self.all_by_family),
                'incoming_columns': [self._norm(c) for c in dataframe.columns],
                'family_ranking': family_candidates,
                'closest_family_expected_features': (
                    self.models[self.all_by_family.get(family_order[0], [None])[0]].get('features')
                    if family_order and self.all_by_family.get(family_order[0]) and self.all_by_family[family_order[0]][0] in self.models
                    else None
                ),
                'attempts': attempts[:100],
            }
            raise ModelCompatibilityError(json.dumps(summary, separators=(',', ':')))

        # Among compatible candidates, select the highest validated metric score. The
        # family score is only a tie-breaker, never a fabricated quality metric.
        compatible.sort(key=lambda x: (self._metric_sort_score(x['info']), x['family_score']), reverse=True)
        chosen = compatible[0]
        info = chosen['info']
        preds = self._predict_array(chosen['X'], info)
        if len(preds) == 0:
            raise ModelCompatibilityError(f'MODEL_INVALID_OUTPUT: {chosen["mid"]} returned an empty output')
        try:
            raw_value = float(preds[-1])
        except (TypeError, ValueError, OverflowError):
            raise ModelCompatibilityError(f'MODEL_INVALID_OUTPUT: {chosen["mid"]} returned a non-numeric value')
        if not np.isfinite(raw_value):
            raise ModelCompatibilityError(f'MODEL_INVALID_OUTPUT: {chosen["mid"]} returned a non-finite value')
        if raw_value < 0:
            raise ModelCompatibilityError(f'MODEL_INVALID_OUTPUT: {chosen["mid"]} returned negative RUL')
        rul = raw_value

        metrics = info.get('metrics') or {}
        md = info.get('metadata') or {}
        try:
            rmse = float(metrics.get('rmse')) if metrics.get('rmse') is not None else None
        except Exception:
            rmse = None
        lower = max(0.0, rul - 1.96 * rmse) if rmse and rmse > 0 else None
        upper = rul + 1.96 * rmse if rmse and rmse > 0 else None
        confidence, confidence_source = self._prediction_confidence(info, chosen['family_score'], chosen['ood'])
        logger.info('Prediction served: request_id=%s model=%s family=%s algorithm=%s rul=%.2f confidence=%s trust=%s',
                    request_id, chosen['mid'], chosen['family'], info.get('algorithm'), rul,
                    f'{confidence:.2f}%' if confidence is not None else 'null',
                    'HIGH' if chosen['family_score'] >= 0.8 and not chosen['ood'] else 'MEDIUM')

        return {
            'schema_version': config.PREDICTION_SCHEMA_VERSION,
            'request_id': request_id,
            'rul_hours': rul,
            'rul_value': rul,
            'rul_unit': str(md.get('rul_unit') or md.get('target_unit') or 'hours'),
            'confidence': confidence if confidence is not None else None,
            'confidence_source': confidence_source,
            'status': _prediction_status(rul),
            'prediction_status': 'success',
            'model_id': chosen['mid'],
            'model_type': info.get('model_type') or info.get('algorithm'),
            'model_version': info.get('version'),
            'dataset_family': chosen['family'],
            'family_score': chosen['family_score'],
            'family_candidates': family_candidates,
            'features_used': chosen['features'],
            'feature_provenance': chosen['provenance'],
            'data_points': int(len(dataframe)),
            'sequence_length': int(info.get('sequence_length') or 1),
            'recommendations': self._recommend(rul),
            'risk_level': self._risk(rul),
            'risk_score': max(0.0, min(100.0, 100.0 - rul / 168.0 * 100.0)),
            'failure_probability': max(0.0, min(100.0, 100.0 - rul / 168.0 * 100.0)),
            'risk_derivation': 'derived_from_predicted_rul',
            'uncertainty_lower': lower,
            'uncertainty_upper': upper,
            'uncertainty_source': 'metrics.rmse_95pct_approximation' if lower is not None else 'not_provided',
            'sensor_quality': quality,
            'sensor_quality_flags': quality_flags,
            'ood_flags': chosen['ood'],
            'prediction_trust': 'HIGH' if chosen['family_score'] >= 0.8 and not chosen['ood'] else ('MEDIUM' if chosen['family_score'] >= 0.5 else 'LOW'),
            'fallback': False,
            'model_selection_audit': {
                'selection_mode': 'automatic_family_fingerprint_then_validated_metrics',
                'preferred_family': preferred_family,
                'selected_family': chosen['family'],
                'family_score': chosen['family_score'],
                'algorithm_ranking': [
                    {'model_id': m, 'algorithm': self.models[m].get('algorithm'), 'metrics': self.models[m].get('metrics', {})}
                    for m in self._algorithm_rank(self.all_by_family.get(chosen['family'], []))
                ],
                'compatible_candidates': [x['mid'] for x in compatible],
                'selected_model': chosen['mid'],
                'attempts': attempts[:100],
            },
        }

    def predict_batch(self, machines, model_type=None):
        results = []
        for machine in machines:
            try:
                sd = (SensorData.query.filter_by(machine_id=machine.id)
                      .order_by(SensorData.created_at.asc()).limit(1000).all())
                result = self.predict(
                    machine, sd, model_type,
                    dataset_hint=((machine.machine_data or {}).get('dataset_family'))
                )
                result['machine_id'] = str(machine.id)
                result['machine_name'] = machine.name
                results.append(result)
            except Exception as exc:
                logger.exception('Batch prediction failed for %s', machine.id)
                results.append({
                    'machine_id': str(machine.id), 'machine_name': machine.name,
                    'prediction_status': 'abstained', 'error': str(exc)
                })
        return results

    def validate_all(self):
        """Explicitly validate every artifact; startup remains lazy."""
        results = []
        for mid in list(self.models):
            try:
                info = self.load_model(mid)
                results.append({'model_id': mid, 'family': info.get('family'), 'status': 'valid'})
            except Exception as exc:
                results.append({'model_id': mid, 'family': self.models[mid].get('family'), 'status': 'invalid', 'error': str(exc)})
        return results

    def _write_registry_snapshot(self, extracted=False, roots=None):
        try:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'schema_version': config.PREDICTION_SCHEMA_VERSION,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'extracted_release': bool(extracted),
                'roots': [str(x) for x in (roots or [])],
                'total_models': len(self.models),
                'total_families': len(self.all_by_family),
                'families': {
                    family: [
                        {
                            'model_id': mid,
                            'algorithm': self.models[mid].get('algorithm'),
                            'model_path': self.models[mid].get('model_path'),
                            'metrics': self.models[mid].get('metrics') or {},
                            'feature_count': self.models[mid].get('feature_count'),
                            'features': self.models[mid].get('features') or [],
                            'preprocessor_path': self.models[mid].get('preprocessor_path'),
                            'feature_engineer_path': self.models[mid].get('feature_engineer_path'),
                        }
                        for mid in mids if mid in self.models
                    ] for family, mids in self.all_by_family.items()
                }
            }
            self.registry_path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
        except Exception:
            logger.exception('Could not write model registry snapshot')


ml_engine = MLEngine()

# Startup smoke test: exercise model deserialization without preventing the web
# service from starting if an optional artifact is invalid. Real prediction
# endpoints still fail closed rather than substituting heuristic predictions.
def _hf_model_smoke_test():
    if not ml_engine.models:
        logger.error('NO MODELS LOADED — check HF_MODEL_REPO, HF_MODEL_FILENAME, HF_TOKEN and ML_MODEL_PATH.')
        return
    attempted = min(10, len(ml_engine.models))
    loaded, failed = 0, []
    for model_id in list(ml_engine.models)[:attempted]:
        try:
            ml_engine.load_model(model_id)
            loaded += 1
        except Exception as exc:
            failed.append((model_id, str(exc)[:200]))
    logger.info('Model smoke test: %s/%s registered models loaded', loaded, attempted)
    for model_id, error in failed:
        logger.warning('Model smoke test failed for %s: %s', model_id, error)

try:
    _hf_model_smoke_test()
except Exception:
    logger.exception('Model smoke test failed unexpectedly; app startup will continue.')


# ============================================================
# MODEL REGISTRY FACADE
# ============================================================

class ModelRegistry:
    """Admin/read-only facade over the production model registry."""
    def __init__(self, engine):
        self.engine = engine

    @property
    def by_family(self):
        return self.engine.by_family

    def snapshot(self):
        families = {}
        for family, mids in self.engine.by_family.items():
            families[family] = []
            for mid in mids:
                x = self.engine.models[mid]
                families[family].append({
                    'id': mid, 'model_type': x.get('model_type'), 'version': x.get('version'),
                    'framework': x.get('framework'), 'feature_count': x.get('feature_count'),
                    'features': x.get('features', []), 'validated': x.get('validated'),
                    'loaded': mid in self.engine._model_cache, 'quarantined': x.get('quarantined'),
                    'checksum_status': x.get('checksum_status'), 'metrics': x.get('metrics', {}),
                    'sequence_length': x.get('sequence_length')
                })
        return {
            'total_models': len(self.engine.models),
            'total_families': len(self.engine.by_family),
            'loaded_models': len(self.engine._model_cache),
            'quarantined_models': sum(1 for x in self.engine.models.values() if x.get('quarantined')),
            'cache_size': config.MODEL_CACHE_SIZE,
            'cache_hits': self.engine.cache_hits, 'cache_misses': self.engine.cache_misses,
            'cache_evictions': self.engine.cache_evictions,
            'families': families
        }

    def validate_all(self):
        results = []
        for mid, info in self.engine.models.items():
            try:
                self.engine.load_model(mid)
                results.append({'model_id': mid, 'status':'valid', 'family':info.get('family')})
            except Exception as e:
                results.append({'model_id': mid, 'status':'invalid', 'family':info.get('family'), 'error':str(e)})
        return results

    def reload(self):
        self.engine._init()
        return self.snapshot()

model_registry = ModelRegistry(ml_engine)



# ============================================================
# OAUTH SERVICE
# ============================================================

class OAuthService:
    def __init__(self):
        self.providers = {
            'google': {
                'client_id': config.GOOGLE_CLIENT_ID,
                'client_secret': config.GOOGLE_CLIENT_SECRET,
                'redirect_uri': config.GOOGLE_REDIRECT_URI,
                'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
                'token_url': 'https://oauth2.googleapis.com/token',
                'userinfo_url': 'https://www.googleapis.com/oauth2/v2/userinfo',
                'scope': 'email profile'
            },
            'github': {
                'client_id': config.GITHUB_CLIENT_ID,
                'client_secret': config.GITHUB_CLIENT_SECRET,
                'redirect_uri': config.GITHUB_REDIRECT_URI,
                'auth_url': 'https://github.com/login/oauth/authorize',
                'token_url': 'https://github.com/login/oauth/access_token',
                'userinfo_url': 'https://api.github.com/user',
                'scope': 'user:email'
            },
            'linkedin': {
                'client_id': config.LINKEDIN_CLIENT_ID,
                'client_secret': config.LINKEDIN_CLIENT_SECRET,
                'redirect_uri': config.LINKEDIN_REDIRECT_URI,
                'auth_url': 'https://www.linkedin.com/oauth/v2/authorization',
                'token_url': 'https://www.linkedin.com/oauth/v2/accessToken',
                'userinfo_url': 'https://api.linkedin.com/v2/userinfo',
                'scope': 'openid profile email'
            }
        }

    def get_authorization_url(self, provider):
        if provider not in self.providers:
            raise ValueError(f"Provider {provider} not supported")
        c = self.providers[provider]
        nonce = secrets.token_urlsafe(24)
        payload = f'{provider}:{nonce}'
        sig = hmac.new(config.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        state = f'{provider}.{nonce}.{sig}'
        if redis_client:
            redis_client.setex(f'oauth_state:{state}', 600, provider)
        params = {
            'client_id': c['client_id'],
            'redirect_uri': c['redirect_uri'],
            'response_type': 'code',
            'scope': c['scope'],
            'state': state
        }
        return f"{c['auth_url']}?{urlencode(params)}", state

    def verify_state(self, state):
        if not state:
            return False
        if redis_client:
            p = redis_client.get(f'oauth_state:{state}')
            if p:
                redis_client.delete(f'oauth_state:{state}')
                return p
        parts = str(state).split('.', 2)
        if len(parts) != 3:
            return False
        provider, nonce, sig = parts
        payload = f'{provider}:{nonce}'
        expected = hmac.new(config.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        return provider if hmac.compare_digest(sig, expected) and provider in self.providers else False

    def exchange_code(self, provider, code):
        if provider not in self.providers:
            raise ValueError(f"Provider {provider} not supported")
        if not REQUESTS_AVAILABLE:
            raise ImportError("Requests not available")
        c = self.providers[provider]
        td = {
            'code': code, 'client_id': c['client_id'],
            'client_secret': c['client_secret'],
            'redirect_uri': c['redirect_uri'],
            'grant_type': 'authorization_code'
        }
        r = requests.post(c['token_url'], data=td,
                          headers={'Accept': 'application/json'},
                          timeout=(5, 15))
        ti = r.json()
        if 'access_token' not in ti:
            raise ValueError("Failed to get access token")
        r = requests.get(c['userinfo_url'],
                         headers={'Authorization': f"Bearer {ti['access_token']}"},
                         timeout=(5, 15))
        return ti, r.json()

    def get_user_email(self, provider, ui):
        return ui.get('email')

    def create_or_update_user(self, provider, ui, ti):
        email = self.get_user_email(provider, ui)
        if not email and provider == 'github' and REQUESTS_AVAILABLE and ti.get('access_token'):
            try:
                r = requests.get(
                    'https://api.github.com/user/emails',
                    headers={'Authorization': f"Bearer {ti['access_token']}",
                             'Accept': 'application/vnd.github+json'},
                    timeout=(5, 10)
                )
                emails = r.json()
                primary = next((e.get('email') for e in emails
                                if e.get('primary') and e.get('verified')), None)
                email = primary or next((e.get('email') for e in emails
                                         if e.get('verified')), None)
            except Exception:
                logger.exception('GitHub email lookup failed')
        if not email:
            raise ValueError("Could not retrieve email")
        ps = ui.get('id') or ui.get('sub') or str(email)

        oa = OAuthAccount.query.filter_by(
            provider=provider, provider_subject=str(ps)
        ).first()
        if oa:
            oa.access_token = ti.get('access_token')
            oa.refresh_token = ti.get('refresh_token')
            oa.token_expires_at = datetime.now(timezone.utc) + \
                timedelta(seconds=ti.get('expires_in', 3600))
            oa.provider_email = email
            oa.provider_name = ui.get('name')
            oa.provider_picture = ui.get('picture') or ui.get('avatar_url')
            db.session.commit()
            u = db.session.get(User, oa.user_id)
            if u:
                return u, oa

        u = User.query.filter_by(email=email).first()
        if u:
            oa = OAuthAccount(
                user_id=u.id, provider=provider, provider_subject=str(ps),
                provider_email=email, provider_name=ui.get('name'),
                provider_picture=ui.get('picture') or ui.get('avatar_url'),
                access_token=ti.get('access_token'),
                refresh_token=ti.get('refresh_token'),
                token_expires_at=datetime.now(timezone.utc) +
                    timedelta(seconds=ti.get('expires_in', 3600))
            )
            db.session.add(oa)
            db.session.commit()
            return u, oa

        org = Organization(
            name=f"{ui.get('name', email)}'s Organization",
            slug=make_unique_org_slug(ui.get('name', email)),
            primary_email=email, plan='FREE', subscription_status='active',
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=config.TRIAL_DAYS)
        )
        db.session.add(org)
        db.session.flush()

        username = email.split('@')[0]
        c = 1
        while User.query.filter_by(username=username).first():
            username = f"{email.split('@')[0]}{c}"
            c += 1

        u = User(
            organization_id=org.id, username=username, email=email,
            first_name=ui.get('given_name', ''),
            last_name=ui.get('family_name', ''),
            display_name=ui.get('name', email), role='org_admin',
            is_active=True, is_verified=True, is_sso_user=True,
            sso_provider=provider, sso_id=str(ps),
            avatar_url=ui.get('picture') or ui.get('avatar_url'),
            password_hash=password_service.hash_password(
                secrets.token_urlsafe(16))[0],
            password_history=[]
        )
        db.session.add(u)
        db.session.flush()

        oa = OAuthAccount(
            user_id=u.id, provider=provider, provider_subject=str(ps),
            provider_email=email, provider_name=ui.get('name'),
            provider_picture=ui.get('picture') or ui.get('avatar_url'),
            access_token=ti.get('access_token'),
            refresh_token=ti.get('refresh_token'),
            token_expires_at=datetime.now(timezone.utc) +
                timedelta(seconds=ti.get('expires_in', 3600))
        )
        db.session.add(oa)
        db.session.commit()
        return u, oa


oauth_service = OAuthService()


# ============================================================
# PAYMENT PROCESSOR
# ============================================================

class PaymentProcessor:
    def __init__(self):
        self.gateways = {}
        self._init()

    def _init(self):
        if config.PADDLE_API_KEY and config.PADDLE_PRICE_IDS:
            self.gateways['paddle'] = {'env': config.PADDLE_ENV}
        # if config.KHALTI_SECRET_KEY and config.KHALTI_AMOUNTS:
        #     self.gateways['khalti'] = {'env': config.KHALTI_ENV}
        if not config.IS_PRODUCTION:
            self.gateways['mock'] = {'env': 'dev'}

    def get_gateways(self):
        return list(self.gateways.keys())

    def gateway_status(self):
        statuses = []
        if config.PADDLE_API_KEY and config.PADDLE_PRICE_IDS:
            key_ok = not config.PADDLE_API_KEY.startswith(('live_', 'test_'))
            statuses.append({
                'name': 'paddle', 'enabled': key_ok,
                'env': config.PADDLE_ENV,
                'reason': None if key_ok else
                    'PADDLE_API_KEY looks like a client token, not a server API key',
            })
        else:
            missing = []
            if not config.PADDLE_API_KEY:
                missing.append('PADDLE_API_KEY')
            if not config.PADDLE_PRICE_IDS:
                missing.append('PADDLE_PRICE_IDS_JSON')
            statuses.append({
                'name': 'paddle', 'enabled': False,
                'reason': f"missing: {', '.join(missing)}",
            })

        # if config.KHALTI_SECRET_KEY and config.KHALTI_AMOUNTS:
        #     statuses.append({
        #         'name': 'khalti', 'enabled': True,
        #         'env': config.KHALTI_ENV,
        #     })
        # else:
        #     missing = []
        #     if not config.KHALTI_SECRET_KEY:
        #         missing.append('KHALTI_SECRET_KEY')
        #     if not config.KHALTI_AMOUNTS:
        #         missing.append('KHALTI_AMOUNTS_JSON')
        #     statuses.append({
        #         'name': 'khalti', 'enabled': False,
        #         'reason': f"missing: {', '.join(missing)}",
        #     })

        if not config.IS_PRODUCTION:
            statuses.append({
                'name': 'mock', 'enabled': True,
                'reason': 'dev only',
            })

        return statuses

    def paddle_client_token(self):
        return config.PADDLE_CLIENT_TOKEN or ''

    def create_checkout(self, gateway, plan_id, user, org):
        if not config.IS_PRODUCTION and (gateway not in self.gateways or gateway == 'mock'):
            plan = config.PLANS.get(plan_id)
            if not plan or plan.get('is_custom'):
                return {'error': 'Invalid plan'}
            p = Payment(
                organization_id=org.id, gateway='mock',
                amount=float(plan['price'] or 0),
                currency=plan['currency'], plan_id=plan['id'],
                plan_name=plan['name'],
                status='pending', customer_email=user.email,
                customer_name=user.display_name or user.email,
                invoice_number=generate_invoice_number(),
                payment_data={'plan_id': plan_id, 'mock': True}
            )
            db.session.add(p)
            db.session.commit()
            self.activate(p, 'mock_' + p.uuid, None)
            if PAYMENTS:
                PAYMENTS.labels(gateway='mock', status='completed').inc()
            return {
                'checkout_url': f"{config.FRONTEND_URL}/payment-success?payment_id={p.uuid}&mock=1",
                'payment_id': p.uuid, 'plan_id': plan_id, 'gateway': 'mock'
            }

        if gateway not in self.gateways:
            return {
                'error': f'Gateway {gateway} not configured',
                'gateway_status': self.gateway_status(),
            }

        plan = config.PLANS.get(plan_id)
        if not plan or plan.get('is_custom'):
            return {'error': 'Invalid plan'}

        p = Payment(
            organization_id=org.id, gateway=gateway,
            amount=float(plan['price'] or 0),
            currency=plan['currency'], plan_id=plan['id'],
            plan_name=plan['name'],
            status='pending', customer_email=user.email,
            customer_name=user.display_name or user.email,
            invoice_number=generate_invoice_number(),
            payment_data={'plan_id': plan_id}
        )
        db.session.add(p)
        db.session.commit()

        try:
            if gateway == 'paddle':
                if not REQUESTS_AVAILABLE:
                    raise RuntimeError('requests required')
                price_id = config.PADDLE_PRICE_IDS.get(plan_id)
                if not price_id:
                    raise RuntimeError(f'Missing Paddle price for {plan_id}')
                base = ('https://sandbox-api.paddle.com'
                        if config.PADDLE_ENV == 'sandbox' else 'https://api.paddle.com')
                r = requests.post(
                    base + '/transactions',
                    headers={'Authorization': f'Bearer {config.PADDLE_API_KEY}',
                             'Content-Type': 'application/json'},
                    json={'items': [{'price_id': price_id, 'quantity': 1}],
                          'customer': {'email': user.email},
                          'custom_data': {'payment_id': p.uuid,
                                          'organization_id': org.id,
                                          'plan_id': plan_id,
                                          'user_id': user.id}},
                    timeout=(5, 20)
                )
                if r.status_code >= 400:
                    body = {}
                    try:
                        body = r.json()
                    except Exception:
                        body = {'raw': r.text[:500]}
                    logger.error(f'Paddle API error {r.status_code}: {body}')
                    err_detail = (body.get('error') or {}).get('detail') or str(body)[:300]
                    hint = ''
                    if r.status_code == 403 and 'authentication' in str(body).lower():
                        hint = (' Your PADDLE_API_KEY looks wrong. It must be the SERVER '
                                'API key from Paddle → Developer Tools → Authentication '
                                '(starts with pdl_live_apikey_ or pdl_sdbx_apikey_).')
                    p.status = 'failed'
                    p.payment_data = {**(p.payment_data or {}), 'gateway_error': body}
                    db.session.commit()
                    return {
                        'error': 'Paddle rejected the checkout request',
                        'detail': (err_detail + hint).strip(),
                        'status_code': r.status_code,
                        'payment_id': p.uuid,
                    }
                body = r.json().get('data', {}) or {}
                checkout = (body.get('checkout') or {}).get('url')
                if not checkout:
                    raise RuntimeError('Paddle no checkout URL')
                p.gateway_order_id = body.get('id')
                p.payment_data = {**(p.payment_data or {}),
                                  'paddle_transaction_id': body.get('id'),
                                  'price_id': price_id}
            # elif gateway == 'khalti':
            #     if not REQUESTS_AVAILABLE:
            #         raise RuntimeError('requests required')
            #     amount = int(config.KHALTI_AMOUNTS.get(plan_id, 0))
            #     if amount <= 0:
            #         raise RuntimeError(f'Missing Khalti amount for {plan_id}')
            #     base = ('https://dev.khalti.com/api/v2'
            #             if config.KHALTI_ENV != 'live' else 'https://khalti.com/api/v2')
            #     r = requests.post(
            #         base + '/epayment/initiate/',
            #         headers={'Authorization': f'Key {config.KHALTI_SECRET_KEY}',
            #                  'Content-Type': 'application/json'},
            #         json={'return_url': config.KHALTI_RETURN_URL,
            #               'website_url': config.FRONTEND_URL,
            #               'amount': str(amount),
            #               'purchase_order_id': p.uuid,
            #               'purchase_order_name': plan['name'],
            #               'customer_info': {
            #                   'name': user.display_name or user.email,
            #                   'email': user.email, 'phone': user.phone or ''
            #               }},
            #         timeout=(5, 20)
            #     )
            #     r.raise_for_status()
            #     body = r.json()
            #     checkout = body.get('payment_url')
            #     pidx = body.get('pidx')
            #     if not checkout or not pidx:
            #         raise RuntimeError('Khalti missing pidx/payment_url')
            #     p.gateway_order_id = pidx
            #     p.payment_data = {**(p.payment_data or {}),
            #                       'pidx': pidx,
            #                       'khalti_amount_paisa': amount}
            else:
                raise RuntimeError('Unsupported gateway')
            db.session.commit()
            return {'checkout_url': checkout, 'payment_id': p.uuid,
                    'plan_id': plan_id, 'gateway': gateway}
        except Exception as exc:
            db.session.rollback()
            logger.exception('Payment checkout failed')
            return {'error': 'Payment checkout could not be created',
                    'detail': str(exc)}

    def activate(self, payment, gateway_payment_id=None, subscription_id=None):
        payment.status = 'completed'
        payment.gateway_payment_id = gateway_payment_id or payment.gateway_payment_id
        payment.webhook_received_at = datetime.now(timezone.utc)
        org = db.session.get(Organization, payment.organization_id)
        if org:
            if subscription_id:
                org.subscription_id = str(subscription_id)
            org.subscription_status = 'active'
            org.plan = payment.plan_id.upper() if payment.plan_id else org.plan
            org.trial_ends_at = None
        db.session.commit()
        try:
            broadcast_both('billing_updated', {
                'payment': payment.to_dict(),
                'organization': org.to_dict() if org else None,
            }, org_id=org.id if org else None)
        except Exception:
            pass


payment_processor = PaymentProcessor()


# ============================================================
# ALERT ENUM COMPATIBILITY
# ============================================================
def _alert_severity_for_db(preferred):
    """Use the app's severity vocabulary, adapting only if a legacy PG enum remains."""
    preferred = str(preferred or 'low').lower()
    try:
        if db.engine.dialect.name != 'postgresql':
            return preferred
        row = db.session.execute(text("""
            SELECT data_type, udt_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='alerts' AND column_name='severity'
        """)).fetchone()
        if not row or row[0] != 'USER-DEFINED':
            return preferred
        labels = [str(x[0]).lower() for x in db.session.execute(text("""
            SELECT e.enumlabel FROM pg_type t
            JOIN pg_enum e ON e.enumtypid=t.oid
            WHERE t.typname=:type_name ORDER BY e.enumsortorder
        """), {'type_name': str(row[1])}).fetchall()]
        if not labels or preferred in labels:
            return preferred
        fallbacks = {
            'warning': ('medium', 'high', 'critical', 'low'),
            'critical': ('high', 'medium', 'warning', 'low'),
            'medium': ('warning', 'high', 'critical', 'low'),
            'high': ('critical', 'medium', 'warning', 'low'),
            'low': ('info', 'normal', 'medium', 'warning', 'high'),
        }
        return next((x for x in fallbacks.get(preferred, ()) if x in labels), labels[-1])
    except Exception:
        # Never allow a metadata lookup failure to prevent the main operation.
        logger.debug('Could not inspect legacy alert severity enum', exc_info=True)
        return preferred


# ============================================================
# AUTO ALERT ENGINE
# ============================================================

def _auto_alert(machine, prediction, result):
    try:
        if result.get('fallback') or result.get('prediction_status') == 'diagnostic':
            logger.info('Skipping auto-alert: diagnostic/fallback result is not a real ML prediction.')
            return None
        rul = float(result.get('rul_hours') or 0)
        if rul <= 0:
            return None
        risk = ('critical' if rul < 24 else
                'warning' if rul < 72 else
                'medium' if rul < 168 else 'low')
        if risk not in ('critical', 'warning'):
            return None
        severity = 'critical' if risk == 'critical' else 'warning'
        org_id = getattr(machine, 'organization_id', None)
        if not org_id:
            logger.error('Auto-alert skipped: machine has no organization_id')
            return None
        a = Alert(
            machine_id=machine.id,
            organization_id=org_id,
            title=f"{machine.name}: {risk.upper()} RUL — {rul:.1f}h",
            message=(f"RUL {rul:.1f}h | Model: {result.get('model_id')} | "
                     f"Confidence: {(result.get('confidence') if result.get('confidence') is not None else 'N/A')}"
                     f"{'%' if result.get('confidence') is not None else ''} | "
                     f"Risk: {risk}"),
            severity=_alert_severity_for_db(severity), category='prediction', source='ml_model',
            status='active', prediction_id=prediction.id,
            incident_id=f"PRED-{prediction.id}"
        )
        # Alert creation is optional and must never invalidate an already
        # committed prediction. The SAVEPOINT also handles legacy PostgreSQL
        # alert_severity enums that have not yet been migrated to VARCHAR.
        with db.session.begin_nested():
            db.session.add(a)
            db.session.flush()

            recipients = set()
            if machine.owner_id:
                recipients.add(machine.owner_id)
            for u in User.query.filter_by(
                organization_id=machine.organization_id,
                is_active=True
            ).filter(User.role.in_(['org_admin', 'super_admin'])).all():
                recipients.add(u.id)

            for uid in recipients:
                db.session.add(Notification(
                    user_id=uid, organization_id=machine.organization_id,
                    alert_id=a.id, title=a.title, message=a.message,
                    type='prediction_alert'
                ))
            db.session.flush()
        db.session.commit()

        try:
            broadcast_both('alert_created', {'alert': a.to_dict()},
                           org_id=machine.organization_id)
        except Exception:
            pass

        email_result = {'sent': False, 'reason': 'no_recipient'}
        try:
            owner = db.session.get(User, machine.owner_id) if machine.owner_id else None
            if not owner:
                owner = User.query.filter_by(
                    organization_id=machine.organization_id,
                    role='org_admin', is_active=True
                ).first()
            if owner and owner.email:
                if not os.environ.get('RESEND_API_KEY'):
                    email_result = {'sent': False, 'reason': 'suppressed',
                                    'recipient': owner.email}
                    logger.info(f"[EMAIL SUPPRESSED] would send to {owner.email}")
                else:
                    ok = send_email(
                        owner.email,
                        f"🚨 {severity.upper()} ALERT: {machine.name}",
                        f"""<div style="font-family:Arial;max-width:600px;">
                        <h2 style="color:{'#dc2626' if severity=='critical' else '#f59e0b'};">
                        ⚠️ {severity.upper()} RUL Alert</h2>
                        <p><strong>Machine:</strong> {machine.name}</p>
                        <p><strong>Location:</strong> {machine.location or 'N/A'}</p>
                        <p><strong>RUL:</strong> {rul:.1f} hours ({risk} risk)</p>
                        <p><strong>Model:</strong> {result.get('model_id')}</p>
                        <p><strong>Confidence:</strong> {((f"{float(result.get('confidence')):.1f}%") if result.get('confidence') is not None else 'N/A')}</p>
                        <p><strong>Recommendations:</strong></p>
                        <ul>{''.join(f'<li>{r}</li>' for r in result.get('recommendations', []))}</ul>
                        <p style="color:#64748b;font-size:12px;">
                        Automated alert from {config.APP_NAME}. Do not reply.</p>
                        </div>"""
                    )
                    email_result = {'sent': bool(ok),
                                    'reason': 'sent' if ok else 'smtp_error',
                                    'recipient': owner.email}
        except Exception as e:
            logger.exception('Alert email failed')
            email_result = {'sent': False, 'reason': str(e)}

        try:
            a.email_status = email_result
            db.session.commit()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.exception('Alert email-status persistence failed; alert itself remains optional')

        return a
    except Exception:
        # An alert is a side-effect of an already committed prediction. Never
        # allow an alert/schema failure to leave the SQLAlchemy session in
        # PendingRollbackError state or turn a valid prediction into HTTP 503.
        # begin_nested() rolls back only the alert savepoint on INSERT errors.
        # Avoid a full session rollback here: prediction rows are committed
        # before this best-effort side effect and must remain readable.
        logger.exception('Auto-alert failed; prediction remains valid')
        return None



# ============================================================
# PREDICTION PERSISTENCE / IDEMPOTENCY
# ============================================================

def _request_id():
    rid = getattr(g, 'request_id', None) or request.headers.get('X-Request-ID') or str(uuid.uuid4())
    rid = re.sub(r'[^A-Za-z0-9._:-]', '', str(rid))[:64]
    return rid or str(uuid.uuid4())

def _persist_prediction(machine, result, org_id, request_id=None, processing_ms=None,
                        source='unknown', user_id=None, source_filename=None):
    """Persist real-model outputs idempotently using a SAVEPOINT for race safety."""
    if not result.get('model_id') or not result.get('model_type') or str(result.get('model_type')).lower() in ('unknown', 'heuristic', 'fallback'):
        raise ModelCompatibilityError('MODEL_IDENTITY_REQUIRED: refusing to persist a prediction without a real trained model identifier.')
    if result.get('fallback') or result.get('prediction_status') == 'diagnostic':
        raise ModelCompatibilityError('DIAGNOSTIC_FALLBACK_DISABLED: only real trained-model predictions can be persisted.')
    rid = _request_id() if not request_id else str(request_id)[:64]
    existing = Prediction.query.filter_by(
        organization_id=str(org_id), request_id=rid
    ).first()
    if existing:
        return existing, True
    # Confidence is optional. If the model bundle does not publish a calibrated
    # confidence value, persist NULL rather than inventing confidence=0.
    _confidence = result.get('confidence')
    p = Prediction(
        request_id=rid,
        schema_version=result.get('schema_version', config.PREDICTION_SCHEMA_VERSION),
        machine_id=machine.id,
        organization_id=org_id,
        rul_hours=float(result['rul_hours']),
        confidence=(float(_confidence) if _confidence is not None else None),
        status=_prediction_status(result.get('rul_hours')),
        model_type=result.get('model_type', 'unknown'),
        model_version=result.get('model_version'),
        risk_level=result.get('risk_level'),
        risk_score=float(result.get('risk_score', 0)) if result.get('risk_score') is not None else None,
        feature_importance=result.get('feature_importance'),
        recommendations=result.get('recommendations', []),
        data_window=result.get('sequence_length'),
        data_points=result.get('data_points'),
        processing_time_ms=processing_ms,
        model_input=result.get('inputs_used'),
        model_output=result,
        prediction_data={
            'rul_value': result.get('rul_value'),
            'rul_unit': result.get('rul_unit')
        },
        feature_provenance=result.get('feature_provenance', {}),
        ood_flags=result.get('ood_flags', []),
        sensor_quality=result.get('sensor_quality'),
        prediction_trust=result.get('prediction_trust'),
        uncertainty_lower=result.get('uncertainty_lower'),
        uncertainty_upper=result.get('uncertainty_upper'),
        model_selection_audit=result.get('model_selection_audit', {}),
        source=str(source or 'unknown')[:50],
        source_filename=str(source_filename)[:255] if source_filename else None,
        user_id=user_id,
    )
    # SAVEPOINT: a duplicate-request_id race rolls back ONLY this insert.
    # The caller's transaction remains usable for its surrounding work.
    try:
        with db.session.begin_nested():
            db.session.add(p)
    except IntegrityError:
        existing = Prediction.query.filter_by(
            organization_id=str(org_id), request_id=rid
        ).first()
        if existing:
            return existing, True
        raise
    if not config.IS_PRODUCTION:
        assert p.model_type and str(p.model_type).lower() != 'unknown', f'Prediction {p.id} has unknown model_type'
        assert p.model_output, f'Prediction {p.id} has empty model_output'
    return p, False

# ------------------------------------------------------------
# Prediction concurrency guard.
# Prevents duplicate inference work when the same request_id is submitted
# concurrently. DB-level idempotency still handles requests after completion.
# ------------------------------------------------------------
def _acquire_prediction_lock(org_id, request_id, ttl_seconds=30):
    """Acquire a short-lived Redis lock for one tenant-scoped prediction.

    Returns True when acquired. If Redis is unavailable, preserve the requested
    degraded/dev behavior and rely on database idempotency as a fallback.
    """
    if not redis_client:
        return True
    key = f'pred_lock:{org_id}:{request_id}'
    token = secrets.token_urlsafe(24)
    try:
        acquired = redis_client.set(key, token, nx=True, ex=max(1, int(ttl_seconds)))
        if acquired:
            # Store the owner token per request context so only this request can
            # release its own lock, even if the TTL expires and another worker
            # acquires a replacement lock in the meantime.
            g._prediction_lock_tokens = getattr(g, '_prediction_lock_tokens', {})
            g._prediction_lock_tokens[(str(org_id), str(request_id))] = token
        return bool(acquired)
    except Exception:
        logger.warning('Prediction lock acquisition failed; continuing without lock', exc_info=True)
        return True


def _release_prediction_lock(org_id, request_id):
    """Release a lock only if this request still owns it."""
    if not redis_client:
        return
    tokens = getattr(g, '_prediction_lock_tokens', {})
    token = tokens.pop((str(org_id), str(request_id)), None)
    if not token:
        return
    key = f'pred_lock:{org_id}:{request_id}'
    try:
        # Compare-and-delete avoids deleting a newer worker's lock after expiry.
        redis_client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1, key, token
        )
    except Exception:
        logger.warning('Prediction lock release failed', exc_info=True)


def _prediction_error_payload(exc, request_id):
    detail = str(exc)
    safe_detail = detail
    try:
        parsed = json.loads(detail)
        safe_detail = {
            'code': parsed.get('code'),
            'registered_models': parsed.get('registered_models'),
            'registered_families': parsed.get('registered_families'),
            'incoming_columns': (parsed.get('incoming_columns') or [])[:100],
            'top_family_candidates': (parsed.get('family_ranking') or [])[:5],
            'closest_family_expected_features': (parsed.get('closest_family_expected_features') or [])[:100],
            'model_attempts': [
                {'model_id': str(a.get('model_id', ''))[:180],
                 'family': str(a.get('family', ''))[:100],
                 'status': str(a.get('status', ''))[:40],
                 'reason': str(a.get('reason', ''))[:500]}
                for a in (parsed.get('attempts') or [])[:20] if isinstance(a, dict)
            ],
        }
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return {
        'schema_version': config.PREDICTION_SCHEMA_VERSION,
        'success': False, 'prediction_status': 'abstained',
        'error': 'PREDICTION_ABSTAINED',
        'message': 'No compatible production trained model could serve this data.',
        'details': safe_detail, 'request_id': request_id,
        'hint': 'Check that the deployed validated model supports the uploaded columns and required history. Do not remove compatibility checks to force a result.',
    }

def _prediction_response(result, p, alert=None):
    audit = result.get('model_selection_audit') or {}
    safe_intelligence = {k: v for k, v in result.items()
                         if k not in ('model_selection_audit', 'family_candidates', 'algorithm_ranking', 'attempts')}
    safe_intelligence['model_selection'] = {
        'mode': audit.get('selection_mode', 'auto'),
        'selected_model': result.get('model_id'),
        'family': result.get('dataset_family'),
    }
    safe_intelligence['model_id'] = result.get('model_id')
    safe_intelligence['request_id'] = p.request_id
    safe_intelligence['fallback'] = False
    return {
        'schema_version': config.PREDICTION_SCHEMA_VERSION,
        'success': True,
        'request_id': p.request_id,
        'prediction': p.to_dict(),
        'intelligence': safe_intelligence,
        'alert_created': alert.to_dict() if alert else None,
    }

# ============================================================
# PRODUCTION READINESS GATE
# ============================================================
def production_readiness_report():
    """Return evidence-based launch checks; never claim model accuracy from metrics alone."""
    checks = []
    def check(name, ok, detail):
        checks.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    if not config.IS_PRODUCTION:
        check('environment', False, 'FLASK_ENV is not production')
    else:
        check('environment', True, 'production')
    check('diagnostic_fallback_disabled', True, 'diagnostic/heuristic prediction code path removed')
    check('validated_models_required', config.MODEL_REQUIRE_VALIDATED,
          'production requires explicit production validation metadata')
    check('trained_models_loaded', len(ml_engine.models) > 0,
          f'{len(ml_engine.models)} trained model artifacts registered')
    check('production_candidates', len(ml_engine.production_ids) > 0,
          f'{len(ml_engine.production_ids)} production-eligible candidates registered')
    check('postgresql', str(config.DATABASE_URL).lower().startswith(('postgresql://','postgres://')),
          'production should use PostgreSQL, not SQLite')
    check('secret_key', bool(config.SECRET_KEY) and len(str(config.SECRET_KEY)) >= 32,
          'SECRET_KEY must be explicitly configured and at least 32 characters')
    check('jwt_secret', bool(config.JWT_SECRET_KEY) and len(str(config.JWT_SECRET_KEY)) >= 32,
          'JWT_SECRET_KEY must be explicitly configured and at least 32 characters')
    cors = str(config.CORS_ORIGINS).lower()
    check('cors', not any(x in cors for x in ('localhost','127.0.0.1')),
          'production CORS must not contain localhost/127.0.0.1')
    # Payment/email are deployment concerns; report their configured state without
    # pretending that a live transaction has been independently verified here.
    check('paddle_live', config.PADDLE_ENV == 'production' and bool(config.PADDLE_API_KEY),
          'Paddle production API key/environment required for live billing')
    check('email', bool(config.MAIL_USERNAME) and not config.MAIL_SUPPRESS_SEND,
          'transactional email must be explicitly configured for launch')
    failures = [c for c in checks if not c['ok']]
    return {
        'ready': not failures,
        'checks': checks,
        'registered_artifacts': len(ml_engine.models),
        'registered_families': len(ml_engine.all_by_family),
        'production_candidates': len(ml_engine.production_ids),
        'warning': 'A metrics.json value is a reported training result unless explicit validation metadata is present.'
    }


# ============================================================
# CREATE APP
# ============================================================

# Global software availability state.  The database is the durable source of truth;
# Redis is mirrored for deployments that use it and process-local state is only a
# last-resort fallback if both shared stores are unavailable.
_SYSTEM_STATE_LOCK = threading.RLock()
_SYSTEM_ONLINE_FALLBACK = True
_SYSTEM_STATE_TABLE_READY = False


def _ensure_system_state_table():
    global _SYSTEM_STATE_TABLE_READY
    if _SYSTEM_STATE_TABLE_READY:
        return
    with _SYSTEM_STATE_LOCK:
        if _SYSTEM_STATE_TABLE_READY:
            return
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS synapse_system_state (
                state_key VARCHAR(100) PRIMARY KEY,
                state_value VARCHAR(20) NOT NULL,
                updated_at VARCHAR(50) NOT NULL,
                updated_by VARCHAR(100)
            )
        """))
        db.session.commit()
        _SYSTEM_STATE_TABLE_READY = True


def _get_system_online():
    global _SYSTEM_ONLINE_FALLBACK
    db_read_failed = False
    try:
        _ensure_system_state_table()
        row = db.session.execute(text(
            "SELECT state_value FROM synapse_system_state WHERE state_key = :k"
        ), {'k': 'system_online'}).first()
        if row is not None:
            value = str(row[0]).strip().lower() not in ('false', '0', 'off', 'disabled')
            _SYSTEM_ONLINE_FALLBACK = value
            return value
        # A readable, newly-created state table with no row means first boot.
        return _SYSTEM_ONLINE_FALLBACK
    except Exception:
        db_read_failed = True
        db.session.rollback()
    if redis_client:
        try:
            raw = redis_client.get('system_online')
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8', errors='ignore')
                value = str(raw).strip().lower() not in ('false', '0', 'off', 'disabled')
                _SYSTEM_ONLINE_FALLBACK = value
                return value
            if not db_read_failed:
                return _SYSTEM_ONLINE_FALLBACK
        except Exception:
            pass
    if db_read_failed:
        raise RuntimeError('System status could not be read from the database or Redis')
    return _SYSTEM_ONLINE_FALLBACK


def _set_system_online(online, actor_id=None):
    global _SYSTEM_ONLINE_FALLBACK
    value = 'true' if bool(online) else 'false'
    now = datetime.now(timezone.utc).isoformat()
    # Write the durable database state first; do not claim success if this fails.
    _ensure_system_state_table()
    row = db.session.execute(text(
        "SELECT state_key FROM synapse_system_state WHERE state_key = :k"
    ), {'k': 'system_online'}).first()
    if row:
        db.session.execute(text("""
            UPDATE synapse_system_state
            SET state_value = :v, updated_at = :t, updated_by = :u
            WHERE state_key = :k
        """), {'k': 'system_online', 'v': value, 't': now,
               'u': str(actor_id) if actor_id else None})
    else:
        db.session.execute(text("""
            INSERT INTO synapse_system_state (state_key, state_value, updated_at, updated_by)
            VALUES (:k, :v, :t, :u)
        """), {'k': 'system_online', 'v': value, 't': now,
               'u': str(actor_id) if actor_id else None})
    db.session.commit()
    if redis_client:
        try:
            redis_client.set('system_online', value)
        except Exception:
            logger.warning('System state saved to DB but Redis mirror update failed', exc_info=True)
    _SYSTEM_ONLINE_FALLBACK = bool(online)
    return bool(online)


def create_app():
    app = Flask(__name__, static_folder=None)
    if SENTRY_AVAILABLE and config.SENTRY_DSN:
        try:
            sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[FlaskIntegration()], traces_sample_rate=0.1, send_default_pii=False)
            logger.info('Sentry error monitoring enabled')
        except Exception:
            logger.exception('Sentry initialization failed')
    app.config.from_object(config)

    try:
        from flask.json.provider import DefaultJSONProvider

        class SafeJSONProvider(DefaultJSONProvider):
            @staticmethod
            def default(o):
                if isinstance(o, memoryview):
                    try:
                        return o.tobytes().decode('utf-8', errors='replace')
                    except Exception:
                        return str(o)
                if isinstance(o, (bytes, bytearray)):
                    try:
                        return o.decode('utf-8', errors='replace')
                    except Exception:
                        return str(o)
                if isinstance(o, datetime):
                    return o.isoformat()
                if isinstance(o, date):
                    return o.isoformat()
                if isinstance(o, Decimal):
                    return float(o)
                if isinstance(o, uuid.UUID):
                    return str(o)
                try:
                    return DefaultJSONProvider.default(o)
                except TypeError:
                    return str(o)

        app.json = SafeJSONProvider(app)
    except Exception as e:
        logger.warning(f'SafeJSONProvider install failed: {e}')

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)
    migrate.init_app(app, db)
    # mail.init_app(app)
    compress.init_app(app)

    if config.ENABLE_RATE_LIMITING:
        try:
            limiter.init_app(app)
        except Exception as e:
            logger.warning(f'Limiter init failed: {e}')

    CORS(app, resources={
        r"/api/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": [
                "Content-Type", "Authorization", "Accept", "Accept-Language",
                "X-API-Key", "X-Correlation-ID", "X-Request-ID", "X-MFA-Token",
                "X-Device-ID", "X-Tenant-ID", "X-Client-Version",
                "X-Timezone", "X-Language", "Cache-Control", "Pragma",
                "X-Device-Key",
            ],
            "expose_headers": [
                "X-Correlation-ID", "X-Request-ID", "X-Response-Time",
                "Content-Disposition", "X-Total-Count", "Retry-After",
            ],
            "supports_credentials": True,
            "max_age": 86400,
        }
    })

    # ============================================================
    # FIX: request hooks — g.start_time is set FIRST, always present
    # ============================================================

    @app.before_request
    def before_request():
        # Set start_time FIRST so after_request never fails, even if
        # Flask-Limiter aborts the request inside dispatch.
        g.start_time = time.time()
        raw_rid = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        g.request_id = re.sub(r'[^A-Za-z0-9._:-]', '', str(raw_rid))[:64] or str(uuid.uuid4())
        g.correlation_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
        if not hasattr(g, 'user'):
            g.user = None
        if not hasattr(g, 'organization_id'):
            g.organization_id = None

        # Global maintenance gate.  Only the admin status/start endpoints and
        # authentication needed to re-establish an admin session remain reachable.
        # All normal APIs return 404 while disabled, avoiding data leakage.
        path = request.path or ''
        if path.startswith('/api/') and request.method != 'OPTIONS':
            allowed_while_offline = {
                '/api/v1/admin/system/status',
                '/api/v1/admin/system/start',
                '/api/v1/auth/login',
                '/api/v1/auth/refresh',
            }
            try:
                online = _get_system_online()
            except Exception:
                online = None
            if online is None and path not in allowed_while_offline:
                return jsonify({'success': False, 'error': 'Service state unavailable'}), 503
            if online is False and path not in allowed_while_offline:
                return jsonify({'success': False, 'error': 'Not found'}), 404

    @app.after_request
    def after_request(response):
        start = getattr(g, 'start_time', None)
        elapsed = (time.time() - start) if start else 0.0

        response.headers['X-Correlation-ID'] = getattr(g, 'correlation_id', str(uuid.uuid4()))
        response.headers['X-Request-ID'] = getattr(g, 'request_id', str(uuid.uuid4()))
        response.headers['X-Response-Time'] = f"{elapsed * 1000:.2f}ms"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Server'] = 'SynapsePM'

        # PWA must be embeddable in itself; do not X-Frame the whole site.
        # DENY broke the standalone PWA window on some browsers.
        path_now = request.path or ''
        if path_now.startswith('/manifest.json') or path_now.startswith('/sw.js'):
            response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
            response.headers['Access-Control-Allow-Origin'] = config.FRONTEND_URL.rstrip('/')
        else:
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        # Critical: allow the service worker scope from the site root.
        if path_now.startswith('/sw.js'):
            response.headers['Service-Worker-Allowed'] = '/'

        path = request.path or ''
        if (path.startswith('/api/v1/auth') or
                path in ('/login.html', '/login', '/signup.html', '/signup',
                         '/dashboard', '/dashboard.html')):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        if config.IS_PRODUCTION:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        if PROMETHEUS_AVAILABLE and config.ENABLE_METRICS and REQUEST_COUNT:
            try:
                ep = request.endpoint or 'unknown'
                REQUEST_COUNT.labels(
                    method=request.method, endpoint=ep,
                    status=response.status_code
                ).inc()
                REQUEST_LATENCY.labels(method=request.method, endpoint=ep).observe(elapsed)
            except Exception:
                pass
        return response

    # ============================================================
    # FIX: JSON 429 handler (was returning HTML from Flask-Limiter)
    # ============================================================

    @app.errorhandler(TooManyRequests)
    def handle_429(e):
        retry_after = getattr(e, 'retry_after', None) or 60
        try:
            retry_after = int(retry_after)
        except Exception:
            retry_after = 60
        resp = jsonify({
            'success': False,
            'error': 'Rate limit exceeded. Please slow down.',
            'retry_after': retry_after,
        })
        resp.status_code = 429
        resp.headers['Retry-After'] = str(retry_after)
        return resp

    @app.errorhandler(404)
    def handle_404(e):
        if (request.path or '').startswith('/api/'):
            return jsonify({
                'success': False,
                'error': getattr(e, 'description', 'Not found'),
                'request_id': getattr(g, 'request_id', None),
            }), 404
        try:
            page = os.path.join(os.path.dirname(os.path.abspath(__file__)), '404.html')
            if os.path.isfile(page):
                return send_file(page), 404
        except Exception:
            pass
        return e

    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        logger.error(f"Unhandled: {e}\n{traceback.format_exc()}")
        return jsonify({
            'success': False, 'error': 'Internal server error',
            'request_id': getattr(g, 'request_id', None)
        }), 500

    with app.app_context():
        if config.SCHEMA_AUTO_PATCH:
            try:
                auto_patch_schema()
            except Exception as e:
                logger.exception(f"Schema auto-patch failed: {e}")

        try:
            _ensure_system_state_table()
            PaymentIdempotency.__table__.create(bind=db.engine, checkfirst=True)
        except Exception as e:
            db.session.rollback()
            logger.exception(f"System-state table initialization failed: {e}")

        try:
            if config.DB_AUTO_CREATE and not config.IS_PRODUCTION:
                db.create_all()
                logger.info("Dev DB tables created/verified")
        except Exception as e:
            logger.warning(f"DB create warning: {e}")
            db.session.rollback()

        def ensure_admin():
            if not config.ADMIN_EMAIL or not config.ADMIN_PASSWORD:
                return
            try:
                admin = User.query.filter_by(email=config.ADMIN_EMAIL).first()
                if admin:
                    if config.ADMIN_FORCE_RESET:
                        admin.set_password(config.ADMIN_PASSWORD)
                        admin.is_locked = False
                        admin.locked_until = None
                        admin.login_attempts = 0
                        admin.is_active = True
                        admin.is_verified = True
                        db.session.commit()
                        logger.info(
                            f"✅ Admin password force-synced for {config.ADMIN_EMAIL}"
                        )
                    return
                org = Organization.query.filter_by(slug='synapse-admin').first()
                if not org:
                    org = Organization(
                        name='SynapsePM Admin', slug='synapse-admin',
                        primary_email=config.ADMIN_EMAIL, plan='ENTERPRISE',
                        subscription_status='active', max_users=999,
                        max_machines=999, max_api_calls=999999, max_storage_gb=999,
                        settings={'trial_override': True}
                    )
                    db.session.add(org)
                    db.session.flush()
                admin = User(
                    email=config.ADMIN_EMAIL, username=config.ADMIN_EMAIL,
                    first_name=config.ADMIN_FIRST_NAME,
                    last_name=config.ADMIN_LAST_NAME,
                    display_name=f"{config.ADMIN_FIRST_NAME} {config.ADMIN_LAST_NAME}",
                    role=config.ADMIN_ROLE, organization_id=org.id,
                    is_verified=True, is_active=True, password_history=[]
                )
                admin.set_password(config.ADMIN_PASSWORD)
                db.session.add(admin)
                db.session.commit()
                logger.info(f"✅ Admin created: {config.ADMIN_EMAIL}")
            except Exception as e:
                logger.error(f"Admin creation failed: {e}")
                db.session.rollback()

        ensure_admin()

        if config.IS_PRODUCTION:
            if config.MODEL_REQUIRE_VALIDATED and not ml_engine.production_ids:
                raise RuntimeError(
                    f'Production boot blocked: 0 validated models. Registered={len(ml_engine.models)}, '
                    f'families={len(ml_engine.all_by_family)}. Deploy a validated artifact before launch.'
                )
            if not ml_engine.production_ids:
                raise RuntimeError('Production boot blocked: no production model candidates are registered.')
            loaded_smoke_tests = 0
            for model_id in ml_engine.production_ids[:3]:
                try:
                    ml_engine.load_model(model_id)
                    loaded_smoke_tests += 1
                except Exception:
                    logger.exception('Production model smoke test failed for %s', model_id)
            if loaded_smoke_tests == 0:
                raise RuntimeError('Production boot blocked: no production candidate model could be loaded.')

        if config.ENABLE_CLEANUP_THREAD:
            t = threading.Thread(target=_cleanup_loop, args=(app,), daemon=True)
            t.start()
            logger.info("Cleanup thread started")

        mqtt = start_mqtt_subscriber(app)
        if mqtt:
            app.mqtt_client = mqtt

    # ============================================================
    # HEALTH / METRICS
    # ============================================================

    @app.route('/health')
    def health():
        """Liveness endpoint: don't let model cold-start trigger Render restart loops."""
        try:
            db.session.execute(text('SELECT 1'))
            db_ok = True
        except Exception as exc:
            db_ok = False
            logger.warning('Health database check failed: %s', exc)
        redis_ok = False
        if redis_client:
            try:
                redis_client.ping()
                redis_ok = True
            except Exception:
                pass
        models_ready = bool(ml_engine.production_ids) if config.MODEL_REQUIRE_VALIDATED else bool(ml_engine.models)
        status = 'unhealthy' if not db_ok else ('healthy' if models_ready else 'starting')
        mail_mode = ('suppressed' if config.MAIL_SUPPRESS_SEND or not config.MAIL_USERNAME else 'live')
        return jsonify({
            'status': status, 'version': config.APP_VERSION,
            'database': db_ok, 'redis': redis_ok, 'realtime': bool(redis_client) or bool(FLASK_SOCK_AVAILABLE),
            'mqtt': bool(_mqtt_client), 'mail_mode': mail_mode,
            'mail_configured': bool(config.MAIL_USERNAME),
            'ml_models': len(ml_engine._model_cache),
            'ml_registered': len(ml_engine.models),
            'ml_production_ready': models_ready,
            'ml_families': len(ml_engine.all_by_family),
            'payment_gateways': payment_processor.get_gateways(),
            'payment_status': payment_processor.gateway_status(),
        }), (503 if not db_ok else 200)

    @app.route('/health/ready')
    def health_ready():
        """Readiness details; reports model loading separately from process liveness."""
        if not ml_engine.models:
            return jsonify({'ready': False, 'reason': 'models_downloading_or_not_registered', 'models': 0}), 200
        if config.MODEL_REQUIRE_VALIDATED and not ml_engine.production_ids:
            return jsonify({'ready': False, 'reason': 'no_validated_models', 'models': len(ml_engine.models)}), 200
        return jsonify({'ready': True, 'models': len(ml_engine.models), 'production_models': len(ml_engine.production_ids)}), 200

    @app.route('/health/deep')
    def health_deep():
        checks = {'database': False, 'redis': False, 'paddle': False, 'smtp': False, 'mqtt': False}
        details = {}
        try:
            db.session.execute(text('SELECT 1'))
            checks['database'] = True
        except Exception as e:
            details['database'] = str(e)
        if redis_client:
            try:
                redis_client.ping(); checks['redis'] = True
            except Exception as e:
                details['redis'] = str(e)
        if config.PADDLE_API_KEY and REQUESTS_AVAILABLE:
            try:
                base = 'https://sandbox-api.paddle.com' if config.PADDLE_ENV == 'sandbox' else 'https://api.paddle.com'
                rr = requests.get(base + '/products?per_page=1', headers={'Authorization': f'Bearer {config.PADDLE_API_KEY}'}, timeout=(2, 5))
                checks['paddle'] = 200 <= rr.status_code < 300
                if not checks['paddle']: details['paddle'] = f'HTTP {rr.status_code}: {rr.text[:300]}'
            except Exception as e:
                details['paddle'] = str(e)
        elif not config.PADDLE_API_KEY:
            details['paddle'] = 'not configured'
        try:
            with socket.create_connection((config.MAIL_SERVER, config.MAIL_PORT), timeout=3):
                checks['smtp'] = True
        except Exception as e:
            details['smtp'] = str(e)
        if config.ENABLE_MQTT:
            try:
                with socket.create_connection((config.MQTT_BROKER, config.MQTT_PORT), timeout=3):
                    checks['mqtt'] = True
            except Exception as e:
                details['mqtt'] = str(e)
        else:
            details['mqtt'] = 'disabled'
        status = 'healthy' if checks['database'] and checks['redis'] else 'degraded'
        return jsonify({'status': status, 'checks': checks, 'details': details, 'version': config.APP_VERSION}), (200 if status == 'healthy' else 503)

    @app.route('/live')
    def live():
        return jsonify({'status': 'alive', 'version': config.APP_VERSION}), 200

    @app.route('/ready')
    def ready():
        try:
            db.session.execute(text('SELECT 1'))
            if config.MODEL_REQUIRE_VALIDATED and not ml_engine.production_ids:
                return jsonify({'status': 'not_ready', 'reason': 'no_production_models'}), 503
            if not ml_engine.models:
                return jsonify({'status': 'not_ready', 'reason': 'no_trained_models'}), 503
            return jsonify({'status': 'ready', 'version': config.APP_VERSION,
                            'registered_models': len(ml_engine.models),
                            'production_candidates': len(ml_engine.production_ids)}), 200
        except Exception:
            return jsonify({'status': 'not_ready'}), 503

    @app.route('/ping')
    def ping():
        return jsonify({'status': 'pong'}), 200

    if PROMETHEUS_AVAILABLE and config.ENABLE_METRICS:
        @app.route('/metrics')
        def metrics():
            return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    # ============================================================
    # STATIC FILE SERVING
    # ============================================================

    # ============================================================
    # PWA ROUTES + STATIC FILES
    # ============================================================

    @app.route('/manifest.json')
    def serve_pwa_manifest():
        if not config.ENABLE_PWA:
            return jsonify({'error': 'PWA disabled'}), 404
        manifest = {
            "name": f"{config.APP_NAME} — Predictive Maintenance",
            "short_name": config.PWA_SHORT_NAME,
            "description": "AI-powered predictive maintenance for industrial equipment",
            "start_url": "/dashboard.html", "scope": "/", "display": "standalone",
            "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
            "orientation": "any", "background_color": config.PWA_BG_COLOR,
            "theme_color": config.PWA_THEME_COLOR, "lang": "en", "dir": "ltr",
            "categories": ["business", "productivity", "utilities"],
            "prefer_related_applications": False,
            "icons": [
                {"src": "/user/assets/img/logo.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/user/assets/img/logo.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "/user/assets/img/logo.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
                {"src": "/user/assets/img/logo.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
            ],
            "shortcuts": [
                {"name": "Dashboard", "short_name": "Dashboard", "url": "/dashboard.html", "icons": [{"src": "/user/assets/img/logo.png", "sizes": "192x192"}]},
                {"name": "Machines", "short_name": "Machines", "url": "/machines.html", "icons": [{"src": "/user/assets/img/logo.png", "sizes": "192x192"}]},
                {"name": "Alerts", "short_name": "Alerts", "url": "/alerts.html", "icons": [{"src": "/user/assets/img/logo.png", "sizes": "192x192"}]}
            ]
        }
        resp = jsonify(manifest)
        resp.headers['Content-Type'] = 'application/manifest+json'
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp

    @app.route('/sw.js')
    def serve_service_worker():
        if not config.ENABLE_PWA:
            resp = Response("// PWA disabled", mimetype='application/javascript')
            resp.headers['Service-Worker-Allowed'] = '/'
            return resp
        sw = r'''// SynapsePM Service Worker v1
const CACHE_NAME = 'synapsepm-shell-v1';
const RUNTIME_CACHE = 'synapsepm-runtime-v1';
const SHELL_URLS = ['/dashboard.html','/machines.html','/predictions.html','/alerts.html','/reports.html','/billing.html','/settings.html','/login.html','/signup.html','/manifest.json','/user/assets/img/logo.png'];
self.addEventListener('install', (event) => { event.waitUntil(caches.open(CACHE_NAME).then((cache) => Promise.allSettled(SHELL_URLS.map((u) => cache.add(u).catch(() => null)))).then(() => self.skipWaiting())); });
self.addEventListener('activate', (event) => { event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME && k !== RUNTIME_CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', (event) => {
  const req = event.request; const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) return;
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(fetch(req).then((res) => { const copy=res.clone(); caches.open(RUNTIME_CACHE).then(c=>c.put(req,copy)).catch(()=>{}); return res; }).catch(()=>caches.match(req).then(c=>c||caches.match('/dashboard.html'))));
    return;
  }
  event.respondWith(caches.match(req).then((cached) => cached || fetch(req).then((res) => { if(res && res.status===200 && res.type==='basic'){const copy=res.clone(); caches.open(RUNTIME_CACHE).then(c=>c.put(req,copy)).catch(()=>{});} return res; }).catch(()=>cached)));
});
self.addEventListener('message', (event) => { if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting(); });
'''
        resp = Response(sw, mimetype='application/javascript')
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp

    @app.route('/offline.html')
    def serve_offline_page():
        return '''<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Offline | SynapsePM</title><style>body{margin:0;font-family:Inter,Arial,sans-serif;background:#0f2b3d;color:white;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1rem}.card{max-width:420px;text-align:center;padding:2rem}.logo{font-size:1.6rem;font-weight:800;margin-bottom:1rem}.logo span{color:#00CFE8}h1{font-size:1.4rem;margin:0 0 .5rem}p{color:#94a3b8;line-height:1.6;font-size:.95rem;margin:0 0 1.5rem}button{background:linear-gradient(135deg,#00b4aa,#009688);color:#fff;border:0;padding:.75rem 1.75rem;border-radius:.75rem;font-weight:600;cursor:pointer}</style></head><body><div class='card'><div class='logo'>Synapse<span>PM</span></div><h1>You're offline</h1><p>SynapsePM needs an internet connection to fetch live machine data, run predictions, and sync alerts. Reconnect and try again.</p><button onclick='location.reload()'>Retry</button></div></body></html>''', 200

    @app.route('/favicon.ico')
    def favicon():
        ff = get_frontend_folder()
        for p in [os.path.join(ff, 'assets', 'img', 'logo.png'), os.path.join(ff, 'img', 'logo.png'), os.path.join(ff, 'favicon.ico')]:
            if os.path.exists(p): return send_file(p)
        return Response('', status=204)

    @app.route('/uploads/<path:filename>')
    def serve_uploads(filename):
        root = Path(config.UPLOAD_FOLDER).resolve()
        target = (root / filename).resolve()
        if not str(target).startswith(str(root) + os.sep):
            return jsonify({'success': False, 'error': 'Invalid path'}), 400
        if not target.is_file():
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return send_file(str(target), conditional=True, max_age=3600)

    @app.route('/verify-email')
    def verify_email_page():
        return '''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Verify Email | SynapsePM</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Manrope:wght@700;800&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" rel="stylesheet">
<style>body{font-family:Inter,sans-serif;background:#f8fafc}.gradient-primary{background:linear-gradient(135deg,#0f2b3d,#1a4a6e)}.gradient-cta{background:linear-gradient(135deg,#00b4aa,#009688)}.logo{font-family:Manrope,sans-serif;font-weight:800}</style>
</head><body class="min-h-screen flex items-center justify-center p-4">
<div class="max-w-md w-full bg-white rounded-2xl shadow-xl overflow-hidden">
<div class="gradient-primary px-8 py-6"><div class="logo text-[22px] text-white">Synapse<span class="text-cyan-300">PM</span></div><p class="text-teal-100 text-xs mt-1 uppercase tracking-widest">Email Verification</p></div>
<div class="p-8 text-center">
<div id="loading"><div class="w-16 h-16 mx-auto bg-teal-50 rounded-full flex items-center justify-center mb-4"><span class="material-symbols-outlined text-teal-600 text-3xl animate-spin">refresh</span></div><h2 class="text-lg font-bold text-slate-800 mb-1">Verifying your email…</h2><p class="text-sm text-slate-500">This will only take a moment.</p></div>
<div id="success" class="hidden"><div class="w-16 h-16 mx-auto bg-green-50 rounded-full flex items-center justify-center mb-4"><span class="material-symbols-outlined text-green-600 text-3xl">check_circle</span></div><h2 class="text-lg font-bold text-slate-800 mb-1">Email verified!</h2><p class="text-sm text-slate-500 mb-6">Your account is ready. Redirecting to your dashboard…</p><a href="/dashboard.html" class="inline-block gradient-cta text-white px-6 py-3 rounded-xl font-semibold text-sm">Go to Dashboard</a></div>
<div id="error" class="hidden"><div class="w-16 h-16 mx-auto bg-red-50 rounded-full flex items-center justify-center mb-4"><span class="material-symbols-outlined text-red-600 text-3xl">error</span></div><h2 class="text-lg font-bold text-slate-800 mb-1">Verification failed</h2><p id="errorMessage" class="text-sm text-slate-500 mb-6"></p><a href="/login.html" class="inline-block border border-slate-200 text-slate-700 px-6 py-3 rounded-xl font-semibold text-sm">Back to Login</a></div>
</div></div>
<script>(function(){const token=new URLSearchParams(location.search).get('token'),loading=document.getElementById('loading'),success=document.getElementById('success'),error=document.getElementById('error'),msg=document.getElementById('errorMessage');if(!token){loading.classList.add('hidden');error.classList.remove('hidden');msg.textContent='No verification token was provided.';return;}fetch('/api/v1/auth/verify-email',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({token})}).then(async r=>{let d={};try{d=await r.json()}catch(_){}if(!r.ok||!d.success)throw new Error(d.error||d.message||'The token is invalid or has expired.');loading.classList.add('hidden');success.classList.remove('hidden');setTimeout(()=>{location.replace('/dashboard.html')},1200)}).catch(e=>{loading.classList.add('hidden');error.classList.remove('hidden');msg.textContent=e.message||'Network error. Please try again.'})})();</script>
</body></html>''', 200

    @app.route('/api')
    def api_index():
        return jsonify({
            'service': config.APP_NAME, 'version': config.APP_VERSION,
            'endpoints': {
                'auth': '/api/v1/auth', 'users': '/api/v1/users',
                'machines': '/api/v1/machines', 'predictions': '/api/v1/predictions',
                'alerts': '/api/v1/alerts', 'payments': '/api/v1/payments',
                'billing': '/api/v1/billing', 'admin': '/api/v1/admin',
                'downloads': '/api/v1/downloads', 'reports': '/api/v1/reports',
                'datasets': '/api/v1/datasets', 'careers': '/api/v1/careers',
                'contact': '/api/v1/contact', 'enterprise': '/api/v1/enterprise',
                'applications': '/api/v1/applications', 'tenants': '/api/v1/tenants',
                'mqtt_topic_template': f'{config.MQTT_TOPIC_PREFIX}/<machine_uuid>/sensor',
            },
            'plans': config.PLANS
        }), 200

    @app.route('/')
    def serve_index():
        ff = get_frontend_folder()
        for p in [os.path.join(ff, 'user', 'index.html'),
                  os.path.join(ff, 'index.html')]:
            if os.path.exists(p):
                return send_file(p, mimetype='text/html')
        return '<html><body><h1>SynapsePM</h1><a href="/login.html">Login</a></body></html>', 200

    @app.route('/dashboard')
    @app.route('/dashboard.html')
    def serve_dashboard():
        ff = get_frontend_folder()
        for p in [os.path.join(ff, 'user', 'dashboard.html'),
                  os.path.join(ff, 'dashboard.html')]:
            if os.path.exists(p):
                return send_file(p, mimetype='text/html')
        return '<html><body><h1>Dashboard</h1></body></html>', 200

    @app.route('/<filename>.html')
    def serve_html(filename):
        ff = get_frontend_folder()
        for p in [os.path.join(ff, 'user', f'{filename}.html'),
                  os.path.join(ff, 'admin', f'{filename}.html'),
                  os.path.join(ff, f'{filename}.html')]:
            if os.path.exists(p):
                return send_file(p, mimetype='text/html')
        return f"Page {filename}.html not found", 404

    @app.route('/admin/<filename>.html')
    def serve_admin_html(filename):
        ff = get_frontend_folder()
        for p in [os.path.join(ff, 'admin', f'{filename}.html'),
                  os.path.join(ff, 'user', f'{filename}.html'),
                  os.path.join(ff, f'{filename}.html')]:
            if os.path.exists(p):
                return send_file(p, mimetype='text/html')
        return f"Page admin/{filename}.html not found", 404

    @app.route('/assets/<path:filename>')
    @app.route('/admin/assets/<path:filename>')
    def serve_assets(filename):
        ff = get_frontend_folder()
        for p in [os.path.join(ff, 'assets', filename),
                  os.path.join(ff, 'user', 'assets', filename),
                  os.path.join(ff, 'img', filename)]:
            if os.path.exists(p):
                return send_file(p)
        bg = os.path.join(ff, 'assets', 'img', 'bg img.png')
        if os.path.exists(bg):
            return send_file(bg)
        return "Asset not found", 404

    # ============================================================
    # SHARED ERROR HELPER
    # ============================================================

    def jerr(msg, code=400, **extra):
        r = {'success': False, 'error': msg, 'message': msg}
        r.update(extra)
        return jsonify(r), code

    # ============================================================
    # AUTH BLUEPRINT
    # ============================================================

    auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

    @auth_bp.route('/register', methods=['POST'])
    @limiter.limit(f"{config.RATE_LIMIT_LOGIN} per minute")
    def register():
        try:
            data = request.get_json() or {}
            email = normalize_email(data.get('email'))
            password = str(data.get('password') or '')
            fn = normalize_name(data.get('first_name'))
            ln = normalize_name(data.get('last_name'))
            company = normalize_name(data.get('company'))
            for f, v in [('email', email), ('password', password),
                         ('first_name', fn), ('last_name', ln), ('company', company)]:
                if not v:
                    return jerr(f'{f} is required.', 400)
            policy_error = password_policy_error(password)
            if policy_error:
                return jerr(policy_error, 400)
            if not EMAIL_REGEX.match(email):
                return jerr('Invalid email.', 400)
            if User.query.filter_by(email=email).first():
                return jerr('Email already registered.', 409)

            ub = re.sub(r"[^a-zA-Z0-9_]", "", email.split('@')[0]).lower() or 'user'
            username = ub
            c = 1
            while User.query.filter_by(username=username).first():
                c += 1
                username = f'{ub}{c}'

            now = datetime.now(timezone.utc)
            org = Organization(
                name=company, slug=make_unique_org_slug(company),
                primary_email=email, plan='FREE', subscription_status='trialing',
                trial_ends_at=now + timedelta(days=config.TRIAL_DAYS),
                max_users=config.PLANS['free']['max_users'],
                max_machines=config.PLANS['free']['max_machines'],
                max_api_calls=config.PLANS['free']['max_api_calls'],
                max_storage_gb=config.PLANS['free']['max_storage_gb']
            )
            db.session.add(org)
            db.session.flush()
            user = User(
                organization_id=org.id, username=username, email=email,
                first_name=fn, last_name=ln, display_name=f'{fn} {ln}',
                role='org_admin', is_active=True, is_verified=False,
                password_history=[]
            )
            user.set_password(password)
            vt = secrets.token_urlsafe(48)
            user.verification_token = vt
            user.verification_token_expires_at = now + timedelta(hours=24)
            db.session.add(user)
            db.session.commit()
            send_verification_email(email, vt, user_name=fn or 'there')
            if config.MAIL_SUPPRESS_SEND:
                logger.info('[DEV] Verification token generated for %s (not returned to client).', email)

            rt, jti = user.generate_refresh_token()
            session_manager.create_session(
                user, request.remote_addr,
                request.headers.get('User-Agent'),
                jti=jti,
                token_hash=hashlib.sha256(rt.encode()).hexdigest()
            )
            access = user.generate_auth_token(session_jti=jti)

            try:
                broadcast_both('user_created', {
                    'user': user.to_dict(),
                    'organization': org.to_dict(),
                }, org_id=org.id)
            except Exception:
                pass

            return jsonify({
                'success': True,
                'message': 'Account created. Please verify your email.',
                'user': user.to_dict(), 'organization': org.to_dict(),
                'access_token': access, 'refresh_token': rt,
                'redirect': '/dashboard.html',
                'trial_days': config.TRIAL_DAYS,
                'requires_verification': True,
                'plans': config.PLANS,
                'gateways': payment_processor.get_gateways()
            }), 201
        except IntegrityError:
            db.session.rollback()
            return jerr('Account exists.', 409)
        except Exception:
            db.session.rollback()
            logger.exception('Register failed')
            return jerr('Registration failed.', 500)

    @auth_bp.route('/login', methods=['POST'])
    @limiter.limit(f"{config.RATE_LIMIT_LOGIN} per minute")
    def login():
        try:
            data = request.get_json() or {}
            email = normalize_email(data.get('email'))
            password = str(data.get('password') or '')
            remember = bool(data.get('remember_me', False))
            # Keep the user and global-admin login portals distinct. The portal is
            # supplied by the page, while role authorization remains server-side.
            portal = str(data.get('portal') or '').strip().lower()
            if portal not in ('user', 'admin'):
                ref_path = urlparse(request.referrer).path.lower() if request.referrer else ''
                portal = 'admin' if ref_path.startswith('/admin/') else 'user'
            if not email or not password:
                return jerr('Email and password required.', 400)
            user = User.query.filter_by(email=email).first()
            if not user:
                return jerr('Invalid email or password.', 401)
            now = datetime.now(timezone.utc)
            if user.is_locked and user.locked_until and \
                    now < ensure_aware(user.locked_until):
                mins = int((ensure_aware(user.locked_until) - now).total_seconds() / 60) + 1
                return jerr(f'Locked. Retry in {mins}m.', 403, account_locked=True)
            if user.is_locked and user.locked_until and \
                    now >= ensure_aware(user.locked_until):
                user.is_locked = False
                user.locked_until = None
                user.login_attempts = 0
                db.session.commit()
            if not user.check_password(password):
                user.login_attempts = (user.login_attempts or 0) + 1
                if user.login_attempts >= config.MAX_LOGIN_ATTEMPTS:
                    user.is_locked = True
                    user.locked_until = now + timedelta(minutes=config.LOCKOUT_DURATION_MINUTES)
                user.add_login_history(request.remote_addr,
                                       request.headers.get('User-Agent'), False)
                db.session.commit()
                return jerr('Invalid email or password.', 401)
            if not user.is_active:
                return jerr('Account deactivated.', 403)
            if portal == 'admin' and user.role not in ('super_admin', 'admin'):
                # Do not let a regular/org user use the global-admin portal.
                return jerr('This account does not have global administrator access. Use User Login.', 403)
            if user.is_password_expired():
                return jerr('Password expired.', 403, password_expired=True)
            if user.is_mfa_enabled:
                ch = jwt.encode({
                    'user_id': str(user.id), 'type': 'mfa_challenge',
                    'portal': portal,
                    'exp': int((now + timedelta(minutes=5)).timestamp()),
                    'iat': int(now.timestamp()), 'jti': str(uuid.uuid4()),
                    'iss': config.JWT_ISSUER, 'aud': config.JWT_AUDIENCE
                }, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
                return jsonify({
                    'success': True, 'mfa_required': True,
                    'challenge_token': ch, 'mfa_token': ch
                }), 200

            user.login_attempts = 0
            user.is_locked = False
            user.locked_until = None
            user.last_login_at = now
            user.last_login_ip = request.remote_addr
            user.login_count = (user.login_count or 0) + 1
            user.add_login_history(request.remote_addr,
                                   request.headers.get('User-Agent'), True)
            db.session.commit()
            org = db.session.get(Organization, user.organization_id)
            if not org:
                return jerr('Organization not found.', 500)
            trial_expired = org.is_trial_expired()
            if trial_expired and org.subscription_status != 'active':
                org.subscription_status = 'expired'
                db.session.commit()

            expiry = (config.JWT_REFRESH_EXPIRY_DAYS * 86400 if remember
                      else config.JWT_ACCESS_EXPIRY_MINUTES * 60)
            rt, jti = user.generate_refresh_token()
            session_manager.create_session(
                user, request.remote_addr,
                request.headers.get('User-Agent'),
                jti=jti,
                token_hash=hashlib.sha256(rt.encode()).hexdigest()
            )
            access = user.generate_auth_token(expiry, session_jti=jti)

            if redis_client:
                try:
                    rev_key = f"user_revoked:{user.id}"
                    rev_raw = redis_client.get(rev_key)
                    if rev_raw:
                        try:
                            rev_value = int(rev_raw)
                        except (TypeError, ValueError):
                            rev_value = 0
                        if rev_value <= 0:
                            access_payload = jwt.decode(
                                access,
                                config.JWT_SECRET_KEY,
                                algorithms=[config.JWT_ALGORITHM],
                                options={
                                    'verify_exp': False,
                                    'verify_iss': False,
                                    'verify_aud': False,
                                }
                            )
                            new_iat = int(access_payload.get('iat') or time.time())
                            redis_client.setex(
                                rev_key,
                                config.JWT_REFRESH_EXPIRY_DAYS * 86400,
                                str(max(0, new_iat - 1))
                            )
                except Exception:
                    logger.warning(
                        "Legacy user revocation marker migration failed",
                        exc_info=True
                    )

            org_dict = org.to_dict()
            try:
                broadcast_both('user_login', {
                    'user': user.to_dict(),
                }, org_id=org.id)
            except Exception:
                pass

            return jsonify({
                'success': True, 'message': 'Login successful',
                'access_token': access, 'refresh_token': rt,
                'user': user.to_dict(),
                'organization': org_dict,
                'tenant': org_dict,
                'redirect': '/admin/dashboard.html' if portal == 'admin' else '/dashboard.html',
                'portal': portal,
                'trial_days_remaining': org.trial_days_remaining,
                'is_trial_active': org.is_trial_active,
                'trial_expired': trial_expired, 'show_upgrade': trial_expired,
                'plans': config.PLANS,
                'gateways': payment_processor.get_gateways()
            }), 200
        except Exception:
            db.session.rollback()
            logger.exception('Login failed')
            return jerr('Login failed.', 500)

    @auth_bp.route('/logout', methods=['POST'])
    @login_required
    def logout():
        try:
            if g.token_jti:
                jwt_blacklist.add(g.token_jti, config.JWT_ACCESS_EXPIRY_MINUTES * 60)
            sid = (g.token_payload or {}).get('sid')
            if sid:
                session_manager.revoke_session(sid)
        except Exception:
            pass
        return jsonify({'success': True, 'message': 'Logged out'}), 200

    @auth_bp.route('/refresh', methods=['POST'])
    def refresh_token():
        try:
            data = request.get_json() or {}
            rt = data.get('refresh_token')
            if not rt:
                return jerr('Refresh token required.', 400)
            payload = jwt.decode(
                rt, config.JWT_REFRESH_SECRET,
                algorithms=[config.JWT_ALGORITHM],
                options={'verify_iss': False, 'verify_aud': False}
            )
            if payload.get('type') != 'refresh':
                return jerr('Invalid token type.', 401)
            uid = payload.get('user_id')
            jti = payload.get('jti')
            if jti and jwt_blacklist.check(jti):
                return jerr('Token revoked.', 401)

            if jti and not session_manager.check_session(jti):
                return jerr('Session revoked.', 401)

            if redis_client:
                try:
                    revoked_raw = redis_client.get(f"user_revoked:{uid}")
                    if revoked_raw:
                        try:
                            revoked_at = int(revoked_raw)
                        except (TypeError, ValueError):
                            revoked_at = 0
                        token_iat = int(payload.get('iat') or 0)
                        if revoked_at > 0 and token_iat < revoked_at:
                            return jerr('All sessions revoked.', 401)
                        if revoked_at == 0:
                            return jerr(
                                'Session revocation marker requires a new login.',
                                401
                            )
                except Exception:
                    logger.warning(
                        "Could not evaluate refresh revocation marker",
                        exc_info=True
                    )

            user = db.session.get(User, uid)
            if not user or not user.is_active:
                return jerr('Invalid user.', 401)
            org = db.session.get(Organization, user.organization_id)
            if not org or org.is_suspended:
                return jerr('Organization unavailable.', 403, organization_suspended=True)
            if jti:
                session_manager.revoke_session(jti)
            new_rt, new_jti = user.generate_refresh_token()
            session_manager.create_session(
                user, request.remote_addr,
                request.headers.get('User-Agent'),
                jti=new_jti,
                token_hash=hashlib.sha256(new_rt.encode()).hexdigest()
            )
            access = user.generate_auth_token(session_jti=new_jti)
            return jsonify({
                'success': True, 'access_token': access,
                'refresh_token': new_rt
            }), 200
        except jwt.ExpiredSignatureError:
            return jerr('Refresh expired.', 401)
        except jwt.InvalidTokenError:
            return jerr('Invalid refresh token.', 401)
        except Exception:
            logger.exception('Refresh failed')
            return jerr('Refresh failed.', 500)

    @auth_bp.route('/me', methods=['GET'])
    @login_required
    def me():
        return jsonify({
            'success': True, 'user': g.user.to_dict(),
            'organization': g.organization.to_dict() if g.organization else None
        }), 200

    @auth_bp.route('/forgot-password', methods=['POST'])
    @limiter.limit("10 per hour")
    def forgot_password():
        try:
            data = request.get_json() or {}
            email = normalize_email(data.get('email'))
            if not email or not EMAIL_REGEX.match(email):
                return jerr('Valid email required.', 400)
            user = User.query.filter_by(email=email).first()
            otp_sent = False
            otp = None
            if user:
                if user.reset_locked_until and \
                        datetime.now(timezone.utc) < ensure_aware(user.reset_locked_until):
                    return jerr('Too many attempts.', 429)
                otp = generate_otp(6)
                user.reset_otp_hash = hash_otp(otp)
                user.reset_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
                user.reset_otp_attempts = 0
                db.session.commit()
                send_password_reset_email(user.email, otp)
                otp_sent = True
            resp = {'success': True, 'message': 'If account exists, OTP sent.'}
            if config.MAIL_SUPPRESS_SEND and otp_sent:
                resp['otp'] = otp
            return jsonify(resp), 200
        except Exception:
            logger.exception('Forgot password failed')
            return jerr('Request failed.', 500)

    @auth_bp.route('/verify-otp', methods=['POST'])
    @limiter.limit("20 per minute")
    def verify_otp():
        try:
            data = request.get_json() or {}
            email = normalize_email(data.get('email'))
            otp = str(data.get('otp') or '').strip()
            if not email or not otp:
                return jerr('Email and OTP required.', 400)
            if not re.fullmatch(r'\d{6}', otp):
                return jerr('OTP must be 6 digits.', 400)
            user = User.query.filter_by(email=email).first()
            if not user:
                return jerr('Invalid OTP.', 400)
            if user.reset_locked_until and \
                    datetime.now(timezone.utc) < ensure_aware(user.reset_locked_until):
                return jerr('Too many attempts.', 429)
            if not user.reset_otp_hash or not user.reset_otp_expires_at:
                return jerr('OTP invalid or expired.', 400)
            if datetime.now(timezone.utc) > ensure_aware(user.reset_otp_expires_at):
                user.reset_otp_hash = None
                user.reset_otp_expires_at = None
                db.session.commit()
                return jerr('OTP expired.', 400)
            if hash_otp(otp) != user.reset_otp_hash:
                user.reset_otp_attempts = (user.reset_otp_attempts or 0) + 1
                if user.reset_otp_attempts >= config.PASSWORD_RESET_MAX_ATTEMPTS:
                    user.reset_locked_until = datetime.now(timezone.utc) + \
                        timedelta(minutes=config.PASSWORD_RESET_LOCKOUT_MINUTES)
                db.session.commit()
                return jerr('Invalid OTP.', 400)
            rt = secrets.token_urlsafe(48)
            user.password_reset_token = rt
            user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            user.reset_otp_hash = None
            user.reset_otp_expires_at = None
            user.reset_otp_attempts = 0
            user.reset_locked_until = None
            db.session.commit()
            return jsonify({
                'success': True, 'message': 'OTP verified.',
                'token': rt, 'reset_token': rt
            }), 200
        except Exception:
            logger.exception('OTP verify failed')
            return jerr('Verification failed.', 500)

    @auth_bp.route('/reset-password', methods=['POST'])
    def reset_password():
        try:
            data = request.get_json() or {}
            token = data.get('token')
            password = data.get('password') or data.get('new_password')
            if not token or not password:
                return jerr('Token and password required.', 400)
            policy_error = password_policy_error(password)
            if policy_error:
                return jerr(policy_error, 400)
            user = User.query.filter_by(password_reset_token=token).first()
            if not user or not user.password_reset_expires_at:
                return jerr('Invalid or expired token.', 400)
            if datetime.now(timezone.utc) > ensure_aware(user.password_reset_expires_at):
                user.password_reset_token = None
                user.password_reset_expires_at = None
                db.session.commit()
                return jerr('Token expired.', 400)
            user.set_password(password)
            session_manager.revoke_all_sessions(user.id)
            jwt_blacklist.revoke_all_user_tokens(user.id)
            user.password_reset_token = None
            user.password_reset_expires_at = None
            user.login_attempts = 0
            user.is_locked = False
            user.locked_until = None
            db.session.commit()
            return jsonify({'success': True, 'message': 'Password reset.'}), 200
        except Exception:
            db.session.rollback()
            logger.exception('Reset failed')
            return jerr('Reset failed.', 500)

    @auth_bp.route('/change-password', methods=['POST'])
    @login_required
    def change_password():
        try:
            data = request.get_json() or {}
            cp = data.get('current_password') or data.get('old_password')
            np = data.get('new_password')
            if not cp or not np:
                return jerr('Current and new password required.', 400)
            policy_error = password_policy_error(np)
            if policy_error:
                return jerr(policy_error, 400)
            if not g.user.check_password(cp):
                return jerr('Current password incorrect.', 401)
            g.user.set_password(np)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Password changed.'}), 200
        except Exception:
            db.session.rollback()
            logger.exception('Change password failed')
            return jerr('Change failed.', 500)

    @auth_bp.route('/verify-email', methods=['POST'])
    def verify_email():
        try:
            data = request.get_json() or {}
            token = data.get('token')
            if not token:
                return jerr('Token required.', 400)
            user = User.query.filter_by(verification_token=token).first()
            if not user:
                return jerr('Invalid or expired token.', 400)
            if user.verification_token_expires_at and \
                    datetime.now(timezone.utc) > ensure_aware(user.verification_token_expires_at):
                return jerr('Token expired.', 400)
            user.is_verified = True
            user.verification_token = None
            user.verification_token_expires_at = None
            db.session.commit()
            return jsonify({'success': True, 'message': 'Email verified.'}), 200
        except Exception:
            logger.exception('Verify email failed')
            return jerr('Verification failed.', 500)

    @auth_bp.route('/resend-verification', methods=['POST'])
    @limiter.limit("10 per hour")
    def resend_verification():
        try:
            data = request.get_json() or {}
            email = normalize_email(data.get('email'))
            if not email:
                return jerr('Email required.', 400)
            user = User.query.filter_by(email=email).first()
            if not user or user.is_verified:
                return jsonify({'success': True, 'message': 'If account exists, email sent.'}), 200
            vt = secrets.token_urlsafe(48)
            user.verification_token = vt
            user.verification_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            db.session.commit()
            send_verification_email(user.email, vt)
            return jsonify({
                'success': True, 'message': 'Verification email sent.',
                'verification_token': vt if config.MAIL_SUPPRESS_SEND else None
            }), 200
        except Exception:
            logger.exception('Resend verification failed')
            return jerr('Resend failed.', 500)

    @auth_bp.route('/sessions', methods=['GET'])
    @login_required
    def sessions():
        ss = session_manager.get_active_sessions(g.user.id)
        return jsonify({'success': True, 'sessions': [s.to_dict() for s in ss]}), 200

    @auth_bp.route('/sessions/<sid>', methods=['DELETE'])
    @login_required
    def delete_session(sid):
        so = UserSession.query.filter_by(id=sid, user_id=g.user.id).first()
        if not so:
            return jerr('Session not found.', 404)
        session_manager.revoke_session(so.jti)
        return jsonify({'success': True, 'message': 'Session revoked'}), 200

    @auth_bp.route('/sessions/revoke', methods=['POST'])
    @login_required
    def revoke_session():
        data = request.get_json() or {}
        sid = data.get('session_id')
        if not sid:
            return jerr('Session ID required.', 400)
        so = UserSession.query.filter_by(id=sid, user_id=g.user.id).first()
        if not so:
            return jerr('Session not found.', 404)
        session_manager.revoke_session(so.jti)
        return jsonify({'success': True, 'message': 'Session revoked'}), 200

    @auth_bp.route('/sessions/revoke-all', methods=['POST'])
    @login_required
    def revoke_all():
        count = session_manager.revoke_all_sessions(g.user.id)
        jwt_blacklist.revoke_all_user_tokens(g.user.id)
        return jsonify({'success': True, 'message': f'Revoked {count} sessions'}), 200

    @auth_bp.route('/revoke-sessions', methods=['POST'])
    @login_required
    def revoke_sessions_alias():
        count = session_manager.revoke_all_sessions(g.user.id)
        jwt_blacklist.revoke_all_user_tokens(g.user.id)
        return jsonify({'success': True, 'message': f'Revoked {count} sessions'}), 200

    @auth_bp.route('/github', methods=['GET'])
    def gh_login():
        if not config.GITHUB_CLIENT_ID:
            return jerr('GitHub not configured.', 501)
        try:
            u, s = oauth_service.get_authorization_url('github')
            return jsonify({'success': True, 'redirect_url': u}), 200
        except Exception as e:
            return jerr(str(e), 500)

    @auth_bp.route('/google', methods=['GET'])
    def g_login():
        if not config.GOOGLE_CLIENT_ID:
            return jerr('Google not configured.', 501)
        try:
            u, s = oauth_service.get_authorization_url('google')
            return jsonify({'success': True, 'redirect_url': u}), 200
        except Exception as e:
            return jerr(str(e), 500)

    @auth_bp.route('/linkedin', methods=['GET'])
    def l_login():
        if not config.LINKEDIN_CLIENT_ID:
            return jerr('LinkedIn not configured.', 501)
        try:
            u, s = oauth_service.get_authorization_url('linkedin')
            return jsonify({'success': True, 'redirect_url': u}), 200
        except Exception as e:
            return jerr(str(e), 500)

    @auth_bp.route('/github/callback', methods=['GET', 'POST'])
    def gh_cb():
        return handle_oauth_callback('github')

    @auth_bp.route('/google/callback', methods=['GET', 'POST'])
    def g_cb():
        return handle_oauth_callback('google')

    @auth_bp.route('/linkedin/callback', methods=['GET', 'POST'])
    def l_cb():
        return handle_oauth_callback('linkedin')

    _oauth_lock = threading.RLock()
    _oauth_codes = {}

    def _oauth_create(user):
        code = secrets.token_urlsafe(48)
        payload = {'user_id': str(user.id), 'exp': time.time() + 60}
        if redis_client:
            redis_client.setex(
                'oauth_exchange:' + hashlib.sha256(code.encode()).hexdigest(),
                60, json.dumps(payload)
            )
        else:
            with _oauth_lock:
                _oauth_codes[code] = payload
        return code

    def _oauth_consume(code):
        if not code:
            return None
        key = 'oauth_exchange:' + hashlib.sha256(code.encode()).hexdigest()
        raw = redis_client.get(key) if redis_client else None
        if raw:
            redis_client.delete(key)
            payload = json.loads(raw)
        else:
            with _oauth_lock:
                payload = _oauth_codes.pop(code, None)
        if not payload or float(payload.get('exp', 0)) < time.time():
            return None
        return db.session.get(User, payload.get('user_id'))

    @auth_bp.route('/oauth/exchange', methods=['POST'])
    @limiter.limit('20 per minute')
    def oauth_exchange():
        data = request.get_json(silent=True) or {}
        user = _oauth_consume(data.get('code'))
        if not user or not user.is_active:
            return jerr('Invalid or expired OAuth code.', 401)
        rt, jti = user.generate_refresh_token()
        session_manager.create_session(
            user, request.remote_addr,
            request.headers.get('User-Agent'),
            jti=jti,
            token_hash=hashlib.sha256(rt.encode()).hexdigest()
        )
        access = user.generate_auth_token(session_jti=jti)
        org = db.session.get(Organization, user.organization_id)
        return jsonify({
            'success': True, 'access_token': access, 'refresh_token': rt,
            'user': user.to_dict(),
            'organization': org.to_dict() if org else None,
            'tenant': org.to_dict() if org else None,
        }), 200

    def handle_oauth_callback(provider):
        code = request.args.get('code') or (request.get_json(silent=True) or {}).get('code')
        state = request.args.get('state') or (request.get_json(silent=True) or {}).get('state')
        error = request.args.get('error')

        if error:
            return redirect(f"{config.FRONTEND_URL}/login.html?error=oauth_denied")
        if not code:
            return redirect(f"{config.FRONTEND_URL}/login.html?error=missing_code")

        sp = oauth_service.verify_state(state)
        if not sp or sp != provider:
            logger.warning(f"Invalid OAuth state for {provider}")
            return redirect(f"{config.FRONTEND_URL}/login.html?error=invalid_state")

        try:
            ti, ui = oauth_service.exchange_code(provider, code)
            user, _ = oauth_service.create_or_update_user(provider, ui, ti)
            ec = _oauth_create(user)
            return redirect(f'{config.FRONTEND_URL}/auth-success.html?code={ec}')
        except Exception:
            logger.exception(f'{provider} OAuth failed')
            return redirect(f"{config.FRONTEND_URL}/login.html?error=auth_failed")

    @auth_bp.route('/verify-mfa', methods=['POST'])
    @limiter.limit('10 per minute')
    def mfa_login_verify():
        if not PYOTP_AVAILABLE:
            return jerr('MFA not available.', 501)
        data = request.get_json(silent=True) or {}
        ch = data.get('challenge_token') or data.get('mfa_token')
        code = str(data.get('code') or '').strip()
        if not ch or not code:
            return jerr('challenge_token and code required.', 400)
        try:
            payload = jwt.decode(
                ch, config.JWT_SECRET_KEY,
                algorithms=[config.JWT_ALGORITHM],
                options={'verify_iss': False, 'verify_aud': False}
            )
            if payload.get('type') != 'mfa_challenge':
                return jerr('Invalid challenge.', 401)
            user = db.session.get(User, payload.get('user_id'))
            if not user or not user.is_active or not user.is_mfa_enabled:
                return jerr('Invalid challenge.', 401)
            portal = str(payload.get('portal') or 'user').lower()
            if portal not in ('user', 'admin'):
                portal = 'user'
            if portal == 'admin' and user.role not in ('super_admin', 'admin'):
                return jerr('This account does not have global administrator access.', 403)
            secret = _normalize_mfa_secret(user.mfa_secret)
            if not secret:
                return jerr('MFA secret is unavailable. Please reset MFA setup.', 401)
            valid = pyotp.TOTP(secret).verify(code, valid_window=1)
            if not valid:
                try:
                    backup = json.loads(user.mfa_backup_codes or '[]')
                except Exception:
                    backup = []
                if code in backup:
                    backup.remove(code)
                    user.mfa_backup_codes = json.dumps(backup)
                    valid = True
            if not valid:
                return jerr('Invalid code.', 401)
            user.last_login_at = datetime.now(timezone.utc)
            user.last_login_ip = request.remote_addr
            user.login_attempts = 0
            user.is_locked = False
            user.locked_until = None
            db.session.commit()
            rt, jti = user.generate_refresh_token()
            session_manager.create_session(
                user, request.remote_addr,
                request.headers.get('User-Agent'),
                jti=jti,
                token_hash=hashlib.sha256(rt.encode()).hexdigest()
            )
            access = user.generate_auth_token(session_jti=jti)
            org = db.session.get(Organization, user.organization_id)
            return jsonify({
                'success': True, 'access_token': access, 'refresh_token': rt,
                'user': user.to_dict(),
                'organization': org.to_dict() if org else None,
                'tenant': org.to_dict() if org else None,
                'portal': portal,
                'redirect': '/admin/dashboard.html' if portal == 'admin' else '/dashboard.html',
            }), 200
        except jwt.ExpiredSignatureError:
            return jerr('Challenge expired.', 401)
        except jwt.InvalidTokenError:
            return jerr('Invalid challenge.', 401)
        except Exception:
            db.session.rollback()
            logger.exception('MFA login failed')
            return jerr('MFA failed.', 500)

    @auth_bp.route('/mfa/login-verify', methods=['POST'])
    def mfa_login_verify_alias():
        return mfa_login_verify()

    def _normalize_mfa_secret(raw):
        """Return an MFA secret as a normal ASCII string.

        Older SynapsePM databases may have users.mfa_secret stored as PostgreSQL
        BYTEA, which psycopg exposes as memoryview. Never call string methods
        directly on the database value.
        """
        if raw is None:
            return ''
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = bytes(raw).decode('utf-8')
            except UnicodeDecodeError:
                return ''
        return str(raw).strip().upper()

    def _mfa_secret_is_binary_column():
        """Detect legacy BYTEA/BLOB storage without changing the DB schema."""
        try:
            cols = inspect(db.engine).get_columns('users')
            for col in cols:
                if col.get('name') == 'mfa_secret':
                    typ = str(col.get('type') or '').upper()
                    return 'BYTEA' in typ or 'BLOB' in typ or 'LARGEBINARY' in typ
        except Exception:
            pass
        return False

    def _store_mfa_secret(user, secret):
        secret = _normalize_mfa_secret(secret)
        user.mfa_secret = secret.encode('utf-8') if _mfa_secret_is_binary_column() else secret

    @auth_bp.route('/mfa/setup', methods=['POST'])
    @login_required
    def mfa_setup():
        if not PYOTP_AVAILABLE:
            return jerr('MFA not available.', 501)
        if getattr(g.user, 'is_mfa_enabled', False):
            return jerr('MFA is already enabled for this account.', 409)

        # Reuse an existing pending secret so reopening the setup dialog does
        # not silently invalidate the QR code already scanned by the user.
        secret = _normalize_mfa_secret(g.user.mfa_secret)
        if not secret:
            secret = pyotp.random_base32()
            _store_mfa_secret(g.user, secret)
            db.session.commit()

        uri = pyotp.TOTP(secret).provisioning_uri(
            g.user.email,
            issuer_name=config.APP_NAME
        )
        return jsonify({
            'success': True,
            'secret': secret,
            'provisioning_uri': uri,
            'qr_code': f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={uri}"
        }), 200

    @auth_bp.route('/mfa/verify', methods=['POST'])
    @login_required
    def mfa_verify():
        if not PYOTP_AVAILABLE:
            return jerr('MFA not available.', 501)

        payload = request.get_json(silent=True) or {}
        code = str(payload.get('code') or '').strip().replace(' ', '').replace('-', '')
        if not code:
            return jerr('Code required.', 400)
        if not code.isdigit() or len(code) != 6:
            return jerr('Enter the 6-digit code from your authenticator app.', 400)
        if not g.user.mfa_secret:
            return jerr('MFA not set up. Please start setup again.', 400)

        # Allow one 30-second TOTP step of clock drift. This is important for
        # phones whose clock is a little ahead/behind the Flask host clock.
        secret = _normalize_mfa_secret(g.user.mfa_secret)
        if not secret:
            return jerr('MFA secret is unavailable. Please start MFA setup again.', 400)
        valid = pyotp.TOTP(secret).verify(code, valid_window=1)
        if valid:
            g.user.is_mfa_enabled = True
            codes = g.user.generate_mfa_backup_codes()
            db.session.commit()
            return jsonify({'success': True, 'backup_codes': codes}), 200
        return jerr(
            'Invalid code. Make sure the authenticator is using the QR code shown here and try the current 6-digit code.',
            400
        )

    @auth_bp.route('/mfa/disable', methods=['POST'])
    @login_required
    def mfa_disable():
        if not PYOTP_AVAILABLE:
            return jerr('MFA not available.', 501)
        payload = request.get_json(silent=True) or {}
        code = str(payload.get('code') or '').strip().replace(' ', '').replace('-', '')
        if not code:
            return jerr('Code required.', 400)
        if not code.isdigit() or len(code) != 6:
            return jerr('Enter the 6-digit code from your authenticator app.', 400)
        if not g.user.mfa_secret:
            return jerr('MFA not set up.', 400)
        secret = _normalize_mfa_secret(g.user.mfa_secret)
        if secret and pyotp.TOTP(secret).verify(code, valid_window=1):
            g.user.is_mfa_enabled = False
            g.user.mfa_secret = None
            g.user.mfa_backup_codes = None
            db.session.commit()
            return jsonify({'success': True}), 200
        return jerr('Invalid code.', 400)

    @auth_bp.route('/mfa/backup-codes', methods=['POST'])
    @login_required
    def mfa_backup_codes():
        if not PYOTP_AVAILABLE:
            return jerr('MFA not available.', 501)
        count = int((request.get_json() or {}).get('count') or 10)
        count = max(1, min(count, 20))
        codes = g.user.generate_mfa_backup_codes(count=count)
        db.session.commit()
        return jsonify({'success': True, 'codes': codes}), 200

    @auth_bp.route('/mfa/verify-backup', methods=['POST'])
    @login_required
    def mfa_verify_backup():
        code = (request.get_json() or {}).get('code')
        if not code:
            return jerr('Code required.', 400)
        try:
            backup = json.loads(g.user.mfa_backup_codes or '[]')
        except Exception:
            backup = []
        if code in backup:
            backup.remove(code)
            g.user.mfa_backup_codes = json.dumps(backup)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Backup code consumed.'}), 200
        return jerr('Invalid backup code.', 401)

    app.register_blueprint(auth_bp)

    # ============================================================
    # USERS BLUEPRINT
    # ============================================================

    users_bp = Blueprint('users', __name__, url_prefix='/api/v1/users')

    @users_bp.route('/profile', methods=['GET'])
    @login_required
    def profile_get():
        return jsonify({'success': True, 'user': g.user.to_dict()}), 200

    @users_bp.route('/profile', methods=['PUT'])
    @login_required
    def profile_put():
        data = request.get_json() or {}
        for f in ['first_name', 'last_name', 'display_name', 'job_title', 'phone',
                  'timezone', 'language', 'notification_preferences', 'ui_preferences']:
            if f in data:
                setattr(g.user, f, data[f])
        if 'name' in data:
            g.user.display_name = data['name']
        if 'company' in data and hasattr(g, 'organization') and g.organization:
            g.organization.name = data['company']
        db.session.commit()
        try:
            broadcast_both('user_updated', {'user': g.user.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True, 'user': g.user.to_dict()}), 200

    @users_bp.route('/avatar', methods=['POST'])
    @login_required
    def avatar_post():
        if 'avatar' not in request.files:
            return jerr('No avatar file.', 400)
        file = request.files['avatar']
        if not file.filename:
            return jerr('No file.', 400)
        ext = Path(file.filename).suffix.lower()
        if ext not in {'.png', '.jpg', '.jpeg', '.gif'}:
            return jerr('Invalid format.', 400)
        if not validate_image_upload(file):
            return jerr('Invalid image.', 400)
        d = os.path.join(config.UPLOAD_FOLDER, 'avatars')
        os.makedirs(d, exist_ok=True)
        fn = f"{uuid.uuid4().hex}{ext}"
        fp = os.path.join(d, fn)
        file.save(fp)
        g.user.avatar_url = f"/uploads/avatars/{fn}"
        db.session.commit()
        try:
            broadcast_both('user_updated', {'user': g.user.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True, 'avatar_url': g.user.avatar_url}), 200

    @users_bp.route('/avatar', methods=['DELETE'])
    @login_required
    def avatar_del():
        g.user.avatar_url = None
        db.session.commit()
        try:
            broadcast_both('user_updated', {'user': g.user.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True}), 200

    @users_bp.route('/preferences', methods=['GET'])
    @login_required
    def prefs_get():
        return jsonify({
            'success': True,
            'preferences': g.user.ui_preferences or {},
            'notifications': (g.user.ui_preferences or {}).get('notifications', {})
        }), 200

    @users_bp.route('/preferences', methods=['PUT'])
    @login_required
    def prefs_put():
        data = request.get_json() or {}
        current = g.user.ui_preferences or {}
        merged = {**current, **data}
        g.user.ui_preferences = merged
        db.session.commit()
        return jsonify({'success': True, 'preferences': merged}), 200

    @users_bp.route('/api-keys', methods=['GET'])
    @login_required
    def keys_get():
        ks = APIKey.query.filter_by(user_id=g.user.id, is_deleted=False).all()
        return jsonify({'success': True, 'keys': [k.to_dict() for k in ks],
                        'api_keys': [k.to_dict() for k in ks]}), 200

    @users_bp.route('/api-keys', methods=['POST'])
    @login_required
    def keys_post():
        data = request.get_json() or {}
        ak = APIKey(
            name=data.get('name', 'API Key'),
            user_id=g.user.id, organization_id=g.user.organization_id,
            permissions=data.get('permissions', ['read']),
            rate_limit=max(1, min(int(data.get('rate_limit', 100)), 10000))
        )
        key = ak.generate_key()
        db.session.add(ak)
        db.session.commit()
        return jsonify({'success': True, 'api_key': ak.to_dict(), 'key': key}), 201

    @users_bp.route('/api-keys/<key_id>', methods=['DELETE'])
    @login_required
    def keys_del(key_id):
        ak = APIKey.query.filter_by(id=key_id, user_id=g.user.id).first_or_404()
        ak.soft_delete(g.user.id)
        db.session.commit()
        return jsonify({'success': True}), 200

    app.register_blueprint(users_bp)

    # ============================================================
    # USER LEGACY BLUEPRINT
    # ============================================================

    ul_bp = Blueprint('user_legacy', __name__, url_prefix='/api/v1/user')

    @ul_bp.route('/profile', methods=['GET'])
    @login_required
    def ul_profile_get():
        return jsonify({'success': True, 'user': g.user.to_dict()}), 200

    @ul_bp.route('/profile', methods=['PUT'])
    @login_required
    def ul_profile_put():
        return profile_put()

    @ul_bp.route('/avatar', methods=['POST'])
    @login_required
    def ul_avatar_post():
        return avatar_post()

    @ul_bp.route('/avatar', methods=['DELETE'])
    @login_required
    def ul_avatar_del():
        return avatar_del()

    @ul_bp.route('/preferences', methods=['GET'])
    @login_required
    def ul_prefs_get():
        return prefs_get()

    @ul_bp.route('/preferences', methods=['PUT'])
    @login_required
    def ul_prefs_put():
        return prefs_put()

    @ul_bp.route('/billing', methods=['GET'])
    @login_required
    def ul_billing():
        org = g.organization
        return jsonify({
            'success': True, 'plan': org.plan,
            'subscription_status': org.subscription_status,
            'trial_ends_at': org.trial_ends_at.isoformat() if org.trial_ends_at else None,
            'trial_days_remaining': org.trial_days_remaining,
            'is_trial_active': org.is_trial_active,
            'is_trial_expired': org.is_trial_expired(),
            'max_users': org.max_users, 'max_machines': org.max_machines,
            'max_api_calls': org.max_api_calls,
            'max_storage_gb': float(org.max_storage_gb) if org.max_storage_gb else 0,
            'available_plans': config.PLANS,
            'gateways': payment_processor.get_gateways(),
            'gateway_status': payment_processor.gateway_status()
        }), 200

    @ul_bp.route('/2fa/status', methods=['GET'])
    @login_required
    def ul_2fa_status():
        return jsonify({
            'success': True, 'enabled': bool(g.user.is_mfa_enabled),
            'available': PYOTP_AVAILABLE
        }), 200

    @ul_bp.route('/2fa/toggle', methods=['POST'])
    @login_required
    def ul_2fa_toggle():
        data = request.get_json() or {}
        enabled = bool(data.get('enabled'))
        if not PYOTP_AVAILABLE:
            return jerr('2FA not available on this server.', 501)
        if enabled:
            if not _normalize_mfa_secret(g.user.mfa_secret):
                _store_mfa_secret(g.user, pyotp.random_base32())
            g.user.is_mfa_enabled = True
        else:
            g.user.is_mfa_enabled = False
            g.user.mfa_secret = None
            g.user.mfa_backup_codes = None
        db.session.commit()
        return jsonify({'success': True, 'enabled': g.user.is_mfa_enabled}), 200

    @ul_bp.route('/change-password', methods=['POST'])
    @login_required
    def ul_change_password():
        return change_password()

    @ul_bp.route('/delete', methods=['DELETE'])
    @login_required
    def ul_delete_account():
        try:
            user = g.user
            now = datetime.now(timezone.utc)
            # Soft-delete first so a 30-day recovery/retention window is possible.
            user.is_active = False
            user.status = 'deleted_pending'
            user.deactivated_at = now
            user.email = f'deleted+{user.id}@invalid.synapsepm.local'
            user.username = f'deleted_{user.id}'
            user.first_name = None; user.last_name = None; user.display_name = None
            user.phone = None; user.avatar_url = None
            user.mfa_secret = None; user.mfa_backup_codes = None
            session_manager.revoke_all_sessions(user.id)
            jwt_blacklist.revoke_all_user_tokens(user.id)
            # Remove local personal uploads/reports where safely identifiable.
            for base in [Path(config.UPLOAD_FOLDER) / 'avatars', Path(config.UPLOAD_FOLDER) / 'resumes']:
                for candidate in base.glob(f'*{user.id}*'):
                    try:
                        candidate.unlink(missing_ok=True)
                    except Exception:
                        pass
            for report in Report.query.filter_by(user_id=user.id).all():
                if report.file_path and os.path.exists(report.file_path):
                    try: os.remove(report.file_path)
                    except Exception: pass
                report.file_path = None
                report.status = 'deleted'
            for payment in Payment.query.filter_by(organization_id=g.organization.id).all():
                pd = payment.payment_data or {}
                pd['customer_anonymized_at'] = now.isoformat()
                payment.payment_data = pd
                payment.customer_email = 'deleted@invalid.synapsepm.local'
                payment.customer_name = 'Deleted User'
            db.session.commit()
            return jsonify({'success': True, 'message': 'Account scheduled for permanent deletion after the retention period.'}), 200
        except Exception:
            db.session.rollback()
            return jerr('Delete failed.', 500)

    @ul_bp.route('/api-keys', methods=['GET'])
    @login_required
    def ul_keys_get():
        return keys_get()

    @ul_bp.route('/api-keys', methods=['POST'])
    @login_required
    def ul_keys_post():
        return keys_post()

    @ul_bp.route('/api-keys/<key_id>', methods=['DELETE'])
    @login_required
    def ul_keys_del(key_id):
        return keys_del(key_id)

    @ul_bp.route('/onboarding/status', methods=['GET'])
    @login_required
    def onboarding_status():
        machines = Machine.query.filter_by(organization_id=g.organization.id, is_deleted=False).all()
        machine_ids = [m.id for m in machines]
        sensor_count = SensorData.query.filter(SensorData.machine_id.in_(machine_ids)).count() if machine_ids else 0
        prediction_count = Prediction.query.join(Machine).filter(Machine.organization_id == g.organization.id).count()
        alert_count = Alert.query.join(Machine).filter(Machine.organization_id == g.organization.id, Alert.status == 'active').count()
        report_count = Report.query.filter_by(organization_id=g.organization.id).count()
        steps = {
            'create_machine': len(machines) > 0,
            'simulate_or_ingest': sensor_count > 0,
            'run_prediction': prediction_count > 0,
            'see_alert': alert_count > 0,
            'download_report': report_count > 0,
        }
        completed = sum(1 for v in steps.values() if v)
        return jsonify({'success': True, 'steps': steps, 'completed': completed, 'total': len(steps), 'next_step': next((k for k,v in steps.items() if not v), None)}), 200

    @ul_bp.route('/export', methods=['GET'])
    @login_required
    def ul_export_data():
        try:
            root = Path(config.DOWNLOAD_FOLDER).resolve()
            root.mkdir(parents=True, exist_ok=True)
            fp = root / f'user_export_{g.user.id}_{int(time.time())}.zip'
            payload = {
                'user': g.user.to_dict(),
                'organization': g.organization.to_dict(),
                'machines': [m.to_dict() for m in Machine.query.filter_by(organization_id=g.organization.id, is_deleted=False).all()],
                'predictions': [p.to_dict() for p in Prediction.query.join(Machine).filter(Machine.organization_id == g.organization.id).all()],
                'alerts': [a.to_dict() for a in Alert.query.join(Machine).filter(Machine.organization_id == g.organization.id).all()],
                'reports': [r.to_dict() for r in Report.query.filter_by(organization_id=g.organization.id).all()],
            }
            with zipfile.ZipFile(fp, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('data.json', json.dumps(json_safe(payload), indent=2))
            return send_file(fp, as_attachment=True, download_name=fp.name, mimetype='application/zip', max_age=0)
        except Exception:
            logger.exception('User export failed')
            return jerr('Data export failed.', 500)

    app.register_blueprint(ul_bp)

    # ============================================================
    # MACHINES BLUEPRINT
    # ============================================================

    machines_bp = Blueprint('machines', __name__, url_prefix='/api/v1/machines')

    @machines_bp.route('', methods=['GET'])
    @login_required
    def list_machines():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            status = request.args.get('status')
            search = request.args.get('search')
            q = Machine.query.filter_by(
                organization_id=g.organization.id, is_deleted=False
            ).filter(Machine.name != '__dataset__')
            if status:
                q = q.filter_by(status=status)
            if search:
                q = q.filter(or_(
                    Machine.name.ilike(f'%{search}%'),
                    Machine.serial_number.ilike(f'%{search}%')
                ))
            q = q.order_by(Machine.created_at.desc())
            result = paginate(q, page, per_page)
            result['machines'] = result['items']
            return jsonify({'success': True, **result}), 200
        except Exception as e:
            logger.exception('List machines failed')
            return jsonify({
                'success': False, 'error': str(e),
                'items': [], 'machines': [], 'total': 0
            }), 500

    @machines_bp.route('', methods=['POST'])
    @login_required
    def create_machine():
        try:
            data = request.get_json() or {}
            if bool(data.get('simulation', False)) or str(data.get('connection') or data.get('connection_method') or '').lower() == 'simulated':
                return jerr('Synthetic machine creation is disabled in production. Submit real sensor readings or configure MQTT/Device API telemetry.', 410,
                            error_code='SIMULATION_DISABLED')
            name = data.get('name')
            mt_raw = data.get('machine_type') or data.get('type')
            # FIX: sanitize machine_type to avoid native enum mismatch
            mt = re.sub(r'[^A-Za-z0-9_\-]', '', str(mt_raw or '')).lower()[:100]
            if not name:
                return jerr('Name required.', 400)
            if not mt:
                return jerr('Machine type required.', 400)
            count = Machine.query.filter_by(
                organization_id=g.organization.id, is_deleted=False
            ).filter(Machine.name != '__dataset__').count()
            if count >= g.organization.max_machines:
                return jerr(
                    f'Machine limit reached. Your plan allows '
                    f'{g.organization.max_machines} machine(s). Upgrade your plan to add more.',
                    403,
                    limit_reached=True,
                    current_plan=str(g.organization.plan or 'free').lower(),
                    max_machines=int(g.organization.max_machines),
                )
            dataset_family = (data.get('dataset_family') or '').strip().lower() or None
            machine_data = dict(data.get('machine_data', {}) or {})

            # If no family was supplied, infer one from machine_type so the ML
            # engine has a useful family hint at prediction time. Prefer an
            # exact/contains match, then use conservative aliases.
            if not dataset_family and mt:
                families = list(ml_engine.all_by_family.keys())
                for fam in families:
                    fam_l = str(fam).strip().lower()
                    if fam_l == mt or mt in fam_l or fam_l.endswith('_' + mt):
                        dataset_family = fam_l
                        break
                if not dataset_family:
                    family_aliases = {
                        'turbine': ['turbine', 'industrial'],
                        'pump': ['pump', 'industrial'],
                        'compressor': ['compressor', 'industrial'],
                        'motor': ['motor', 'industrial'],
                        'generator': ['generator', 'industrial'],
                        'ct': ['ct', 'medical', 'healthcare'],
                        'mri': ['mri', 'medical', 'healthcare'],
                        'xray': ['xray', 'x_ray', 'medical'],
                        'server': ['server', 'it'],
                        'laptop': ['laptop', 'it'],
                    }
                    hints = family_aliases.get(mt, [mt])
                    for fam in families:
                        fam_l = str(fam).strip().lower()
                        if any(str(h).lower() in fam_l for h in hints):
                            dataset_family = fam_l
                            break

            if dataset_family:
                machine_data['dataset_family'] = dataset_family
            m = Machine(
                name=name, machine_type=mt,
                manufacturer=data.get('manufacturer', ''),
                model=data.get('model', ''),
                serial_number=data.get('serial_number', ''),
                location=data.get('location', ''),
                floor=data.get('floor', ''),
                department=data.get('department', ''),
                status=data.get('status', 'offline'),
                health=100,
                machine_data=machine_data,
                organization_id=g.organization.id,
                owner_id=g.user.id
            )
            db.session.add(m)
            db.session.commit()
            if bool(data.get('simulation', False)):
                for _ in range(min(30, int(data.get('simulation_points', 30)))):
                    db.session.add(SensorData(
                        machine_id=m.id,
                        temperature=random.uniform(50, 90),
                        vibration=random.uniform(1, 8),
                        pressure=random.uniform(40, 80),
                        source='simulation'
                    ))
                m.status = 'online'
                db.session.commit()
            try:
                log_audit('create_machine', 'machine', m.id, {'name': m.name})
            except Exception:
                pass
            try:
                broadcast_both('machine_created', {'machine': m.to_dict()},
                               org_id=g.organization.id)
            except Exception:
                pass
            return jsonify({'success': True, 'machine': m.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            logger.exception('Create machine failed')
            return jsonify({'success': False, 'error': str(e)}), 500

    @machines_bp.route('/<machine_id>', methods=['GET'])
    @login_required
    def get_machine(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()
        return jsonify({'success': True, 'machine': m.to_dict()}), 200

    @machines_bp.route('/<machine_id>/sensor-contract', methods=['GET'])
    @login_required
    def machine_sensor_contract(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id, organization_id=g.organization.id, is_deleted=False
        ).first_or_404()
        family = (m.machine_data or {}).get('dataset_family')
        model_pool = (
            ml_engine.by_family.get(family, [])
            if getattr(config, 'MODEL_REQUIRE_VALIDATED', False)
            else ml_engine.all_by_family.get(family, [])
        ) if family else []
        model_info = next((
            ml_engine.models[key] for key in model_pool
            if key in ml_engine.models and ml_engine.models[key].get('features')
        ), None)
        fallback = sensor_catalog_for(m.machine_type)
        return jsonify({
            'success': True,
            'machine_id': str(m.id),
            'machine_type': m.machine_type,
            'dataset_family': family,
            'required_features': model_info.get('features') if model_info else fallback,
            'sequence_length': int((model_info or {}).get('sequence_length') or 1),
            'training_ranges': (model_info or {}).get('training_ranges') or {},
            'has_trained_model': bool(model_info),
            'fallback_catalog': fallback,
        }), 200

    @machines_bp.route('/<machine_id>/telemetry-status', methods=['GET'])
    @login_required
    def machine_telemetry_status(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id, organization_id=g.organization.id, is_deleted=False
        ).first_or_404()
        latest = (
            SensorData.query.filter_by(machine_id=m.id)
            .order_by(SensorData.created_at.desc()).first()
        )
        age_seconds = None
        if latest and latest.created_at:
            try:
                age_seconds = max(
                    0.0,
                    (datetime.now(timezone.utc) - ensure_aware(latest.created_at)).total_seconds()
                )
            except Exception:
                age_seconds = None
        return jsonify({
            'success': True,
            'machine': m.to_dict(),
            'latest': latest.to_dict() if latest else None,
            'age_seconds': age_seconds,
            'is_live': bool(age_seconds is not None and age_seconds <= 300),
            'telemetry_state': (m.machine_data or {}).get('telemetry_state'),
        }), 200

    @machines_bp.route('/<machine_id>', methods=['PUT'])
    @login_required
    def update_machine(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()
        data = request.get_json() or {}
        allowed_statuses = {'online', 'offline', 'maintenance', 'blocked'}
        for f in ['name', 'machine_type', 'manufacturer', 'model',
                  'serial_number', 'location', 'floor', 'department',
                  'status', 'health', 'machine_data']:
            if f in data:
                if f == 'machine_type':
                    data[f] = re.sub(r'[^A-Za-z0-9_\-]', '', str(data[f] or '')).lower()[:100]
                if f == 'status':
                    status_value = str(data[f] or '').lower()
                    if status_value not in allowed_statuses:
                        return jerr('Invalid machine status.', 400)
                    m.is_blocked = status_value == 'blocked'
                    if m.is_blocked:
                        m.blocked_at = datetime.now(timezone.utc)
                        m.blocked_by = g.user.id
                    else:
                        m.blocked_at = None
                        m.blocked_by = None
                setattr(m, f, data[f])
        if 'type' in data and 'machine_type' not in data:
            m.machine_type = re.sub(r'[^A-Za-z0-9_\-]', '', str(data['type'] or '')).lower()[:100]
        db.session.commit()
        try:
            broadcast_both('machine_updated', {'machine': m.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True, 'machine': m.to_dict()}), 200

    @machines_bp.route('/<machine_id>', methods=['DELETE'])
    @login_required
    def delete_machine(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()
        m.soft_delete(g.user.id)
        db.session.commit()
        try:
            broadcast_both('machine_deleted', {'machine_id': machine_id},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True}), 200

    @machines_bp.route('/<machine_id>/status', methods=['PATCH'])
    @login_required
    def update_machine_status(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()
        data = request.get_json() or {}
        m.status = data.get('status') or m.status
        db.session.commit()
        try:
            broadcast_both('machine_updated', {'machine': m.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True, 'machine': m.to_dict()}), 200

    @machines_bp.route('/<machine_id>/connect', methods=['POST'])
    @login_required
    def connect_machine(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()

        data = request.get_json() or {}
        connection = (data.get('connection') or 'manual').lower()
        endpoint = (data.get('endpoint') or '').strip()

        verification = {
            'method': connection,
            'ok': False,
            'message': '',
            'checked_at': datetime.now(timezone.utc).isoformat(),
        }

        # Only expose integrations that this deployment can actually receive.
        # A successful TCP port check is NOT treated as a successful industrial
        # protocol handshake or proof that sensor telemetry is flowing.
        if connection == 'manual':
            verification['ok'] = True
            verification['message'] = 'Manual entry selected; validating operator-entered measurements.'
        elif connection == 'mqtt':
            mqtt_connected = False
            try:
                mqtt_connected = bool(_mqtt_client and _mqtt_client.is_connected())
            except Exception:
                mqtt_connected = False
            if not config.ENABLE_MQTT or not mqtt_connected:
                verification['message'] = 'The server MQTT subscriber is not connected. Configure ENABLE_MQTT and the broker settings, then restart the service.'
                return jerr(verification['message'], 503, verification=verification)
            topic_prefix = str(config.MQTT_TOPIC_PREFIX or 'synapsepm').strip('/')
            expected_topic = f'{topic_prefix}/{m.id}/sensor'
            verification['ok'] = True
            verification['waiting_for_telemetry'] = True
            verification['topic'] = expected_topic
            verification['message'] = f'MQTT subscriber is connected. Waiting for real telemetry on {expected_topic}; the machine will remain offline until a valid message arrives.'
        elif connection == 'api':
            verification['ok'] = True
            verification['waiting_for_telemetry'] = True
            verification['message'] = 'Device API configured. Create a per-machine device key and POST real sensor readings to this machine sensor-data endpoint. The machine remains offline until a valid reading arrives.'
        elif connection in ('cable', 'modbus', 'opcua', 'websocket'):
            # This verifies TCP reachability only; it is not a Modbus/OPC-UA/
            # WebSocket protocol handshake and never claims telemetry is live.
            host = None
            port = None
            try:
                if '://' in endpoint:
                    parsed_endpoint = urlparse(endpoint)
                    host = parsed_endpoint.hostname
                    port = parsed_endpoint.port
                elif ':' in endpoint:
                    host, port_text = endpoint.rsplit(':', 1)
                    port = int(port_text)
                default_ports = {
                    'modbus': 502, 'opcua': 4840, 'websocket': 443, 'cable': 502
                }
                if not port:
                    port = default_ports.get(connection)
                if host:
                    host = host.strip().strip('[]')
            except (TypeError, ValueError):
                host, port = None, None
            if not host or not port or not (1 <= int(port) <= 65535):
                return jerr(
                    f'{connection.upper()} requires a reachable host:port endpoint.',
                    400, verification=verification,
                    supported_connections=['manual', 'mqtt', 'api', 'cable', 'modbus', 'opcua', 'websocket']
                )
            try:
                # Refuse loopback/link-local/private literal IPs to avoid exposing
                # internal services through user-controlled connection checks.
                import ipaddress
                try:
                    ip = ipaddress.ip_address(host)
                    if not ip.is_global:
                        raise ValueError('Private, loopback, and link-local IPs are not allowed.')
                except ValueError as ip_error:
                    if 'not allowed' in str(ip_error):
                        raise
                with socket.create_connection((host, int(port)), timeout=5):
                    pass
                verification['ok'] = True
                verification['waiting_for_telemetry'] = True
                verification['message'] = (
                    f'TCP endpoint {host}:{port} is reachable. This is not a protocol '
                    f'handshake; the machine remains offline until real telemetry arrives.'
                )
            except Exception as exc:
                logger.info('Machine TCP endpoint check failed for machine=%s method=%s: %s',
                            m.id, connection, type(exc).__name__)
                verification['ok'] = False
                verification['message'] = f'Could not verify the configured TCP endpoint ({type(exc).__name__}).'
                return jerr(verification['message'], 502, verification=verification)
        else:
            supported = 'manual, mqtt, api, cable, modbus, opcua, websocket'
            return jerr(
                f'{connection.upper()} is not enabled in this deployment. Supported connection modes are: {supported}.',
                501, verification=verification,
                supported_connections=['manual', 'mqtt', 'api', 'cable', 'modbus', 'opcua', 'websocket']
            )

        # Never mark a network integration online merely because configuration
        # succeeded. Keep it online only when recent real telemetry is already stored.
        latest_sensor = SensorData.query.filter_by(machine_id=m.id).order_by(SensorData.created_at.desc()).first()
        recent_sensor = False
        if latest_sensor and latest_sensor.created_at:
            try:
                recent_sensor = (datetime.now(timezone.utc) - ensure_aware(latest_sensor.created_at)).total_seconds() <= 300
            except Exception:
                recent_sensor = False
        m.status = 'online' if connection in ('mqtt', 'api', 'cable', 'modbus', 'opcua', 'websocket') and recent_sensor else 'offline'
        m.machine_data = {
            **(m.machine_data or {}),
            'connection': connection,
            'endpoint': None,
            'simulated': False,
            'telemetry_state': 'receiving' if recent_sensor else ('awaiting_first_reading' if connection in ('mqtt', 'api', 'cable', 'modbus', 'opcua', 'websocket') else 'manual_validation'),
            'verified_at': verification['checked_at'],
            'last_verification': verification,
        }
        if connection in ('mqtt', 'api', 'cable', 'modbus', 'opcua', 'websocket') and recent_sensor:
            verification['waiting_for_telemetry'] = False
            verification['message'] = 'Connection settings checked; recent real sensor telemetry exists.'
        supplied_sensors = data.get('sensors') or data.get('sensor_schema') or {}
        sensor_units = data.get('sensor_units') or data.get('units') or {}
        if isinstance(supplied_sensors, list):
            supplied_sensors = {str(x): {} for x in supplied_sensors}
        if not isinstance(supplied_sensors, dict):
            supplied_sensors = {}
        m.machine_data['sensor_contract'] = {
            'sensors': sorted(str(x) for x in supplied_sensors.keys()),
            'units': {str(k): str(v) for k, v in (sensor_units or {}).items()},
            'declared_at': datetime.now(timezone.utc).isoformat(),
        }
        # Manual entry must use operator-supplied measurements. Never create
        # made-up 65/3/60 baselines when a machine is connected.
        initial_readings = data.get('initial_readings') or data.get('readings') or []

        # Accept scalar sensor fields at the top level as a single manual row.
        # This keeps POST /connect tolerant of simple clients that send
        # {temperature: 72, vibration: 2.1, pressure: 1.2}.
        if not initial_readings:
            top_level = {
                key: data.get(key)
                for key in ('temperature', 'vibration', 'pressure')
                if data.get(key) is not None
            }
            if top_level:
                initial_readings = [top_level]

        if isinstance(initial_readings, dict):
            initial_readings = [initial_readings]
        if initial_readings and not isinstance(initial_readings, list):
            return jerr('initial_readings must be a list of timestamp rows (each row maps feature names to numeric values).', 400)
        clean_rows = []
        for row_index, row in enumerate(initial_readings or [], start=1):
            if not isinstance(row, dict) or not row:
                return jerr(f'Manual sensor time step {row_index} must contain feature values.', 400)
            clean_row = {}
            for feature_name, raw_value in row.items():
                feature_name = str(feature_name).strip()
                if not feature_name or raw_value is None or isinstance(raw_value, bool):
                    return jerr(f'Invalid manual sensor value for {feature_name or "unnamed feature"} at time step {row_index}.', 400)
                try:
                    numeric_value = float(raw_value)
                except (TypeError, ValueError):
                    return jerr(f'Manual sensor value for {feature_name} at time step {row_index} must be numeric.', 400)
                if not __import__('math').isfinite(numeric_value):
                    return jerr(f'Manual sensor value for {feature_name} at time step {row_index} must be finite.', 400)
                clean_row[feature_name] = numeric_value
            clean_rows.append(clean_row)

        if connection == 'manual' and not clean_rows:
            db.session.rollback()
            return jerr('Manual entry requires actual measured sensor values. No values were supplied, so the machine was not connected.', 400,
                        error_code='MANUAL_READINGS_REQUIRED')

        if connection == 'manual' and clean_rows:
            def _norm_sensor_key(value):
                return re.sub(r'[^a-z0-9]+', '_', str(value).lower()).strip('_')
            family_name = str((m.machine_data or {}).get('dataset_family') or '').strip().lower()
            family_ids = ml_engine.by_family.get(family_name, []) if config.MODEL_REQUIRE_VALIDATED else ml_engine.all_by_family.get(family_name, [])
            family_info = next((ml_engine.models[mid] for mid in family_ids if mid in ml_engine.models and ml_engine.models[mid].get('features')), None)
            if not family_info:
                verification['manual_feature_contract'] = 'unavailable'
                verification['manual_warning'] = (
                    f'No trained model with a named feature contract is registered for '
                    f'dataset_family="{family_name or "unset"}". Readings will be stored, '
                    'but predictions will abstain until a compatible model is deployed.'
                )
            else:
                required_features = [str(x) for x in (family_info.get('features') or [])]
                required_sequence = max(1, int(family_info.get('sequence_length') or 1))
                if len(clean_rows) < required_sequence:
                    return jerr(f'This trained model requires {required_sequence} chronological readings; received {len(clean_rows)}.', 400,
                                error_code='MANUAL_SEQUENCE_TOO_SHORT', required_readings=required_sequence, received_readings=len(clean_rows))
                for row_index, row_values in enumerate(clean_rows, start=1):
                    row_keys = {_norm_sensor_key(k) for k in row_values}
                    missing_features = [f for f in required_features if _norm_sensor_key(f) not in row_keys]
                    if missing_features:
                        return jerr(f'Reading {row_index} is missing required model features: {missing_features[:20]}', 400,
                                    error_code='MANUAL_FEATURES_MISSING', reading_index=row_index, missing_features=missing_features[:50])
            aliases = {
                'temperature': ('temperature', 'temperature_c', 'temp', 'temp_c', 'temperature_celsius'),
                'vibration': ('vibration', 'vibration_rms', 'vibration_mm_s', 'vib'),
                'pressure': ('pressure', 'pressure_psi', 'pressure_bar', 'pressure_kpa'),
            }
            def _first_sensor(row, keys):
                normalized = {_norm_sensor_key(k): v for k, v in row.items()}
                for key in keys:
                    if key in normalized:
                        return normalized[key]
                return None
            for row_values in clean_rows:
                temperature = _first_sensor(row_values, aliases['temperature'])
                vibration = _first_sensor(row_values, aliases['vibration'])
                pressure = _first_sensor(row_values, aliases['pressure'])
                db.session.add(SensorData(
                    machine_id=m.id, temperature=temperature, vibration=vibration,
                    pressure=pressure, readings=row_values, source='manual_entry'
                ))
            latest = clean_rows[-1]
            temperature = _first_sensor(latest, aliases['temperature'])
            vibration = _first_sensor(latest, aliases['vibration'])
            pressure = _first_sensor(latest, aliases['pressure'])
            if temperature is not None: m.temperature = max(-50.0, min(500.0, temperature))
            if vibration is not None: m.vibration = max(0.0, min(100.0, vibration))
            if pressure is not None: m.pressure = max(0.0, min(1000.0, pressure))
            m.machine_data = {**(m.machine_data or {}), 'latest_readings': latest,
                              'manual_readings_count': len(clean_rows),
                              'sensor_contract': {**((m.machine_data or {}).get('sensor_contract') or {}),
                                                  'sensors': sorted(str(k) for k in latest.keys()),
                                                  'declared_at': datetime.now(timezone.utc).isoformat()}}
            m.status = 'online'
            m.last_activity_at = datetime.now(timezone.utc)
        elif connection == 'manual':
            # A configured machine with no initial readings is not falsely
            # represented as having live sensor data.
            m.status = 'offline'
            verification['message'] = 'Machine saved; awaiting the first manual sensor reading.'
        db.session.commit()

        try:
            log_audit('connect_machine', 'machine', m.id, verification)
        except Exception:
            pass

        try:
            broadcast_both('machine_updated', {'machine': m.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass

        return jsonify({
            'success': True,
            'machine': m.to_dict(),
            'verification': verification,
        }), 200

    @machines_bp.route('/<machine_id>/api-keys', methods=['POST'])
    @login_required
    def create_device_key(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()

        data = request.get_json() or {}
        ak = MachineAPIKey(
            machine_id=m.id,
            organization_id=g.organization.id,
            name=data.get('name') or f'{m.name} device key',
        )
        raw_key = ak.generate_key()
        db.session.add(ak)
        db.session.commit()

        return jsonify({
            'success': True,
            'api_key': ak.to_dict(),
            'key': raw_key,
            'note': 'Save this key now — it will not be shown again.',
            'usage': {
                'curl': (
                    f'curl -X POST {config.APP_URL}/api/v1/machines/{m.id}/sensor-data '
                    f'-H "X-Device-Key: {raw_key}" '
                    f'-H "Content-Type: application/json" '
                    f'-d \'{{"temperature":72.5,"vibration":3.2,"pressure":88.1}}\''
                ),
                'mqtt_topic': f'{config.MQTT_TOPIC_PREFIX}/{m.uuid}/sensor',
            },
        }), 201

    @machines_bp.route('/<machine_id>/api-keys', methods=['GET'])
    @login_required
    def list_device_keys(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()
        keys = MachineAPIKey.query.filter_by(
            machine_id=m.id, is_deleted=False
        ).order_by(MachineAPIKey.created_at.desc()).all()
        return jsonify({
            'success': True,
            'keys': [k.to_dict() for k in keys],
        }), 200

    @machines_bp.route('/<machine_id>/api-keys/<key_id>', methods=['DELETE'])
    @login_required
    def revoke_device_key(machine_id, key_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        m = Machine.query.filter_by(
            id=machine_id,
            organization_id=g.organization.id,
            is_deleted=False
        ).first_or_404()
        ak = MachineAPIKey.query.filter_by(
            id=key_id, machine_id=m.id, is_deleted=False
        ).first_or_404()
        ak.is_deleted = True
        ak.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'success': True}), 200

    @machines_bp.route('/<machine_id>/sensor-data', methods=['POST'])
    def add_sensor(machine_id):
        m, user, org, err = machine_iot_auth(machine_id)
        if err:
            return err

        data = request.get_json() or {}
        for scalar_name in ('temperature', 'vibration', 'pressure'):
            if scalar_name in data and data[scalar_name] is not None:
                if isinstance(data[scalar_name], bool):
                    return jerr(f'{scalar_name} must be a finite numeric value.', 400)
                try:
                    scalar_value = float(data[scalar_name])
                except (TypeError, ValueError):
                    return jerr(f'{scalar_name} must be a finite numeric value.', 400)
                if not math.isfinite(scalar_value):
                    return jerr(f'{scalar_name} must be a finite numeric value.', 400)
                data[scalar_name] = scalar_value
        supplied_readings = data.get('readings')
        has_scalar_reading = any(
            key in data and data.get(key) is not None and not isinstance(data.get(key), bool)
            for key in ('temperature', 'vibration', 'pressure')
        )
        if not (isinstance(supplied_readings, dict) and len(supplied_readings) > 0) and not has_scalar_reading:
            return jerr('No sensor data provided. Send at least one actual numeric reading.', 400)

        raw_readings = data.get('readings', {}) or {}
        if not isinstance(raw_readings, dict):
            return jerr('readings must be an object mapping feature names to numeric values.', 400)
        clean_readings = {}
        for feature_name, raw_value in raw_readings.items():
            if not str(feature_name).strip() or isinstance(raw_value, bool) or raw_value is None:
                return jerr(f'Invalid sensor value for feature {feature_name!r}.', 400)
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                return jerr(f'Sensor value for {feature_name} must be numeric.', 400)
            if not math.isfinite(numeric_value):
                return jerr(f'Sensor value for {feature_name} must be finite.', 400)
            clean_readings[str(feature_name)] = numeric_value
        s = SensorData(
            machine_id=m.id,
            temperature=data.get('temperature'),
            vibration=data.get('vibration'),
            pressure=data.get('pressure'),
            readings=clean_readings,
            source='device_api' if (request.headers.get('X-Device-Key') or request.headers.get('X-API-Key')) else 'rest',
        )

        # Clamp external readings before persistence. This prevents malformed
        # device values from poisoning rolling statistics or model inputs.
        def _clamp(v, lo, hi):
            try:
                if v is None:
                    return None
                f = float(v)
                return max(lo, min(hi, f))
            except (TypeError, ValueError):
                return None

        s.temperature = _clamp(s.temperature, -50, 500)
        s.vibration = _clamp(s.vibration, 0, 100)
        s.pressure = _clamp(s.pressure, 0, 1000)
        db.session.add(s)
        if s.temperature is not None:
            m.temperature = s.temperature
        if s.vibration is not None:
            m.vibration = s.vibration
        if s.pressure is not None:
            m.pressure = s.pressure
        m.status = 'online'
        m.machine_data = {**(m.machine_data or {}), 'telemetry_state': 'receiving', 'last_telemetry_at': datetime.now(timezone.utc).isoformat()}
        m.last_activity_at = datetime.now(timezone.utc)

        if s.temperature is not None and (s.temperature > 95 or s.temperature < 30):
            s.is_anomaly = True
            s.anomaly_score = 0.8
            s.anomaly_type = 'temperature_outlier'
            db.session.add(Alert(
                machine_id=m.id, organization_id=m.organization_id, title='Temperature Anomaly',
                message=f'{m.name}: {s.temperature}°C',
                severity=_alert_severity_for_db('warning'), category='sensor', source='rule',
            ))
        if s.vibration is not None and s.vibration > 10:
            s.is_anomaly = True
            s.anomaly_score = 0.9
            s.anomaly_type = 'vibration_outlier'
            db.session.add(Alert(
                machine_id=m.id, organization_id=m.organization_id, title='Vibration Anomaly',
                message=f'{m.name}: {s.vibration}mm/s',
                severity=_alert_severity_for_db('warning'), category='sensor', source='rule',
            ))

        db.session.commit()
        try:
            if s.is_anomaly:
                alert_rows = Alert.query.filter_by(machine_id=m.id, status='active').order_by(Alert.created_at.desc()).limit(2).all()
                for alert_row in alert_rows:
                    broadcast_both('alert_created', {'alert': alert_row.to_dict()}, org_id=m.organization_id)
            broadcast_both('sensor_update', {
                'machine': m.to_dict(),
                'sensor_data': s.to_dict(),
            }, org_id=m.organization_id)
        except Exception:
            pass
        return jsonify({'success': True, 'sensor_data': s.to_dict()}), 201

    @machines_bp.route('/<machine_id>/sensor-data', methods=['GET'])
    def get_sensor(machine_id):
        m, user, org, err = machine_iot_auth(machine_id)
        if err:
            return err
        limit = request.args.get('limit', 100, type=int)
        limit = max(1, min(limit, 1000))
        d = (SensorData.query.filter_by(machine_id=m.id)
             .order_by(SensorData.created_at.desc()).limit(limit).all())
        return jsonify({'success': True, 'sensor_data': [x.to_dict() for x in d]}), 200

    @machines_bp.route('/<machine_id>/simulate', methods=['POST'])
    @login_required
    def simulate(machine_id):
        return jerr('Synthetic readings are disabled in this production deployment. Send actual readings through Manual Entry, MQTT, or Device API.', 410,
                    error_code='SIMULATION_DISABLED')

    @machines_bp.route('/<machine_id>/predict-debug', methods=['POST'])
    @login_required
    def machine_predict_debug(machine_id):
        if g.user.role not in ('super_admin', 'admin', 'org_admin'):
            return jerr('Admin privileges required.', 403)
        machine_id=_uuid_or_404(machine_id,'machine_id')
        machine=Machine.query.filter_by(id=machine_id,organization_id=g.organization.id,is_deleted=False).first_or_404()
        sensor_data=(SensorData.query.filter_by(machine_id=machine.id).order_by(SensorData.created_at.asc()).limit(1000).all())
        df=ml_engine._df_from_records(machine,sensor_data)
        incoming=set(ml_engine._canonical_feature(c) for c in df.columns if ml_engine._norm(c) not in TARGET_LEAKAGE_COLUMNS)
        ranked=[]
        for fam,mids in ml_engine.all_by_family.items():
            expected=set()
            for mid in mids: expected.update(ml_engine._canonical_feature(f) for f in (ml_engine.models[mid].get('features') or []))
            score=len(incoming & expected)/max(1,len(incoming|expected)) if expected else 0.0
            ranked.append((score,fam))
        ranked.sort(reverse=True)
        report={'incoming_columns':list(df.columns),'row_count':len(df),'family_ranking':[{'family':f,'score':float(sc)} for sc,f in ranked[:10]],'per_model_attempts':[]}
        # Debug must inspect every registered family/model, not only the top
        # metadata-ranked families, because folder/metadata names can be wrong.
        debug_families = ranked if ranked else [(0.0, fam) for fam in ml_engine.all_by_family]
        for score,fam in debug_families:
            for mid in ml_engine.all_by_family.get(fam,[]):
                if mid not in ml_engine.models: continue
                entry={'model_id':mid,'family':fam,'family_score':float(score)}
                try:
                    info=ml_engine.load_model(mid); entry['required_features']=info.get('features'); entry['required_feature_count']=info.get('feature_count')
                    X,used,diag=ml_engine._prep_matrix(df,info,diagnostics=True); entry['status']='COMPATIBLE'; entry['matched_features']=diag['used_features']; entry['rows_after_cleaning']=int(X.shape[0])
                except ModelCompatibilityError as e: entry['status']='INCOMPATIBLE'; entry['reason']=str(e)
                except Exception as e: entry['status']='ERROR'; entry['reason']=f'{type(e).__name__}: {e}'
                report['per_model_attempts'].append(entry)
        if g.user.role not in ('super_admin', 'admin'):
            report['incoming_columns'] = []
            for entry in report['per_model_attempts']:
                entry.pop('required_features', None)
                entry.pop('matched_features', None)
        return jsonify({'success':True,'diagnosis':report}),200

    @machines_bp.route('/<machine_id>/predict-compatibility', methods=['POST'])
    @login_required
    def machine_predict_compatibility(machine_id):
        if g.user.role not in ('super_admin', 'admin', 'org_admin'):
            return jerr('Admin privileges required.', 403)
        """Return exact real-model compatibility diagnostics for a machine."""
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        machine = Machine.query.filter_by(
            id=machine_id, organization_id=g.organization.id, is_deleted=False
        ).first_or_404()
        data = request.get_json(silent=True) or {}
        payload_rows = (data.get('sensor_data') or data.get('readings') or
                        data.get('records') or data.get('data'))
        dataframe = None
        if payload_rows:
            if isinstance(payload_rows, dict):
                payload_rows = payload_rows.get('rows') or payload_rows.get('records') or payload_rows
            if isinstance(payload_rows, dict):
                payload_rows = [payload_rows]
            if isinstance(payload_rows, list) and payload_rows:
                dataframe = pd.DataFrame(payload_rows)
        sensor_data = (SensorData.query.filter_by(machine_id=machine.id)
                       .order_by(SensorData.created_at.asc()).limit(1000).all())
        if dataframe is None or dataframe.empty:
            dataframe = ml_engine._df_from_records(machine, sensor_data)
        ranked = ml_engine._rank_families(dataframe, data.get('dataset_hint'))
        report = {
            'success': True,
            'prediction_status': 'diagnostic_only',
            'incoming_columns': [str(c) for c in dataframe.columns],
            'row_count': int(len(dataframe)),
            'family_ranking': [{'family': f, 'score': float(sc)} for sc, f in ranked[:20]],
            'registered_models': len(ml_engine.models),
            'registered_families': len(ml_engine.all_by_family),
            'attempts': []
        }
        for score, family in ranked:
            for mid in ml_engine.all_by_family.get(family, []):
                info = ml_engine.models[mid]
                item = {'model_id': mid, 'family': family, 'algorithm': info.get('algorithm'),
                        'family_score': float(score)}
                try:
                    loaded = ml_engine.load_model(mid)
                    X, used, diag = ml_engine._prep_matrix(dataframe, loaded, diagnostics=True)
                    item.update({'status': 'COMPATIBLE', 'required_features': loaded.get('features'),
                                 'required_feature_count': loaded.get('feature_count'),
                                 'matched_features': diag.get('used_features'),
                                 'matrix_shape': list(X.shape)})
                except Exception as exc:
                    item.update({'status': 'INCOMPATIBLE', 'reason': str(exc)[:2000]})
                if g.user.role not in ('super_admin', 'admin'):
                    item.pop('required_features', None)
                    item.pop('feature_names', None)
                report['attempts'].append(item)
        return jsonify(report), 200

    @machines_bp.route('/<machine_id>/predict', methods=['POST'])
    @login_required
    @limiter.limit(f"{config.RATE_LIMIT_AI} per hour")
    def machine_predict(machine_id):
        machine_id = _uuid_or_404(machine_id, 'machine_id')
        rid = _request_id()
        quota_reserved = False
        lock_held = False
        try:
            if not _acquire_prediction_lock(g.organization.id, rid):
                return jerr('A prediction with this request_id is already in progress.',
                            409, request_id=rid, already_processing=True)
            lock_held = True
            machine = Machine.query.filter_by(
                id=machine_id, organization_id=g.organization.id, is_deleted=False
            ).filter(Machine.is_blocked == False).first_or_404()
            # Idempotency is checked before inference so frontend retries do not
            # perform duplicate work.
            existing = Prediction.query.filter_by(
                organization_id=g.organization.id, request_id=rid
            ).first()
            if existing:
                return jsonify({
                    'schema_version': config.PREDICTION_SCHEMA_VERSION,
                    'success': True, 'idempotent_replay': True,
                    'request_id': rid, 'prediction': existing.to_dict()
                }), 200
            data = request.get_json(silent=True) or {}

            # A connected machine may send the current sensor rows directly in the
            # prediction request. Older versions ignored these fields and always
            # used the single connection-baseline row, which made every multi-feature
            # production model appear incompatible. Prefer explicit request data;
            # otherwise use the persisted machine history. Never manufacture missing
            # trained features.
            dataframe = None
            payload_rows = (data.get('sensor_data') or data.get('readings') or
                            data.get('records') or data.get('data'))
            if payload_rows:
                if isinstance(payload_rows, dict):
                    # {"temperature": 70, "vibration": 2.1, ...}
                    # or {"rows": [...]} are both accepted.
                    payload_rows = payload_rows.get('rows') or payload_rows.get('records') or payload_rows
                if isinstance(payload_rows, dict):
                    payload_rows = [payload_rows]
                if isinstance(payload_rows, list) and payload_rows:
                    dataframe = pd.DataFrame(payload_rows)
                    if dataframe.empty:
                        dataframe = None

            sensor_data = (SensorData.query.filter_by(machine_id=machine.id)
                           .order_by(SensorData.created_at.asc()).limit(1000).all())
            allowed, qerr = consume_pred_quota(g.organization, 1)
            if not allowed:
                return jerr(qerr, 429, quota_reached=True)
            quota_reserved = True
            t0 = time.perf_counter()
            try:
                result = ml_engine.predict(
                    machine, sensor_data, data.get('model') or data.get('model_type'),
                    dataframe=dataframe,
                    dataset_hint=data.get('dataset_hint') or ((machine.machine_data or {}).get('dataset_family'))
                )
            except Exception:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
                raise
            ms = (time.perf_counter() - t0) * 1000
            p, replay = _persist_prediction(machine, result, g.organization.id, rid, ms, source='machine_predict', user_id=g.user.id)
            if replay:
                consume_pred_quota(g.organization, -1)
            db.session.commit()
            quota_reserved = False
            alert = _auto_alert(machine, p, result)
            try:
                log_audit('machine_predict', 'prediction', p.id, {
                    'machine_id': machine.id, 'request_id': rid,
                    'model_id': result.get('model_id')
                })
            except Exception:
                pass
            broadcast_both('prediction_created', {
                'prediction': {**p.to_dict(), 'machine_name': machine.name,
                               'owner_name': g.user.display_name or g.user.email}
            }, org_id=g.organization.id)
            if ML_PREDICTIONS:
                ML_PREDICTIONS.labels(
                    status='success', model_type=p.model_type,
                    dataset_family=result.get('dataset_family','unknown')
                ).inc()
            return jsonify(_prediction_response(result, p, alert)), 200
        except ModelCompatibilityError as e:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            if ML_PREDICTIONS_ABSTAINED:
                ML_PREDICTIONS_ABSTAINED.labels(reason=str(e)[:100]).inc()
            return jsonify(_prediction_error_payload(e, rid)), 422
        except Exception as exc:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            logger.exception('machine_predict failed request_id=%s', rid)
            details = {'exception_type': type(exc).__name__}
            if not config.IS_PRODUCTION:
                details['debug_message'] = str(exc)[:500]
            return jerr('Prediction could not complete in the model/persistence pipeline.', 503,
                        request_id=rid, error_code='PREDICTION_RUNTIME_ERROR', details=details,
                        hint='Check the server log for this request_id, model loading, feature compatibility, and database schema.')
        finally:
            if lock_held:
                _release_prediction_lock(g.organization.id, rid)


    families_bp = Blueprint('model_families', __name__, url_prefix='/api/v1/model-families')

    @families_bp.route('', methods=['GET'])
    @login_required
    def list_model_families():
        out=[]
        for family,mids in sorted(ml_engine.all_by_family.items()):
            infos=[ml_engine.models[mid] for mid in mids if mid in ml_engine.models]
            production_mids = ml_engine.by_family.get(family, [])
            contract_mids = production_mids if config.MODEL_REQUIRE_VALIDATED else mids
            contract_infos = [ml_engine.models[mid] for mid in contract_mids if mid in ml_engine.models]
            best=next((x for x in contract_infos if x.get('features')), contract_infos[0] if contract_infos else (next((x for x in infos if x.get('features')), infos[0] if infos else {})))
            out.append({'family_id':family,'display_name':str(family).replace('_',' ').title(),'model_count':len(infos),'production_model_count':len(production_mids),'required_features':best.get('features',[]),'feature_count':int(best.get('feature_count') or len(best.get('features') or [])),'sequence_length':int(best.get('sequence_length') or 1),'training_ranges':best.get('training_ranges') or {},'models':[{'model_id':x.get('id'),'model_type':x.get('model_type'),'framework':x.get('framework'),'feature_count':x.get('feature_count'),'sequence_length':x.get('sequence_length'),'validated':bool(x.get('validated'))} for x in infos]})
        return jsonify({'success':True,'families':out,'count':len(out)}),200

    app.register_blueprint(machines_bp)
    app.register_blueprint(families_bp)

    # ============================================================
    # PREDICTIONS BLUEPRINT
    # ============================================================

    def consume_pred_quota(org, amount=1):
        # Negative amounts refund a reservation after inference/persistence failure.
        if int(amount) < 0:
            refund = abs(int(amount))
            plan = config.PLANS.get(str(org.plan or 'free').lower(), config.PLANS['free'])
            period = plan.get('prediction_period', 'day')
            stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d' if period == 'day' else '%Y-%m')
            keys = []
            if redis_client and config.ORG_DAILY_AI_CAP > 0:
                keys.append(f'quota:ai-org:{org.id}:{datetime.now(timezone.utc).strftime("%Y-%m-%d")}')
            if plan.get('max_predictions') is not None:
                keys.append(f'quota:pred:{org.id}:{period}:{stamp}')
            if redis_client:
                for key in keys:
                    try:
                        current = int(redis_client.get(key) or 0)
                        if current > 0:
                            redis_client.decrby(key, min(refund, current))
                    except Exception:
                        logger.warning('Quota refund failed for key=%s', key, exc_info=True)
            return True, None
        # Hard per-organization/day guard, independent of per-user limits.
        if redis_client and config.ORG_DAILY_AI_CAP > 0:
            cap_key = f'quota:ai-org:{org.id}:{datetime.now(timezone.utc).strftime("%Y-%m-%d")}'
            try:
                cap = int(redis_client.get(f'ratecap:org:{org.id}') or config.ORG_DAILY_AI_CAP)
                current = int(redis_client.incrby(cap_key, int(amount)))
                redis_client.expire(cap_key, 172800)
                if current > cap:
                    redis_client.decrby(cap_key, int(amount))
                    return False, 'Organization daily AI usage cap reached.'
            except Exception:
                if config.IS_PRODUCTION:
                    return False, 'AI quota service unavailable.'
        plan = config.PLANS.get(str(org.plan or 'free').lower(), config.PLANS['free'])
        limit = plan.get('max_predictions')
        if limit is None:
            return True, None
        period = plan.get('prediction_period', 'day')
        stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d' if period == 'day' else '%Y-%m')
        key = f"quota:pred:{org.id}:{period}:{stamp}"
        if not redis_client:
            return (False, 'Quota service unavailable.') if config.IS_PRODUCTION else (True, None)
        try:
            v = int(redis_client.incrby(key, int(amount)))
            redis_client.expire(key, 172800 if period == 'day' else 2678400)
            if v > int(limit):
                redis_client.decrby(key, int(amount))
                if config.ORG_DAILY_AI_CAP > 0:
                    cap_key = f'quota:ai-org:{org.id}:{datetime.now(timezone.utc).strftime("%Y-%m-%d")}'
                    try:
                        redis_client.decrby(cap_key, int(amount))
                    except Exception:
                        logger.warning('Could not release organization quota reservation after plan limit rejection', exc_info=True)
                return False, f'Quota reached for {plan.get("name", "current")} plan.'
            return True, None
        except Exception:
            logger.exception('Quota failure')
            return False, 'Quota service unavailable.'

    def org_dataset_path(filename, org_id):
        if not filename or Path(filename).name != filename:
            raise ValueError('Invalid filename')
        if not re.fullmatch(r'[A-Za-z0-9._-]+', filename):
            raise ValueError('Invalid filename')
        root = Path(config.UPLOAD_FOLDER).resolve()
        org_root = (root / f'org_{org_id}' / 'datasets').resolve()
        p = (org_root / filename).resolve()
        if not str(p).startswith(str(org_root) + os.sep):
            raise ValueError('Invalid path')
        return p

    def read_dataset_file(fp):
        if not PANDAS_AVAILABLE:
            raise RuntimeError('Pandas required')
        NA_TOKENS=['na','NA','n/a','N/A','null','NULL','?','-','']
        ext=fp.suffix.lower()
        if ext=='.csv': return pd.read_csv(fp,index_col=False,na_values=NA_TOKENS,keep_default_na=True)
        if ext in ('.txt','.dat'): return pd.read_csv(fp,sep=None,engine='python',index_col=False,na_values=NA_TOKENS,keep_default_na=True)
        if ext in ('.xlsx','.xls'):
            df=pd.read_excel(fp,na_values=NA_TOKENS,keep_default_na=True)
            if len(df.columns) == 1:
                only_col = str(df.columns[0])
                if ',' in only_col or ';' in only_col:
                    try:
                        recovered = pd.read_csv(fp, sep=None, engine='python', index_col=False, na_values=NA_TOKENS, keep_default_na=True)
                        if len(recovered.columns) > 1:
                            logger.warning('Recovered embedded delimited data from %s', fp.name)
                            return recovered
                    except Exception:
                        pass
                if len(df) > 0 and isinstance(df.iloc[0, 0], str) and (',' in df.iloc[0, 0] or ';' in df.iloc[0, 0]):
                    try:
                        from io import StringIO
                        text_blob = '\n'.join(df.iloc[:, 0].astype(str).tolist())
                        recovered = pd.read_csv(StringIO(text_blob), sep=None, engine='python', index_col=False, na_values=NA_TOKENS, keep_default_na=True)
                        if len(recovered.columns) > 1:
                            return recovered
                    except Exception:
                        pass
            return df
        if ext == '.json':
            raw = json.loads(fp.read_text(encoding='utf-8'))
            if isinstance(raw, dict) and 'data' in raw:
                raw = raw['data']
            return pd.DataFrame(raw) if isinstance(raw, (list, dict)) else pd.read_json(fp)
        raise ValueError('Unsupported format')

    def isolate_machine_rows(df, machine, requested=None):
        norm = {c: ml_engine._norm(c) for c in df.columns}
        cands = [c for c, n in norm.items() if n in {
            'machine_id','unit_id','asset_id','engine_id','equipment_id','machine','asset'
        }]
        if not cands:
            return df
        col = cands[0]
        vals = df[col].dropna().astype(str)
        uniq = list(vals.unique())
        if len(uniq) <= 1:
            return df
        req = str(requested) if requested is not None else None
        if req is None:
            tokens = {str(machine.id), str(getattr(machine,'uuid','')), str(getattr(machine,'name',''))}
            matches = [v for v in uniq if v in tokens]
            if len(matches) == 1:
                req = matches[0]
        if req is None:
            raise ModelCompatibilityError(
                f'AMBIGUOUS_MACHINE_DATASET: dataset contains {len(uniq)} machines in {col!r}. '
                'Provide machine_key explicitly.'
            )
        f = df[df[col].astype(str) == req].copy()
        if f.empty:
            raise ModelCompatibilityError(f'No rows for machine_key={req}')
        return f

    preds_bp = Blueprint('predictions', __name__, url_prefix='/api/v1/predictions')

    @preds_bp.route('', methods=['POST'])
    @login_required
    def save_prediction():
        return jerr('Client-submitted predictions are disabled. Use the trained-model prediction endpoint.', 410,
                    error_code='MANUAL_PREDICTIONS_DISABLED')

    @preds_bp.route('/run', methods=['POST'])
    @login_required
    @limiter.limit(f"{config.RATE_LIMIT_AI} per hour")
    def run_pred():
        rid = _request_id()
        quota_reserved = False
        lock_held = False
        try:
            if not _acquire_prediction_lock(g.organization.id, rid):
                return jerr('A prediction with this request_id is already in progress.',
                            409, request_id=rid, already_processing=True)
            lock_held = True
            existing = Prediction.query.filter_by(
                organization_id=g.organization.id, request_id=rid
            ).first()
            if existing:
                return jsonify({'schema_version': config.PREDICTION_SCHEMA_VERSION,
                                'success': True, 'idempotent_replay': True,
                                'request_id': rid, 'prediction': existing.to_dict()}), 200
            data = request.get_json(silent=True) or {}
            mid = data.get('machine_id') or data.get('machineId')
            if not mid:
                return jerr('Machine ID required.', 400)
            machine = Machine.query.filter_by(
                id=mid, organization_id=g.organization.id, is_deleted=False
            ).filter(Machine.is_blocked == False).first_or_404()
            dataset_file = data.get('dataset_file') or data.get('filename')
            model_type = data.get('model_type') or data.get('model')
            dataset_hint = data.get('dataset_hint')
            dataframe, sensor_data = None, []
            if dataset_file:
                fp = org_dataset_path(dataset_file, g.organization.id)
                if not fp.exists():
                    return jerr('File not found.', 404)
                dataframe = isolate_machine_rows(read_dataset_file(fp), machine, data.get('machine_key'))
                dataset_hint = dataset_hint or ((machine.machine_data or {}).get('dataset_family'))
            else:
                sensor_data = (SensorData.query.filter_by(machine_id=machine.id)
                               .order_by(SensorData.created_at.asc()).limit(1000).all())
            allowed, qerr = consume_pred_quota(g.organization, 1)
            if not allowed:
                return jerr(qerr, 429, quota_reached=True)
            quota_reserved = True
            try:
                t0 = time.perf_counter()
                result = ml_engine.predict(machine, sensor_data, model_type, dataframe=dataframe,
                                           dataset_hint=dataset_hint)
                ms = (time.perf_counter() - t0) * 1000
            except Exception:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
                raise
            p, replay = _persist_prediction(machine, result, g.organization.id, rid, ms, source='run_pred', user_id=g.user.id, source_filename=dataset_file)
            if replay:
                consume_pred_quota(g.organization, -1)
            db.session.commit()
            quota_reserved = False
            alert = _auto_alert(machine, p, result)
            if ML_PREDICTIONS:
                ML_PREDICTIONS.labels(status='success', model_type=p.model_type,
                                      dataset_family=result.get('dataset_family','unknown')).inc()
            broadcast_both('prediction_created', {
                'prediction': {**p.to_dict(), 'machine_name': machine.name}
            }, org_id=g.organization.id)
            return jsonify(_prediction_response(result, p, alert)), 200
        except ModelCompatibilityError as e:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            if ML_PREDICTIONS_ABSTAINED:
                ML_PREDICTIONS_ABSTAINED.labels(reason=str(e)[:100]).inc()
            return jsonify(_prediction_error_payload(e, rid)), 422
        except Exception as exc:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            logger.exception('run prediction failed request_id=%s', rid)
            details = {'exception_type': type(exc).__name__}
            if not config.IS_PRODUCTION:
                details['debug_message'] = str(exc)[:500]
            return jerr('Prediction could not complete in the model/persistence pipeline.', 503,
                        request_id=rid, error_code='PREDICTION_RUNTIME_ERROR', details=details,
                        hint='Check the server log for this request_id, model loading, feature compatibility, and database schema.')
        finally:
            if lock_held:
                _release_prediction_lock(g.organization.id, rid)

    @preds_bp.route('/predict-dataset', methods=['POST'])
    @login_required
    @limiter.limit(f"{config.RATE_LIMIT_AI} per hour")
    def pred_dataset():
        rid = _request_id()
        quota_reserved = False
        lock_held = False
        try:
            if not _acquire_prediction_lock(g.organization.id, rid):
                return jerr('A prediction with this request_id is already in progress.',
                            409, request_id=rid, already_processing=True)
            lock_held = True
            existing = Prediction.query.filter_by(
                organization_id=g.organization.id, request_id=rid
            ).first()
            if existing:
                return jsonify({'schema_version': config.PREDICTION_SCHEMA_VERSION,
                                'success': True, 'idempotent_replay': True,
                                'request_id': rid, 'prediction': existing.to_dict()}), 200
            data = request.get_json(silent=True) or {}
            filename = data.get('filename') or data.get('dataset_file') or data.get('file')
            if not filename:
                return jerr('filename required.', 400)
            fp = org_dataset_path(filename, g.organization.id)
            if not fp.exists():
                return jerr('File not found.', 404)
            mid = data.get('machine_id') or data.get('machineId') or data.get('machine')
            machine_type = (data.get('machine_type') or data.get('machineType') or '').strip()
            if mid:
                machine = Machine.query.filter_by(
                    id=mid, organization_id=g.organization.id, is_deleted=False
                ).filter(Machine.is_blocked == False).first_or_404()
            else:
                hidden_name = '__dataset__'
                machine = Machine.query.filter_by(
                    organization_id=g.organization.id, name=hidden_name, is_deleted=False
                ).first()
                if not machine:
                    mt = re.sub(r'[^A-Za-z0-9_\-]', '', machine_type or 'dataset').lower()[:100] or 'dataset'
                    machine = Machine(
                        name=hidden_name, machine_type=mt,
                        location='Dataset (unassigned)', status='offline', health=100,
                        machine_data={'connection':'manual', 'dataset_only':True},
                        organization_id=g.organization.id, owner_id=g.user.id
                    )
                    db.session.add(machine)
                    db.session.commit()
            df = isolate_machine_rows(
                read_dataset_file(fp), machine, data.get('machine_key')
            )
            allowed, qerr = consume_pred_quota(g.organization, 1)
            if not allowed:
                return jerr(qerr, 429, quota_reached=True)
            quota_reserved = True
            try:
                t0 = time.perf_counter()
                result = ml_engine.predict(
                    machine, [], data.get('model_type') or data.get('model'),
                    dataframe=df, dataset_hint=data.get('dataset_hint') or ((machine.machine_data or {}).get('dataset_family'))
                )
                ms = (time.perf_counter() - t0) * 1000
            except Exception:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
                raise
            p, replay = _persist_prediction(machine, result, g.organization.id, rid, ms, source='pred_dataset', user_id=g.user.id, source_filename=filename)
            if replay:
                consume_pred_quota(g.organization, -1)
            db.session.commit()
            quota_reserved = False
            alert = _auto_alert(machine, p, result)
            if ML_PREDICTIONS:
                ML_PREDICTIONS.labels(status='success', model_type=p.model_type,
                                      dataset_family=result.get('dataset_family','unknown')).inc()
            broadcast_both('prediction_created', {
                'prediction': {**p.to_dict(), 'machine_name': machine.name}
            }, org_id=g.organization.id)
            return jsonify(_prediction_response(result, p, alert)), 200
        except ModelCompatibilityError as e:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            if ML_PREDICTIONS_ABSTAINED:
                ML_PREDICTIONS_ABSTAINED.labels(reason=str(e)[:100]).inc()
            return jsonify(_prediction_error_payload(e, rid)), 422
        except Exception as exc:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            logger.exception('predict-dataset failed request_id=%s', rid)
            details = {'exception_type': type(exc).__name__}
            if not config.IS_PRODUCTION:
                details['debug_message'] = str(exc)[:500]
            return jerr('Dataset prediction could not complete in the model/persistence pipeline.', 503,
                        request_id=rid, error_code='DATASET_PREDICTION_RUNTIME_ERROR', details=details,
                        hint='Check the server log for this request_id, file parsing, model compatibility, and database schema.')
        finally:
            if lock_held:
                _release_prediction_lock(g.organization.id, rid)

    @preds_bp.route('/evaluate', methods=['POST'])
    @login_required
    @limiter.limit(f"{config.RATE_LIMIT_AI} per hour")
    def evaluate_pred():
        """Evaluation-only path: ground truth is never supplied to inference."""
        rid = _request_id()
        quota_reserved = False
        lock_held = False
        try:
            if not _acquire_prediction_lock(g.organization.id, rid):
                return jerr('An evaluation with this request_id is already in progress.',
                            409, request_id=rid, already_processing=True)
            lock_held = True
            data = request.get_json(silent=True) or {}
            mid = data.get('machine_id') or data.get('machineId')
            filename = data.get('filename') or data.get('dataset_file')
            target_col = data.get('target_column') or 'rul_hours'
            if not mid or not filename:
                return jerr('machine_id and filename are required.', 400)
            machine = Machine.query.filter_by(
                id=mid, organization_id=g.organization.id, is_deleted=False
            ).filter(Machine.is_blocked == False).first_or_404()
            fp = org_dataset_path(filename, g.organization.id)
            if not fp.exists():
                return jerr('File not found.', 404)
            df = isolate_machine_rows(read_dataset_file(fp), machine, data.get('machine_key'))
            target_name = next((c for c in df.columns if ml_engine._norm(c) == ml_engine._norm(target_col)), None)
            if not target_name:
                return jerr(f'Ground-truth target column {target_col!r} not found.', 400)
            truth = pd.to_numeric(df[target_name], errors='coerce')
            if truth.isna().all():
                return jerr('Ground-truth target is not numeric.', 400)
            allowed, qerr = consume_pred_quota(g.organization, 1)
            if not allowed:
                return jerr(qerr, 429, quota_reached=True)
            quota_reserved = True
            try:
                result = ml_engine.predict(
                    machine, [], data.get('model_type') or data.get('model'),
                    dataframe=df.drop(columns=[target_name]),
                    dataset_hint=data.get('dataset_hint') or ((machine.machine_data or {}).get('dataset_family'))
                )
            except Exception:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
                raise
            pred = float(result['rul_hours'])
            persisted, _ = _persist_prediction(machine, result, g.organization.id, rid, 0,
                                               source='evaluate', user_id=g.user.id,
                                               source_filename=filename)
            db.session.commit()
            quota_reserved = False
            actual = float(truth.dropna().iloc[-1])
            err = pred - actual
            return jsonify({
                'schema_version': config.PREDICTION_SCHEMA_VERSION, 'success': True,
                'mode': 'evaluation', 'request_id': rid,
                'prediction_id': persisted.id,
                'model_id': result.get('model_id'), 'dataset_family': result.get('dataset_family'),
                'predicted_rul': pred, 'actual_rul': actual,
                'absolute_error': abs(err), 'signed_error': err,
                'uncertainty_lower': result.get('uncertainty_lower'),
                'uncertainty_upper': result.get('uncertainty_upper')
            }), 200
        except ModelCompatibilityError as e:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            return jsonify({'schema_version': config.PREDICTION_SCHEMA_VERSION,
                            'success': False, 'prediction_status': 'abstained',
                            'error': 'EVALUATION_ABSTAINED', 'details': str(e),
                            'request_id': rid}), 422
        except Exception as exc:
            if quota_reserved:
                consume_pred_quota(g.organization, -1)
                quota_reserved = False
            db.session.rollback()
            logger.exception('Evaluation failed request_id=%s', rid)
            details = {'exception_type': type(exc).__name__}
            if not config.IS_PRODUCTION:
                details['debug_message'] = str(exc)[:500]
            return jerr('Evaluation could not complete in the model/persistence pipeline.', 503,
                        request_id=rid, error_code='EVALUATION_RUNTIME_ERROR', details=details,
                        hint='Check the server log for this request_id, model loading, feature compatibility, and database schema.')
        finally:
            if lock_held:
                _release_prediction_lock(g.organization.id, rid)

    @preds_bp.route('/batch', methods=['POST'])
    @login_required
    @limiter.limit(f"{config.RATE_LIMIT_AI * 2} per hour")
    def batch_pred():
        data = request.get_json(silent=True) or {}
        ids = data.get('machine_ids') or []
        if not ids:
            return jerr('Machine IDs required.', 400)
        machines = Machine.query.filter(
            Machine.id.in_(ids), Machine.organization_id == g.organization.id,
            Machine.is_deleted == False, Machine.is_blocked == False
        ).all()
        if not machines:
            return jerr('No valid machines found.', 404)
        results = []
        persisted = []
        for machine in machines:
            rid = f"{_request_id()[:27]}:{machine.id}"[:64]
            quota_reserved = False
            try:
                existing = Prediction.query.filter_by(
                    organization_id=g.organization.id, request_id=rid
                ).first()
                if existing:
                    results.append(existing.to_dict())
                    continue
                allowed, qerr = consume_pred_quota(g.organization, 1)
                if not allowed:
                    results.append({'machine_id': str(machine.id), 'machine_name': machine.name,
                                    'prediction_status': 'quota_reached', 'error': qerr, 'request_id': rid})
                    continue
                quota_reserved = True
                try:
                    sd = (SensorData.query.filter_by(machine_id=machine.id)
                          .order_by(SensorData.created_at.asc()).limit(1000).all())
                    t0 = time.perf_counter()
                    result = ml_engine.predict(machine, sd, data.get('model_type') or data.get('model'),
                                               dataset_hint=((machine.machine_data or {}).get('dataset_family')))
                    ms = (time.perf_counter() - t0) * 1000
                except Exception:
                    consume_pred_quota(g.organization, -1)
                    quota_reserved = False
                    raise
                p, replay = _persist_prediction(machine, result, g.organization.id, rid, ms, source='batch', user_id=g.user.id)
                db.session.commit()
                if replay:
                    consume_pred_quota(g.organization, -1)
                quota_reserved = False
                if not replay:
                    persisted.append((p, result))
                results.append(p.to_dict())
            except ModelCompatibilityError as e:
                if quota_reserved:
                    consume_pred_quota(g.organization, -1)
                    quota_reserved = False
                db.session.rollback()
                if ML_PREDICTIONS_ABSTAINED:
                    ML_PREDICTIONS_ABSTAINED.labels(reason=str(e)[:100]).inc()
                results.append({'machine_id':str(machine.id), 'machine_name':machine.name,
                                'prediction_status':'abstained', 'error':str(e), 'request_id':rid})
            except Exception as e:
                if quota_reserved:
                    consume_pred_quota(g.organization, -1)
                    quota_reserved = False
                db.session.rollback()
                logger.exception('Batch prediction failed machine=%s', machine.id)
                results.append({'machine_id':str(machine.id), 'machine_name':machine.name,
                                'prediction_status':'failed', 'error':'Prediction failed', 'request_id':rid})
        for p, result in persisted:
            try:
                _auto_alert(p.machine_id and db.session.get(Machine, p.machine_id), p, result)
            except Exception:
                pass
        return jsonify({'schema_version':config.PREDICTION_SCHEMA_VERSION,
                        'success':True, 'predictions':results, 'count':len(results)}), 200

    @preds_bp.route('/history', methods=['GET'])
    @login_required
    def pred_history():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            mid = request.args.get('machine_id')
            q = Prediction.query.join(Machine).filter(
                Machine.organization_id == g.organization.id,
                Machine.is_deleted == False
            )
            if mid:
                q = q.filter(Prediction.machine_id == mid)
            q = q.order_by(Prediction.created_at.desc())
            result = paginate(q, page, per_page)
            result['predictions'] = result['items']
            return jsonify({'success': True, **result}), 200
        except Exception:
            logger.exception('History failed')
            return jsonify({
                'success': False, 'error': 'Failed',
                'items': [], 'predictions': [], 'total': 0
            }), 500

    @preds_bp.route('/stats', methods=['GET'])
    @login_required
    def pred_stats():
        try:
            total = Prediction.query.join(Machine).filter(
                Machine.organization_id == g.organization.id
            ).count()
            avg_rul = db.session.query(func.avg(Prediction.rul_hours)).join(Machine).filter(
                Machine.organization_id == g.organization.id
            ).scalar() or 0
            status_counts = db.session.query(
                Prediction.status, func.count(Prediction.id)
            ).join(Machine).filter(
                Machine.organization_id == g.organization.id
            ).group_by(Prediction.status).all()
            return jsonify({
                'success': True,
                'stats': {
                    'total': total, 'avg_rul': float(avg_rul),
                    'status_breakdown': {s: c for s, c in status_counts}
                }
            }), 200
        except Exception:
            return jsonify({'success': False, 'error': 'Failed'}), 500

    app.register_blueprint(preds_bp)

    # ============================================================
    # ALERTS BLUEPRINT
    # ============================================================

    alerts_bp = Blueprint('alerts', __name__, url_prefix='/api/v1/alerts')

    @alerts_bp.route('', methods=['GET'])
    @login_required
    def list_alerts():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            status = request.args.get('status')
            severity = request.args.get('severity')
            mid = request.args.get('machine_id')
            q = Alert.query.join(Machine).filter(
                Machine.organization_id == g.organization.id
            ).order_by(Alert.created_at.desc())
            if status:
                q = q.filter(Alert.status == status)
            if severity:
                q = q.filter(Alert.severity == severity)
            if mid:
                q = q.filter(Alert.machine_id == mid)
            result = paginate(q, page, per_page)
            result['alerts'] = result['items']
            return jsonify({'success': True, **result}), 200
        except Exception:
            logger.exception('List alerts failed')
            return jsonify({
                'success': False, 'error': 'Failed',
                'items': [], 'alerts': [], 'total': 0
            }), 500

    @alerts_bp.route('', methods=['POST'])
    @login_required
    def create_alert():
        try:
            data = request.get_json() or {}
            machine_id = data.get('machine_id') or data.get('machineId')
            if not machine_id:
                return jerr('machine_id is required.', 400)
            machine = Machine.query.filter_by(
                id=machine_id,
                organization_id=g.organization.id,
                is_deleted=False
            ).first()
            if not machine:
                return jerr('Machine not found.', 404)
            alert = Alert(
                machine_id=machine.id, organization_id=machine.organization_id,
                title=data.get('title') or 'Alert',
                message=data.get('message') or data.get('description') or '',
                severity=data.get('severity') or 'warning',
                category=data.get('category') or 'manual',
                source=data.get('source') or 'user',
                status=data.get('status') or 'active',
                incident_id=data.get('incident_id'),
            )
            db.session.add(alert)
            db.session.commit()
            try:
                broadcast_both('alert_created', {'alert': alert.to_dict()},
                               org_id=g.organization.id)
            except Exception:
                pass
            return jsonify({'success': True, 'alert': alert.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            logger.exception('create_alert failed')
            return jerr(str(e), 500)

    @alerts_bp.route('/<int:aid>', methods=['GET'])
    @login_required
    def get_alert(aid):
        a = Alert.query.join(Machine).filter(
            Alert.id == aid,
            Machine.organization_id == g.organization.id
        ).first_or_404()
        return jsonify({'success': True, 'alert': a.to_dict()}), 200

    @alerts_bp.route('/<int:aid>/acknowledge', methods=['POST'])
    @login_required
    def ack_alert(aid):
        a = Alert.query.join(Machine).filter(
            Alert.id == aid,
            Machine.organization_id == g.organization.id
        ).first_or_404()
        a.status = 'acknowledged'
        a.acknowledged_at = datetime.now(timezone.utc)
        a.acknowledged_by = g.user.id
        a.is_read = True
        db.session.commit()
        try:
            broadcast_both('alert_updated', {'alert': a.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True}), 200

    @alerts_bp.route('/<int:aid>/resolve', methods=['POST', 'PATCH'])
    @login_required
    def resolve_alert(aid):
        data = request.get_json() or {}
        a = Alert.query.join(Machine).filter(
            Alert.id == aid,
            Machine.organization_id == g.organization.id
        ).first_or_404()
        a.status = 'resolved'
        a.resolved_at = datetime.now(timezone.utc)
        a.resolved_by = g.user.id
        a.resolution_notes = data.get('notes') or data.get('resolution_notes')
        a.is_read = True
        db.session.commit()
        try:
            broadcast_both('alert_updated', {'alert': a.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True}), 200

    @alerts_bp.route('/<int:aid>/escalate', methods=['POST'])
    @login_required
    def esc_alert(aid):
        a = Alert.query.join(Machine).filter(
            Alert.id == aid,
            Machine.organization_id == g.organization.id
        ).first_or_404()
        a.escalation_level = (a.escalation_level or 0) + 1
        a.escalated_at = datetime.now(timezone.utc)
        db.session.commit()
        try:
            broadcast_both('alert_updated', {'alert': a.to_dict()},
                           org_id=g.organization.id)
        except Exception:
            pass
        return jsonify({'success': True,
                        'escalation_level': a.escalation_level}), 200

    # FIX: bulk mark-all-read endpoint
    @alerts_bp.route('/mark-all-read', methods=['POST'])
    @login_required
    def mark_all_read():
        try:
            q = Alert.query.join(Machine).filter(
                Machine.organization_id == g.organization.id,
                Alert.is_read == False,
            )
            ids = [row[0] for row in q.with_entities(Alert.id).all()]
            if ids:
                Alert.query.filter(Alert.id.in_(ids)).update(
                    {'is_read': True}, synchronize_session=False
                )
                db.session.commit()
            try:
                broadcast_both('alerts_marked_read', {'count': len(ids)},
                               org_id=g.organization.id)
            except Exception:
                pass
            return jsonify({'success': True, 'updated': len(ids)}), 200
        except Exception:
            db.session.rollback()
            logger.exception('mark_all_read failed')
            return jerr('Failed to mark alerts as read.', 500)

    app.register_blueprint(alerts_bp)

    # ============================================================
    # PAYMENTS + BILLING BLUEPRINTS
    # ============================================================

    def _sub_resp():
        org = g.organization
        return jsonify({
            'success': True,
            'plan': org.plan,
            'plan_id': org.plan,
            'subscription_status': org.subscription_status,
            'trial_ends_at': org.trial_ends_at.isoformat() if org.trial_ends_at else None,
            'trial_days_remaining': org.trial_days_remaining,
            'is_trial_active': org.is_trial_active,
            'is_trial_expired': org.is_trial_expired(),
            'max_users': org.max_users, 'max_machines': org.max_machines,
            'max_api_calls': org.max_api_calls,
            'max_storage_gb': float(org.max_storage_gb) if org.max_storage_gb else 0,
            'available_plans': config.PLANS,
            'gateways': payment_processor.get_gateways(),
            'gateway_status': payment_processor.gateway_status(),
            'payment_enabled': len(payment_processor.get_gateways()) > 0,
        }), 200

    def _inv_resp():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        q = Payment.query.filter_by(
            organization_id=g.organization.id, status='completed'
        ).order_by(Payment.created_at.desc())
        result = paginate(q, page, per_page)
        result['invoices'] = result['items']
        return jsonify({'success': True, **result}), 200

    def _usage_resp():
        org = g.organization
        plan = config.PLANS.get(str(org.plan or 'free').lower(), config.PLANS['free'])
        preds_query = Prediction.query.join(Machine).filter(Machine.organization_id == org.id)
        preds_all_time = preds_query.count()
        period = str(plan.get('prediction_period', 'month')).lower()
        now = datetime.now(timezone.utc)
        period_key = now.strftime('%Y-%m-%d' if period == 'day' else '%Y-%m')
        max_pred = plan.get('max_predictions')
        current_preds = None
        if redis_client:
            try:
                current_preds = int(redis_client.get(f'quota:pred:{org.id}:{period}:{period_key}') or 0)
            except Exception:
                current_preds = None
        if current_preds is None:
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0) if period == 'day' else now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            current_preds = preds_query.filter(Prediction.created_at >= period_start).count()
        ddir = Path(config.UPLOAD_FOLDER) / f'org_{org.id}' / 'datasets'
        try:
            sb = sum(f.stat().st_size for f in ddir.rglob('*') if f.is_file()) if ddir.exists() else 0
        except OSError:
            sb = 0
        api_calls = 0
        if redis_client:
            try:
                api_calls = int(redis_client.get(f"usage:api:guard:{org.id}:{now.strftime('%Y-%m-%d')}") or redis_client.get(f"usage:api:{org.id}:{now.strftime('%Y-%m-%d')}") or 0)
            except Exception:
                api_calls = 0
        machine_count = Machine.query.filter_by(organization_id=org.id, is_deleted=False).filter(Machine.name != '__dataset__').count()
        return jsonify({
            'success': True, 'plan': org.plan, 'plan_name': plan.get('name'),
            'usage': {
                'api_calls': api_calls, 'api_calls_limit': plan.get('max_api_calls', 0),
                'predictions': current_preds, 'predictions_limit': max_pred if max_pred is not None else 'Unlimited',
                'predictions_period': period, 'predictions_period_key': period_key,
                'predictions_all_time': preds_all_time,
                'machines': machine_count, 'machines_limit': getattr(org, 'max_machines', plan.get('max_machines')),
                'storage_used_bytes': sb, 'storage_used_gb': round(sb / (1024 ** 3), 6),
                'storage_limit_gb': float(getattr(org, 'max_storage_gb', 0) or 0)
            }
        }), 200

    def _stats_resp():
        total = db.session.query(func.sum(Payment.amount)).filter_by(
            organization_id=g.organization.id, status='completed'
        ).scalar() or 0
        machine_count = Machine.query.filter_by(
            organization_id=g.organization.id, is_deleted=False
        ).filter(Machine.name != '__dataset__').count()
        active_alerts = Alert.query.join(Machine).filter(
            Machine.organization_id == g.organization.id,
            Alert.status == 'active'
        ).count()
        critical_alerts = Alert.query.join(Machine).filter(
            Machine.organization_id == g.organization.id,
            Alert.status == 'active',
            Alert.severity == 'critical'
        ).count()
        pred_count = Prediction.query.join(Machine).filter(
            Machine.organization_id == g.organization.id
        ).count()
        org = g.organization
        return jsonify({
            'success': True,
            'stats': {
                'total_paid': float(total),
                'total_invoices': Payment.query.filter_by(
                    organization_id=org.id, status='completed'
                ).count(),
                'pending_payments': Payment.query.filter_by(
                    organization_id=org.id, status='pending'
                ).count(),
                'machines': machine_count,
                'machinesLimit': org.max_machines,
                'machine_limit': org.max_machines,
                'predictions': pred_count,
                'predictionsLimit': org.max_api_calls or 'Unlimited',
                'prediction_limit': org.max_api_calls or 'Unlimited',
                'alerts': active_alerts,
                'alert_count': active_alerts,
                'criticalAlerts': critical_alerts,
                'critical_alert_count': critical_alerts,
            }
        }), 200

    def _payment_idempotency_record(user, body):
      raw_key = (request.headers.get('Idempotency-Key') or '').strip()
      if not raw_key:
        # Fallback: derive a stable per-user+plan key so an old frontend that
        # does not send the header still gets idempotent behaviour.
        import hashlib as _hl
        seed = f"{user.id}:{body.get('plan_id','')}:{body.get('gateway','paddle')}"
        raw_key = 'auto-' + _hl.sha256(seed.encode()).hexdigest()[:40]
      request_hash = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
      storage_key = hashlib.sha256(f'{user.id}:{raw_key}'.encode()).hexdigest()
      record = PaymentIdempotency.query.filter_by(key=storage_key).first()
      now = datetime.now(timezone.utc)
      if record:
        if str(record.user_id) != str(user.id) or record.request_hash != request_hash:
            return None, jerr('Idempotency key was already used for a different request.', 409)
        age = (now - ensure_aware(record.created_at)).total_seconds() if record.created_at else 0
        if record.status == 'processing' and age > 900:
            record.status = 'failed'
            record.response_payload = {'success': False, 'error': 'Previous checkout attempt expired; use a new idempotency key.'}
            record.status_code = 409
            db.session.commit()
        if record.status == 'completed' and record.response_payload is not None:
            return (record.response_payload, int(record.status_code or 200)), None
        if record.status == 'processing':
            return None, jerr('A checkout with this idempotency key is already in progress.', 409)
        if record.status == 'failed' and record.response_payload is not None:
            return (record.response_payload, int(record.status_code or 409)), None
      else:
        record = PaymentIdempotency(key=storage_key, user_id=user.id, request_hash=request_hash, status='processing')
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = PaymentIdempotency.query.filter_by(key=storage_key).first()
            if existing and existing.status == 'completed' and existing.response_payload is not None:
                return (existing.response_payload, int(existing.status_code or 200)), None
            return None, jerr('A checkout with this idempotency key is already in progress.', 409)
      return record, None
    def _payment_idempotency_finish(record, payload, status_code, success):
        if not isinstance(record, PaymentIdempotency):
            return
        try:
            record.status = 'completed' if success else 'failed'
            record.response_payload = payload
            record.status_code = int(status_code)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('Could not persist payment idempotency response')

    def _checkout_resp():
        data = request.get_json() or {}
        plan_id = data.get('plan_id') or data.get('plan')
        gw = data.get('gateway', 'paddle')
        if not plan_id or plan_id not in config.PLANS:
            return jerr('Invalid plan.', 400)
        plan = config.PLANS[plan_id]
        if plan.get('is_custom'):
            return jerr('Enterprise plan requires contacting sales.', 400, enterprise=True)
        if not payment_processor.get_gateways():
            return jerr('Payment gateway is not configured on the server.', 503,
                        gateway_status=payment_processor.gateway_status(), contact='sales@synapsepm.com')
        idem_record, idem_error = _payment_idempotency_record(g.user, {'plan_id': plan_id, 'gateway': gw})
        if idem_error is not None:
            return idem_error
        if isinstance(idem_record, tuple):
            payload, code = idem_record
            return jsonify(payload), code
        try:
            result = payment_processor.create_checkout(gw, plan_id, g.user, g.organization)
            if 'error' in result:
                upstream = bool(result.get('status_code')) or gw in ('paddle', 'khalti')
                status_code = 503 if upstream else 400
                payload = {'success': False, 'error': result['error'],
                           'detail': result.get('detail') or result.get('error'),
                           **{k: v for k, v in result.items() if k not in ('error', 'detail')}}
                _payment_idempotency_finish(idem_record, payload, status_code, False)
                return jsonify(payload), status_code
            payload = {'success': True, **result}
            _payment_idempotency_finish(idem_record, payload, 200, True)
            if PAYMENTS:
                PAYMENTS.labels(gateway=gw, status='initiated').inc()
            return jsonify(payload), 200
        except Exception:
            db.session.rollback()
            logger.exception('Checkout initiation failed')
            _payment_idempotency_finish(idem_record, {'success': False, 'error': 'Checkout initiation failed.'}, 500, False)
            return jerr('Checkout initiation failed.', 500)

    payments_bp = Blueprint('payments', __name__, url_prefix='/api/v1/payments')
    billing_bp = Blueprint('billing', __name__, url_prefix='/api/v1/billing')

    @payments_bp.route('/plans', methods=['GET'])
    def plans():
        ps = [{'id': p['id'], 'name': p['name'], 'price': p['price'],
               'price_display': p['price_display'], 'currency': p['currency'],
               'features': p['features'], 'is_custom': p.get('is_custom', False)}
              for p in config.PLANS.values()]
        gateways = payment_processor.get_gateways()
        return jsonify({
            'success': True, 'plans': ps,
            'gateways': gateways,
            'gateway_status': payment_processor.gateway_status(),
            'payment_enabled': len(gateways) > 0,
            'trial_days': config.TRIAL_DAYS
        }), 200

    @payments_bp.route('/paddle-config', methods=['GET'])
    def paddle_config():
        return jsonify({
            'success': True,
            'client_token': payment_processor.paddle_client_token(),
            'environment': config.PADDLE_ENV,
            'enabled': bool(config.PADDLE_API_KEY and config.PADDLE_PRICE_IDS),
        }), 200

    @payments_bp.route('/create-checkout', methods=['POST'])
    @login_required
    def checkout():
        return _checkout_resp()

    @payments_bp.route('/checkout', methods=['POST'])
    @login_required
    def checkout_alias():
        return _checkout_resp()

    @payments_bp.route('/khalti/initiate', methods=['POST'])
    @login_required
    def khalti_init():
        data = request.get_json() or {}
        plan_id = data.get('plan_id') or data.get('plan')
        if not plan_id or plan_id not in config.PLANS:
            return jerr('Valid plan ID required.', 400)
        idem_record, idem_error = _payment_idempotency_record(g.user, {'plan_id': plan_id, 'gateway': 'khalti'})
        if idem_error is not None:
            return idem_error
        if isinstance(idem_record, tuple):
            payload, code = idem_record
            return jsonify(payload), code
        try:
            result = payment_processor.create_checkout('khalti', plan_id, g.user, g.organization)
            if result.get('error'):
                payload = {'success': False, 'error': result['error']}
                _payment_idempotency_finish(idem_record, payload, 502, False)
                return jsonify(payload), 502
            payload = {'success': True, **result}
            _payment_idempotency_finish(idem_record, payload, 200, True)
            return jsonify(payload), 200
        except Exception:
            db.session.rollback()
            logger.exception('Khalti checkout initiation failed')
            _payment_idempotency_finish(idem_record, {'success': False, 'error': 'Khalti checkout failed.'}, 500, False)
            return jerr('Khalti checkout failed.', 500)

    @payments_bp.route('/subscription', methods=['GET'])
    @login_required
    def sub_get():
        return _sub_resp()

    @payments_bp.route('/invoices', methods=['GET'])
    @login_required
    def inv_get():
        return _inv_resp()

    @payments_bp.route('/payment-methods', methods=['GET'])
    @login_required
    def pm_get():
        return jsonify({
            'success': True,
            'methods': [
                {'name': 'card', 'label': 'Credit / Debit Card', 'via': 'Paddle'},
                {'name': 'paypal', 'label': 'PayPal', 'via': 'Paddle'},
                {'name': 'apple_pay', 'label': 'Apple Pay', 'via': 'Paddle'},
                {'name': 'google_pay', 'label': 'Google Pay', 'via': 'Paddle'},
            ],
        }), 200

    @payments_bp.route('/usage', methods=['GET'])
    @login_required
    def usage_get():
        return _usage_resp()

    @payments_bp.route('/stats', methods=['GET'])
    @login_required
    def pay_stats():
        return _stats_resp()

    # FIX: verify payment endpoint (frontend calls after Paddle redirect)
    @payments_bp.route('/verify/<payment_uuid>', methods=['GET'])
    @login_required
    def verify_payment(payment_uuid):
        payment_uuid = _uuid_or_404(payment_uuid, 'payment_uuid')
        p = Payment.query.filter_by(uuid=payment_uuid).first()
        if not p:
            return jerr('Payment not found.', 404)
        if p.organization_id != g.organization.id:
            return jerr('Not your payment.', 403)
        return jsonify({'success': True, 'payment': p.to_dict()}), 200

    @payments_bp.route('/cancel', methods=['POST'])
    @login_required
    def cancel_sub():
        org = g.organization
        org.subscription_status = 'canceled'
        db.session.commit()
        try:
            broadcast_both('billing_updated', {
                'organization': org.to_dict(),
                'status': 'canceled',
            }, org_id=org.id)
        except Exception:
            pass
        return jsonify({'success': True, 'message': 'Subscription canceled'}), 200

    @payments_bp.route('/khalti/callback', methods=['GET'])
    def khalti_cb():
        pidx = request.args.get('pidx')
        if not pidx or not config.KHALTI_SECRET_KEY or not REQUESTS_AVAILABLE:
            return redirect(f'{config.FRONTEND_URL}/payment-cancel?reason=invalid_callback')
        p = Payment.query.filter_by(gateway='khalti', gateway_order_id=pidx).first()
        if not p:
            return redirect(f'{config.FRONTEND_URL}/payment-cancel?reason=not_found')
        try:
            base = ('https://dev.khalti.com/api/v2'
                    if config.KHALTI_ENV != 'live' else 'https://khalti.com/api/v2')
            r = requests.post(
                base + '/epayment/lookup/',
                headers={'Authorization': f'Key {config.KHALTI_SECRET_KEY}',
                         'Content-Type': 'application/json'},
                json={'pidx': pidx}, timeout=(5, 15)
            )
            r.raise_for_status()
            body = r.json()
            exp = int((p.payment_data or {}).get('khalti_amount_paisa', 0))
            if body.get('status') == 'Completed' and int(body.get('total_amount', -1)) == exp:
                payment_processor.activate(p, body.get('transaction_id'), None)
                return redirect(f'{config.FRONTEND_URL}/payment-success?payment_id={p.uuid}')
            return redirect(f'{config.FRONTEND_URL}/payment-cancel?reason=not_completed')
        except Exception:
            logger.exception('Khalti callback failed')
            return redirect(f'{config.FRONTEND_URL}/payment-cancel?reason=verify_failed')

    @payments_bp.route('/paddle/webhook', methods=['POST'])
    def paddle_wh():
        if not config.PADDLE_WEBHOOK_SECRET:
            logger.error('Paddle webhook received but PADDLE_WEBHOOK_SECRET not set')
            return jsonify({'error': 'webhook not configured'}), 503

        raw = request.get_data(cache=False, as_text=False)
        sig = request.headers.get('Paddle-Signature', '')
        try:
            parts = dict(item.split('=', 1) for item in sig.split(';') if '=' in item)
            ts = parts.get('ts')
            provided = parts.get('h1')
            try:
                ts_int = int(ts)
            except (TypeError, ValueError):
                return jsonify({'error': 'invalid signature'}), 400
            if not provided or abs(time.time() - ts_int) > 300:
                logger.warning('Paddle webhook: bad timestamp/sig format')
                return jsonify({'error': 'invalid signature'}), 400
            expected = hmac.new(
                config.PADDLE_WEBHOOK_SECRET.encode(),
                f'{ts}:'.encode() + raw, hashlib.sha256
            ).hexdigest()
            if not secrets.compare_digest(expected, provided):
                logger.warning('Paddle webhook: signature mismatch')
                return jsonify({'error': 'invalid signature'}), 400

            event = json.loads(raw.decode('utf-8'))
            event_id = event.get('event_id')
            event_type = event.get('event_type')
            data = event.get('data') or {}
            custom = data.get('custom_data') or {}

            if event_id:
                try:
                    existing = WebhookEvent.query.filter_by(
                        event_id=event_id, gateway='paddle'
                    ).first()
                    if existing:
                        return jsonify({'success': True, 'note': 'duplicate'}), 200
                    db.session.add(WebhookEvent(
                        event_id=event_id, gateway='paddle', payload=event
                    ))
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    return jsonify({'success': True, 'note': 'duplicate'}), 200

            if event_type in ('transaction.paid', 'transaction.completed'):
                pid = custom.get('payment_id')
                p = Payment.query.filter_by(uuid=pid).first() if pid else None
                if p and p.status != 'completed':
                    payment_processor.activate(
                        p, data.get('id'), data.get('subscription_id')
                    )
                    logger.info(f'Paddle webhook: activated payment {p.uuid}')
            elif event_type == 'subscription.canceled':
                sid = data.get('id')
                org = Organization.query.filter_by(subscription_id=sid).first()
                if org:
                    org.subscription_status = 'canceled'
                    db.session.commit()
            elif event_type == 'transaction.payment_failed':
                pid = custom.get('payment_id')
                p = Payment.query.filter_by(uuid=pid).first() if pid else None
                if p:
                    p.status = 'failed'
                    db.session.commit()
            return jsonify({'success': True}), 200
        except Exception:
            db.session.rollback()
            logger.exception('Paddle webhook failed')
            return jsonify({'error': 'processing failed'}), 500

    @payments_bp.route('/mock/success', methods=['GET'])
    def mock_success():
        pid = request.args.get('payment_id')
        if not pid:
            return redirect(f'{config.FRONTEND_URL}/payment-cancel?reason=missing_id')
        p = Payment.query.filter_by(uuid=pid, gateway='mock').first()
        if not p:
            return redirect(f'{config.FRONTEND_URL}/payment-cancel?reason=not_found')
        if p.status != 'completed':
            payment_processor.activate(p, 'mock_' + p.uuid, None)
        return redirect(f'{config.FRONTEND_URL}/payment-success?payment_id={p.uuid}')

    @billing_bp.route('/subscription', methods=['GET'])
    @login_required
    def b_sub():
        return _sub_resp()

    @billing_bp.route('/invoices', methods=['GET'])
    @login_required
    def b_inv():
        return _inv_resp()

    @billing_bp.route('/payment-methods', methods=['GET'])
    @login_required
    def b_pm():
        return pm_get()

    @billing_bp.route('/usage', methods=['GET'])
    @login_required
    def b_usage():
        return _usage_resp()

    @billing_bp.route('/stats', methods=['GET'])
    @login_required
    def b_stats():
        return _stats_resp()

    @billing_bp.route('/create-checkout', methods=['POST'])
    @login_required
    def b_checkout():
        return _checkout_resp()

    @billing_bp.route('/khalti/initiate', methods=['POST'])
    @login_required
    def b_khalti():
        return khalti_init()

    @billing_bp.route('/enterprise-request', methods=['POST'])
    def b_enterprise_request():
        try:
            data = request.get_json(silent=True) or {}
            full_name = normalize_name(data.get('name') or data.get('full_name'))
            email = normalize_email(data.get('email'))
            company = normalize_name(data.get('company'))
            phone = normalize_name(data.get('phone'))
            machines = normalize_name(data.get('machines'))
            requirements = data.get('requirements') or ''
            if not full_name or not email or not company:
                return jerr('Name, email, and company are required.', 400)
            if not EMAIL_REGEX.match(email):
                return jerr('Invalid email address.', 400)

            org_id = None
            user_id = None
            try:
                auth = request.headers.get('Authorization', '')
                if auth.startswith('Bearer '):
                    tok = auth.split(' ', 1)[1].strip()
                    payload = jwt.decode(
                        tok, config.JWT_SECRET_KEY,
                        algorithms=[config.JWT_ALGORITHM],
                        options={'verify_iss': False, 'verify_aud': False}
                    )
                    user_id = payload.get('user_id')
                    u = db.session.get(User, user_id) if user_id else None
                    if u:
                        org_id = u.organization_id
            except Exception:
                pass

            req = EnterpriseRequest(
                organization_id=org_id, user_id=user_id,
                full_name=full_name, email=email, company=company,
                phone=phone, machines=machines, requirements=requirements,
                status='pending',
            )
            db.session.add(req)
            db.session.commit()

            try:
                supers = User.query.filter_by(role='super_admin', is_active=True).all()
                for s in supers:
                    send_email(
                        s.email,
                        f"New Enterprise Request: {company}",
                        f"""<h2>New Enterprise Plan Request</h2>
                        <p><strong>Company:</strong> {company}</p>
                        <p><strong>Name:</strong> {full_name}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Phone:</strong> {phone or 'N/A'}</p>
                        <p><strong>Machines:</strong> {machines or 'N/A'}</p>
                        <p><strong>Requirements:</strong></p>
                        <pre>{requirements or '(none)'}</pre>"""
                    )
            except Exception:
                logger.exception('Enterprise admin notify failed')

            try:
                broadcast_both('enterprise_request_created', {
                    'request': req.to_dict(),
                }, org_id=org_id)
            except Exception:
                pass

            return jsonify({
                'success': True,
                'message': 'Request submitted. Our team will contact you within 24 hours.',
                'request_id': req.uuid,
            }), 201
        except Exception:
            db.session.rollback()
            logger.exception('Enterprise request failed')
            return jerr('Submission failed. Please try again.', 500)

    @billing_bp.route('/enterprise-requests', methods=['GET'])
    @login_required
    @admin_required
    def b_enterprise_list():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        q = EnterpriseRequest.query.order_by(EnterpriseRequest.created_at.desc())
        return jsonify({'success': True, **paginate(q, page, per_page)}), 200

    app.register_blueprint(payments_bp)
    app.register_blueprint(billing_bp)

    # ============================================================
    # DATASETS BLUEPRINT
    # ============================================================

    ds_bp = Blueprint('datasets', __name__, url_prefix='/api/v1/datasets')

    @ds_bp.route('/upload', methods=['POST'])
    @login_required
    def ds_upload():
        try:
            if 'file' not in request.files and 'dataset' not in request.files:
                return jerr('No file uploaded.', 400)
            file = request.files.get('file') or request.files.get('dataset')
            if not file.filename:
                return jerr('No file selected.', 400)
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
            if ext not in config.DATASET_EXTENSIONS:
                return jerr(
                    f'Type not allowed. Allowed: {", ".join(sorted(config.DATASET_EXTENSIONS))}',
                    400
                )
            orig = secure_filename_enhanced(file.filename)
            if not orig:
                return jerr('Invalid filename.', 400)
            plan = config.PLANS.get(str(g.organization.plan or 'free').lower(),
                                     config.PLANS['free'])
            max_gb = float(plan.get('max_storage_gb') or 0)
            org_root = Path(config.UPLOAD_FOLDER) / f'org_{g.organization.id}' / 'datasets'
            cur = (sum(p.stat().st_size for p in org_root.rglob('*') if p.is_file())
                   if org_root.exists() else 0)
            inc = int(request.content_length or 0)
            if max_gb and cur + inc > max_gb * (1024 ** 3):
                return jerr('Storage quota reached.', 413, quota_reached=True)
            filename = f"{uuid.uuid4().hex}_{orig}"
            org_root.mkdir(parents=True, exist_ok=True)
            fp = org_root / filename
            file.save(fp)
            try:
                publish_user_event(g.organization.id, 'dataset_uploaded', {
                    'filename': filename,
                    'original_filename': orig,
                })
            except Exception:
                pass
            return jsonify({
                'success': True, 'message': 'Uploaded',
                'filename': filename, 'original_filename': orig,
                'size_bytes': fp.stat().st_size
            }), 200
        except Exception as e:
            logger.exception('Upload failed')
            return jerr(str(e), 500)

    @ds_bp.route('', methods=['GET'])
    @login_required
    def ds_list():
        try:
            org_root = Path(config.UPLOAD_FOLDER) / f'org_{g.organization.id}' / 'datasets'
            files = []
            if org_root.exists():
                for p in sorted(org_root.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True):
                    if p.is_file():
                        files.append({
                            'filename': p.name,
                            'size_bytes': p.stat().st_size,
                            'uploaded_at': datetime.fromtimestamp(
                                p.stat().st_mtime, tz=timezone.utc
                            ).isoformat()
                        })
            return jsonify({'success': True, 'files': files, 'datasets': files}), 200
        except Exception as e:
            return jerr(str(e), 500)

    @ds_bp.route('/analyze', methods=['POST'])
    @login_required
    @limiter.limit(f"{config.RATE_LIMIT_AI} per hour")
    def ds_analyze():
        try:
            data = request.get_json(silent=True) or {}
            filename = data.get('filename')
            if not filename:
                return jerr('filename required.', 400)
            try:
                fp = org_dataset_path(filename, g.organization.id)
            except ValueError as e:
                return jerr(str(e), 400)
            if not fp.exists():
                return jerr('File not found.', 404)
            df = read_dataset_file(fp)
            profile = {
                'rows': len(df),
                'columns': len(df.columns),
                'column_names': list(df.columns),
                'numeric_columns': [c for c in df.columns
                                    if pd.api.types.is_numeric_dtype(df[c])],
                'missing_values': {c: int(df[c].isna().sum())
                                   for c in df.columns if df[c].isna().any()},
            }
            return jsonify({'success': True, 'profile': profile}), 200
        except Exception:
            logger.exception('Analyze failed')
            return jerr('Analyze failed.', 500)

    app.register_blueprint(ds_bp)

    # ============================================================
    # CAREERS / CONTACT / ENTERPRISE / APPLICATIONS
    # ============================================================

    careers_bp = Blueprint('careers', __name__, url_prefix='/api/v1/careers')

    @careers_bp.route('/submit', methods=['POST'])
    @limiter.limit(f"{config.RATE_LIMIT_CAREER} per hour")
    def career_submit():
        try:
            if request.content_type and 'multipart/form-data' in request.content_type:
                form = request.form
                full_name = normalize_name(form.get('full_name') or form.get('name'))
                email = normalize_email(form.get('email'))
                phone = normalize_name(form.get('phone'))
                position = normalize_name(form.get('position'))
                experience = form.get('experience') or ''
                cover_letter = form.get('cover_letter') or ''
                org_slug = form.get('organization_slug')
            else:
                data = request.get_json(silent=True) or {}
                full_name = normalize_name(data.get('full_name') or data.get('name'))
                email = normalize_email(data.get('email'))
                phone = normalize_name(data.get('phone'))
                position = normalize_name(data.get('position'))
                experience = data.get('experience') or ''
                cover_letter = data.get('cover_letter') or ''
                org_slug = data.get('organization_slug')

            if not full_name:
                return jerr('Full name is required.', 400)
            if not email or not EMAIL_REGEX.match(email):
                return jerr('Valid email is required.', 400)
            if not position:
                return jerr('Position is required.', 400)

            org = None
            if org_slug:
                org = Organization.query.filter_by(slug=org_slug).first()
            if not org:
                org = Organization.query.order_by(Organization.created_at.asc()).first()

            resume_path = None
            resume_filename = None
            if 'resume' in request.files:
                resume = request.files['resume']
                if resume and resume.filename:
                    r_ext = (resume.filename.rsplit('.', 1)[-1].lower()
                             if '.' in resume.filename else '')
                    if r_ext not in config.RESUME_EXTENSIONS:
                        return jerr(
                            f'Resume must be one of: {", ".join(sorted(config.RESUME_EXTENSIONS))}',
                            400
                        )
                    r_dir = Path(config.UPLOAD_FOLDER) / 'resumes'
                    r_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = secure_filename_enhanced(resume.filename)
                    r_path = r_dir / safe_name
                    resume.save(str(r_path))
                    resume_path = f"/uploads/resumes/{safe_name}"
                    resume_filename = resume.filename

            sub = CareerSubmission(
                organization_id=org.id if org else None,
                full_name=full_name, email=email, phone=phone,
                position=position, experience=experience,
                cover_letter=cover_letter,
                resume_path=resume_path,
                resume_filename=resume_filename,
                status='pending'
            )
            db.session.add(sub)
            db.session.commit()

            if CAREER_SUBMISSIONS:
                CAREER_SUBMISSIONS.labels(status='received').inc()
            logger.info(f"Career submission: {email} for {position}")

            return jsonify({
                'success': True,
                'message': 'Application submitted successfully.',
                'submission_id': sub.uuid
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.exception('Career submission failed')
            return jerr(str(e) or 'Submission failed.', 500)

    app.register_blueprint(careers_bp)

    contact_bp = Blueprint('contact', __name__, url_prefix='/api/v1/contact')

    @contact_bp.route('/submit', methods=['POST'])
    @contact_bp.route('', methods=['POST'])
    @limiter.limit(f"{config.RATE_LIMIT_CONTACT} per hour")
    def contact_submit():
        try:
            data = request.get_json(silent=True) or {}
            if request.content_type and 'multipart/form-data' in request.content_type:
                data = dict(request.form)

            full_name = normalize_name(
                data.get('full_name') or data.get('name')
                or (f"{data.get('first_name','')} {data.get('last_name','')}".strip())
            )
            email = normalize_email(data.get('email'))
            phone = normalize_name(data.get('phone'))
            subject = normalize_name(data.get('subject'))
            message = data.get('message') or ''
            org_slug = data.get('organization_slug')

            if not full_name:
                return jerr('Full name is required.', 400)
            if not email or not EMAIL_REGEX.match(email):
                return jerr('Valid email is required.', 400)
            if not subject:
                return jerr('Subject is required.', 400)
            if not message or len(message.strip()) < 5:
                return jerr('Message must be at least 5 characters.', 400)

            org = None
            if org_slug:
                org = Organization.query.filter_by(slug=org_slug).first()
            if not org:
                org = Organization.query.order_by(Organization.created_at.asc()).first()

            sub = ContactSubmission(
                organization_id=org.id if org else None,
                full_name=full_name, email=email, phone=phone,
                subject=subject, message=message, status='pending'
            )
            db.session.add(sub)
            db.session.commit()

            if CONTACT_SUBMISSIONS:
                CONTACT_SUBMISSIONS.labels(status='received').inc()
            logger.info(f"Contact submission: {email} — {subject}")

            return jsonify({
                'success': True,
                'message': 'Message sent.',
                'submission_id': sub.uuid
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.exception('Contact submission failed')
            return jerr(str(e) or 'Submission failed.', 500)

    app.register_blueprint(contact_bp)

    enterprise_bp = Blueprint('enterprise', __name__, url_prefix='/api/v1/enterprise')

    @enterprise_bp.route('/request', methods=['POST'])
    def enterprise_request():
        try:
            data = request.get_json(silent=True) or {}
            company = normalize_name(data.get('company') or data.get('organization'))
            full_name = normalize_name(data.get('full_name') or data.get('name'))
            email = normalize_email(data.get('email'))
            phone = normalize_name(data.get('phone'))
            message = data.get('message') or data.get('requirements') or ''
            machines_range = data.get('machines') or ''

            if not full_name or not email or not company:
                return jerr('Name, email, and company are required.', 400)
            if not EMAIL_REGEX.match(email):
                return jerr('Invalid email address.', 400)

            req = EnterpriseRequest(
                full_name=full_name, email=email, company=company,
                phone=phone, machines=machines_range, requirements=message,
                status='pending',
            )
            db.session.add(req)
            db.session.commit()

            try:
                broadcast_both('enterprise_request_created',
                               {'request': req.to_dict()})
            except Exception:
                pass

            return jsonify({
                'success': True,
                'message': 'Request submitted. Our team will contact you shortly.',
                'request_id': req.uuid,
            }), 201
        except Exception:
            db.session.rollback()
            logger.exception('Enterprise request failed')
            return jerr('Submission failed.', 500)

    app.register_blueprint(enterprise_bp)

    apps_bp = Blueprint('applications', __name__, url_prefix='/api/v1/applications')

    @apps_bp.route('', methods=['POST'])
    def apps_submit():
        return career_submit()

    @apps_bp.route('', methods=['GET'])
    @login_required
    def apps_list():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        q = CareerSubmission.query.filter_by(organization_id=g.organization.id)\
            .order_by(CareerSubmission.created_at.desc())
        return jsonify({'success': True, **paginate(q, page, per_page)}), 200

    app.register_blueprint(apps_bp)

    # ============================================================
    # AUDIT LOG
    # ============================================================

    audit_bp = Blueprint('audit', __name__, url_prefix='/api/v1/audit')

    @audit_bp.route('/log', methods=['POST'])
    def audit_log_endpoint():
        try:
            data = request.get_json() or {}
            try:
                log_audit(
                    action=data.get('action') or 'client_event',
                    rtype=data.get('resource_type') or 'client',
                    rid=data.get('resource_id'),
                    changes={'description': data.get('description')},
                    user_id=data.get('user_id')
                )
            except Exception:
                pass
            return jsonify({'success': True}), 200
        except Exception:
            return jsonify({'success': True}), 200

    app.register_blueprint(audit_bp)

    # ============================================================
    # TENANTS
    # ============================================================

    tenants_bp = Blueprint('tenants', __name__, url_prefix='/api/v1')

    @tenants_bp.route('/tenants', methods=['GET'])
    @login_required
    def list_tenants():
        return jsonify({
            'success': True,
            'tenants': [g.organization.to_dict()],
            'current': g.organization.id
        }), 200

    @tenants_bp.route('/tenant/switch', methods=['POST'])
    @login_required
    def switch_tenant():
        return jsonify({
            'success': True,
            'tenant': g.organization.to_dict()
        }), 200

    app.register_blueprint(tenants_bp)

    # Public operational status page. Exposes aggregate health only, never secrets.
    @app.route('/status')
    def status_page():
        try:
            db.session.execute(text('SELECT 1'))
            db_ok = True
        except Exception:
            db_ok = False
        redis_ok = False
        if redis_client:
            try:
                redis_ok = bool(redis_client.ping())
            except Exception:
                pass
        model_count = len(ml_engine.models)
        production_count = len(ml_engine.production_ids)
        try:
            total_predictions = Prediction.query.count() if db_ok else 0
        except Exception:
            total_predictions = 0
        status_html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Status | {config.APP_NAME}</title>
        <style>body{{font-family:system-ui,sans-serif;background:#0f2b3d;color:#fff;margin:0;padding:3rem 1rem}}main{{max-width:620px;margin:auto;background:#fff;color:#0f172a;border-radius:18px;padding:2rem}}.row{{display:flex;justify-content:space-between;padding:.8rem 0;border-bottom:1px solid #e2e8f0}}.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px}}.up{{background:#10b981}}.warn{{background:#f59e0b}}.down{{background:#ef4444}}</style></head><body><main><h1>{config.APP_NAME} status</h1><p>Updated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
        <div class="row"><span><i class="dot {'up' if db_ok else 'down'}"></i>Database</span><b>{'Operational' if db_ok else 'Down'}</b></div>
        <div class="row"><span><i class="dot {'up' if redis_ok else 'warn'}"></i>Realtime cache</span><b>{'Operational' if redis_ok else 'Degraded / not configured'}</b></div>
        <div class="row"><span><i class="dot {'up' if model_count else 'warn'}"></i>ML models</span><b>{model_count} registered · {production_count} production-ready</b></div>
        <div class="row"><span>Stored predictions</span><b>{total_predictions:,}</b></div><p>v{config.APP_VERSION}</p></main></body></html>"""
        return Response(status_html, mimetype='text/html')

    @app.route('/api/v1/demo/seed', methods=['POST'])
    @login_required
    def seed_demo():
        """Idempotent sample data endpoint restricted to the explicit demo account."""
        if (getattr(g.user, 'email', '') or '').strip().lower() != 'demo@synapsepm.com':
            return jerr('Demo seeding is restricted to the demo account.', 403)
        org = g.organization
        existing = Machine.query.filter_by(organization_id=org.id, is_deleted=False).filter(Machine.name != '__dataset__').count()
        if existing >= 3:
            return jsonify({'success': True, 'message': 'Demo already seeded', 'machines': existing}), 200
        specs = [
            {'name': 'Pump P-201', 'type': 'pump', 'location': 'Plant A, Line 1', 'health': 82, 'status': 'online'},
            {'name': 'Turbine T-105', 'type': 'turbine', 'location': 'Plant A, Line 2', 'health': 54, 'status': 'warning'},
            {'name': 'Compressor C-330', 'type': 'compressor', 'location': 'Plant B, Bay 4', 'health': 91, 'status': 'online'},
        ]
        created = []
        try:
            for spec in specs:
                m = Machine(name=spec['name'], machine_type=spec['type'], location=spec['location'],
                            status=spec['status'], health=spec['health'], organization_id=org.id,
                            owner_id=g.user.id, machine_data={'dataset_family': spec['type'], 'connection': 'manual'})
                db.session.add(m)
                db.session.flush()
                created.append(m)
                for i in range(20):
                    rul = max(5.0, (240 if spec['status'] == 'online' else 36) - i * 3)
                    risk = 'critical' if rul < 24 else ('warning' if rul < 72 else 'low')
                    db.session.add(Prediction(request_id=f'demo-{m.id}-{i}-{uuid.uuid4().hex[:8]}',
                        machine_id=m.id, organization_id=org.id, user_id=g.user.id, rul_hours=rul,
                        confidence=float(max(60, min(99, 85 + random.randint(-8, 10)))), status='critical' if risk == 'critical' else ('warning' if risk == 'warning' else 'healthy'),
                        model_type='demo_sample', model_version='demo-1', risk_level=risk,
                        risk_score=max(0.0, min(100.0, 100.0 - rul / 240.0 * 100.0)),
                        recommendations=['Sample data only: run a real model prediction before acting on this result.'],
                        source='demo', created_at=datetime.now(timezone.utc) - timedelta(days=i)))
                for i in range(3 if spec['status'] == 'warning' else 1):
                    sev = 'critical' if spec['status'] == 'warning' and i == 0 else 'warning'
                    db.session.add(Alert(machine_id=m.id, organization_id=org.id, title=f"{m.name}: {sev.upper()} demo alert",
                        message='Sample alert generated by demo seeding; not a live sensor event.', severity=sev,
                        category='demo', source='demo', status='active', email_status={'sent': False, 'reason': 'demo sample; no email sent'}))
            db.session.commit()
            try:
                broadcast_both('machine_created', {'machine': created[0].to_dict()}, org_id=org.id)
            except Exception:
                logger.debug('Demo realtime broadcast unavailable', exc_info=True)
            return jsonify({'success': True, 'message': 'Demo sample data created; it is not real inference.', 'machines': [m.to_dict() for m in created]}), 201
        except Exception as exc:
            db.session.rollback()
            logger.exception('Demo seed failed')
            return jerr('Could not seed demo data.', 500)

    # ============================================================
    # REPORTS — REAL DATA GENERATION
    # ============================================================

    def _gen_report_content(data, user, org):
        scope = data.get('scope') or {}
        machine_ids = scope.get('machine_ids') or data.get('machine_ids') or []
        date_from = scope.get('date_from') or data.get('date_from')
        date_to = scope.get('date_to') or data.get('date_to')

        def parse_dt(v):
            if not v:
                return None
            try:
                return datetime.fromisoformat(str(v).replace('Z', '+00:00'))
            except Exception:
                return None

        dt_from = parse_dt(date_from)
        dt_to = parse_dt(date_to)

        mq = Machine.query.filter_by(organization_id=org.id, is_deleted=False)
        if machine_ids:
            mq = mq.filter(Machine.id.in_(machine_ids))
        machines = mq.all()

        lines = []
        lines.append('=' * 78)
        lines.append(f'  {config.APP_NAME} — MAINTENANCE INTELLIGENCE REPORT')
        lines.append('=' * 78)
        lines.append(f'  Organization : {org.name}')
        lines.append(f'  Generated by : {user.display_name or user.email}')
        lines.append(f'  Generated at : {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
        lines.append(f'  Scope        : {len(machines)} machine(s)')
        if dt_from or dt_to:
            lines.append(f'  Date range   : {dt_from or "beginning"} → {dt_to or "now"}')
        lines.append('=' * 78)
        lines.append('')

        # Bulk prefetch for all machines to avoid two SQL queries per machine.
        machine_ids_list = [m.id for m in machines]
        all_preds_by_machine = {}
        all_alerts_by_machine = {}
        if machine_ids_list:
            pq_bulk = Prediction.query.filter(Prediction.machine_id.in_(machine_ids_list))
            if dt_from:
                pq_bulk = pq_bulk.filter(Prediction.created_at >= dt_from)
            if dt_to:
                pq_bulk = pq_bulk.filter(Prediction.created_at <= dt_to)
            for _p in pq_bulk.order_by(Prediction.created_at.desc()).all():
                bucket = all_preds_by_machine.setdefault(_p.machine_id, [])
                if len(bucket) < 20:
                    bucket.append(_p)
            aq_bulk = Alert.query.filter(Alert.machine_id.in_(machine_ids_list))
            if dt_from:
                aq_bulk = aq_bulk.filter(Alert.created_at >= dt_from)
            if dt_to:
                aq_bulk = aq_bulk.filter(Alert.created_at <= dt_to)
            for _a in aq_bulk.order_by(Alert.created_at.desc()).all():
                bucket = all_alerts_by_machine.setdefault(_a.machine_id, [])
                if len(bucket) < 20:
                    bucket.append(_a)

        grand_total_alerts = 0
        grand_critical = 0
        grand_avg_rul = 0
        grand_count = 0

        for m in machines:
            lines.append('─' * 78)
            lines.append(f'MACHINE: {m.name}')
            lines.append('─' * 78)
            lines.append(f'  Type            : {m.machine_type}')
            lines.append(f'  Location        : {m.location or "N/A"}')
            lines.append(f'  Status          : {m.status}')
            lines.append(f'  Health          : {m.health}%')
            lines.append(f'  Temperature     : {m.temperature or 0:.1f}°C')
            lines.append(f'  Vibration       : {m.vibration or 0:.2f} mm/s')
            lines.append(f'  Pressure        : {m.pressure or 0:.1f}')
            lines.append('')

            preds = all_preds_by_machine.get(m.id, [])
            alerts = all_alerts_by_machine.get(m.id, [])

            if preds:
                latest = preds[0]
                confidence_values = [
                    float(p.confidence) for p in preds if p.confidence is not None
                ]
                rul_values = [
                    float(p.rul_hours) for p in preds if p.rul_hours is not None
                ]
                avg_conf = (
                    sum(confidence_values) / len(confidence_values)
                    if confidence_values else None
                )
                avg_rul = sum(rul_values) / len(rul_values) if rul_values else None
                if avg_rul is not None:
                    grand_avg_rul += avg_rul
                    grand_count += 1
                latest_rul = float(latest.rul_hours) if latest.rul_hours is not None else None
                risk = str(latest.risk_level or 'unknown').lower()
                lines.append(f'  PREDICTIONS ({len(preds)} records)')
                lines.append(f'    Latest RUL     : {latest_rul:.1f} hours' if latest_rul is not None
                             else '    Latest RUL     : unavailable')
                lines.append(f'    Latest Model   : {latest.model_type or "unknown"} v{latest.model_version or "?"}')
                lines.append(f'    Avg Confidence : {avg_conf:.1f}%' if avg_conf is not None
                             else '    Avg Confidence : unavailable')
                lines.append(f'    Avg RUL (20)   : {avg_rul:.1f} hours' if avg_rul is not None
                             else '    Avg RUL (20)   : unavailable')
                lines.append(f'    Risk Level     : {risk}')
                lines.append(f'    Health Score   : {m.health if m.health is not None else "unavailable"}%')
                if risk in ('critical', 'high') or (latest_rul is not None and latest_rul < 24):
                    recommendation = 'Inspect immediately; plan controlled shutdown and maintenance.'
                elif risk in ('warning', 'medium') or (latest_rul is not None and latest_rul < 72):
                    recommendation = 'Schedule maintenance soon and monitor sensor trends closely.'
                else:
                    recommendation = 'Continue monitoring; follow the manufacturer maintenance schedule.'
                lines.append(f'    Recommendation : {recommendation}')
                lines.append('    Recent predictions:')
                for p in preds[:5]:
                    p_rul = float(p.rul_hours) if p.rul_hours is not None else None
                    p_conf = float(p.confidence) if p.confidence is not None else None
                    stamp = p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else 'unknown time'
                    rul_text = f'{p_rul:.1f}h' if p_rul is not None else 'RUL unavailable'
                    conf_text = f'{p_conf:.0f}% conf' if p_conf is not None else 'confidence unavailable'
                    lines.append(f'      • {stamp} — {rul_text} ({conf_text})')
                lines.append('')
            else:
                lines.append('  PREDICTIONS: No predictions in scope.')
                lines.append('')

            if alerts:
                grand_total_alerts += len(alerts)
                grand_critical += sum(1 for a in alerts if a.severity == 'critical')
                lines.append(f'  ALERTS ({len(alerts)} records)')
                for a in alerts[:10]:
                    lines.append(f'    • [{a.severity.upper()}] '
                                 f'{a.created_at.strftime("%Y-%m-%d %H:%M")} — {a.title}')
                lines.append('')
            else:
                lines.append('  ALERTS: No alerts in scope.')
                lines.append('')

        lines.append('=' * 78)
        lines.append('  SUMMARY')
        lines.append('=' * 78)
        lines.append(f'  Total machines analyzed   : {len(machines)}')
        lines.append(f'  Machines with predictions : {grand_count}')
        if grand_count:
            lines.append(f'  Fleet avg RUL             : {grand_avg_rul / grand_count:.1f} hours')
        lines.append(f'  Total alerts              : {grand_total_alerts}')
        lines.append(f'  Critical alerts           : {grand_critical}')
        lines.append('')
        lines.append(f'  Report ID: {uuid.uuid4()}')
        lines.append(f'  Generated by {config.APP_NAME} v{config.APP_VERSION}')
        lines.append('=' * 78)
        return '\n'.join(lines)

    def _save_report(report, content):
        d = (Path(config.DOWNLOAD_FOLDER).expanduser().resolve() / 'reports').resolve()
        d.mkdir(parents=True, exist_ok=True)
        fmt = (report.format or 'pdf').lower()
        fn = f"report_{report.uuid}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.{fmt}"
        fp = d / fn
        if fmt == 'pdf':
            if not REPORTLAB_AVAILABLE:
                fp = fp.with_suffix('.txt')
                fp.write_text(content, encoding='utf-8')
                return str(fp.resolve())
            doc = SimpleDocTemplate(
                str(fp), pagesize=A4,
                rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
            )
            styles = getSampleStyleSheet()
            story = []
            for line in content.splitlines():
                if line.strip():
                    story.append(Paragraph(
                        line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'),
                        styles['BodyText']
                    ))
                else:
                    story.append(Spacer(1, 6))
            doc.build(story)
        elif fmt == 'json':
            fp.write_text(json.dumps({'report': content}, indent=2), encoding='utf-8')
        else:
            fp.write_text(content, encoding='utf-8')
        return str(fp.resolve())

    rp_bp = Blueprint('reports', __name__, url_prefix='/api/v1/reports')

    @rp_bp.route('', methods=['GET'])
    @login_required
    def rp_list():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        if getattr(g.user, 'role', None) in ('super_admin', 'admin'):
            q = Report.query.order_by(Report.created_at.desc())
        else:
            q = Report.query.filter_by(organization_id=g.organization.id)\
                .order_by(Report.created_at.desc())
        result = paginate(q, page, per_page)
        # Enrich the system-wide admin view with the real report owner.
        if getattr(g.user, 'role', None) in ('super_admin', 'admin'):
            enriched = []
            for item in result.get('items', []):
                row = dict(item)
                owner_id = row.get('user_id')
                owner = db.session.get(User, owner_id) if owner_id else None
                row['user_name'] = (owner.display_name or owner.username or owner.email) if owner else 'Unknown'
                row['user_email'] = owner.email if owner else None
                enriched.append(row)
            result['items'] = enriched
        result['reports'] = result['items']
        return jsonify({'success': True, **result}), 200

    @rp_bp.route('', methods=['POST'])
    @login_required
    def rp_create():
        try:
            data = request.get_json() or {}
            report = Report(
                organization_id=g.organization.id,
                user_id=g.user.id,
                name=data.get('name') or f"Report {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
                type=data.get('type') or 'maintenance',
                format=(data.get('format') or 'pdf').lower(),
                parameters=data.get('scope') or {},
                status='pending',
            )
            db.session.add(report)
            db.session.flush()

            content = _gen_report_content(data, g.user, g.organization)
            fp = _save_report(report, content)
            report.status = 'completed'
            report.generated_at = datetime.now(timezone.utc)
            report.file_path = fp
            try:
                report.file_size = os.path.getsize(fp)
            except Exception:
                pass
            db.session.commit()

            try:
                broadcast_both('report_created', {'report': report.to_dict()},
                               org_id=g.organization.id)
            except Exception:
                pass

            return jsonify({
                'success': True,
                'report': report.to_dict(),
                'preview': content[:3000],
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.exception('Report create failed')
            return jerr(str(e), 500)

    @rp_bp.route('/generate', methods=['POST'])
    @login_required
    def rp_gen():
        return rp_create()

    @rp_bp.route('/<rid>', methods=['GET'])
    @login_required
    def rp_get(rid):
        rid = _uuid_or_404(rid, 'report_id')
        r = Report.query.filter_by(uuid=rid, organization_id=g.organization.id).first_or_404()
        return jsonify({'success': True, 'report': r.to_dict()}), 200

    @rp_bp.route('/<rid>/download', methods=['GET'])
    @login_required
    def rp_dl(rid):
        rid = _uuid_or_404(rid, 'report_id')
        if getattr(g.user, 'role', None) in ('super_admin', 'admin'):
            r = Report.query.filter_by(uuid=rid).first_or_404()
        else:
            r = Report.query.filter_by(uuid=rid, organization_id=g.organization.id).first_or_404()
        if str(r.status or '').lower() in ('pending', 'generating'):
            return jerr('Report is still generating. Retry shortly.', 425,
                        report_status=r.status, retry_after_seconds=5)

        # Try the stored absolute path, then known report-folder candidates.
        # Restrict candidate resolution to the configured download/report folders.
        download_root = Path(config.DOWNLOAD_FOLDER).expanduser().resolve()
        report_root = (download_root / 'reports').resolve()
        candidates = []
        if r.file_path:
            stored = Path(r.file_path).expanduser()
            candidates.append(stored.resolve() if stored.is_absolute()
                             else (project_root / stored).resolve())
            candidates.append((report_root / stored.name).resolve())
            candidates.append((download_root / stored.name).resolve())
        existing_path = None
        for candidate in candidates:
            try:
                if candidate.is_file() and (
                    candidate == report_root or report_root in candidate.parents
                    or candidate == download_root or download_root in candidate.parents
                ):
                    existing_path = candidate
                    break
            except (OSError, ValueError):
                continue
        if existing_path is None:
            logger.warning('Report file missing: report_uuid=%s status=%s stored_path=%s',
                           r.uuid, r.status, r.file_path)
            return jerr('Report file not found on server. Regenerate the report.', 404,
                        report_status=r.status)
        r.file_path = str(existing_path)
        r.download_count = (r.download_count or 0) + 1
        db.session.add(Download(
            user_id=g.user.id, organization_id=r.organization_id,
            name=f'Report: {r.name}', type='report', version='1',
            file_path=r.file_path, file_size=r.file_size,
            platform='web', ip_address=request.remote_addr,
            metadata_json={'report_uuid': r.uuid, 'format': r.format}
        ))
        db.session.commit()
        try:
            broadcast_both('download_created', {
                'download': {'type': 'report', 'report_id': r.uuid,
                             'user_id': str(g.user.id), 'user_name': g.user.display_name or g.user.email}
            }, org_id=r.organization_id)
        except Exception:
            logger.debug('report download broadcast failed', exc_info=True)
        ext = (r.format or 'pdf').lower()
        mime = ('application/pdf' if ext == 'pdf'
                else ('application/json' if ext == 'json' else 'text/plain'))
        return send_file(str(existing_path), as_attachment=True,
                         download_name=os.path.basename(str(existing_path)),
                         mimetype=mime, conditional=True, max_age=0)

    @rp_bp.route('/downloads', methods=['GET'])
    @login_required
    def rp_download_history():
        page = max(1, request.args.get('page', 1, type=int))
        per_page = min(100, max(1, request.args.get('per_page', 20, type=int)))
        q = Download.query.filter(Download.type == 'report')
        if getattr(g.user, 'role', None) not in ('super_admin', 'admin'):
            q = q.filter_by(organization_id=g.organization.id)
        result = paginate(q.order_by(Download.created_at.desc()), page, per_page)
        return jsonify({'success': True, **result, 'downloads': result.get('items', [])}), 200

    app.register_blueprint(rp_bp)

    # ============================================================
    # ADMIN BLUEPRINT
    # ============================================================

    adm_bp = Blueprint('admin', __name__, url_prefix='/api/v1/admin')

    @adm_bp.route('/rate-limits', methods=['GET', 'PUT'])
    @admin_required
    def adm_rate_limits():
        if request.method == 'GET':
            caps = {}
            if redis_client:
                for org in Organization.query.filter_by(is_deleted=False).all():
                    raw = redis_client.get(f'ratecap:org:{org.id}')
                    if raw:
                        caps[str(org.id)] = int(raw)
            return jsonify({'success': True, 'default_org_daily_ai_cap': config.ORG_DAILY_AI_CAP, 'organization_caps': caps}), 200
        data = request.get_json() or {}
        org_id = data.get('organization_id')
        cap = data.get('daily_ai_cap')
        if not org_id or cap is None or int(cap) < 0:
            return jerr('organization_id and non-negative daily_ai_cap required.', 400)
        if not redis_client:
            return jerr('Redis required to update runtime rate limits.', 503)
        org = db.session.get(Organization, _uuid_or_404(org_id, 'organization_id'))
        if not org:
            return jerr('Organization not found.', 404)
        redis_client.set(f'ratecap:org:{org.id}', int(cap))
        return jsonify({'success': True, 'organization_id': org.id, 'daily_ai_cap': int(cap)}), 200

    @adm_bp.route('/rotate-keys', methods=['POST'])
    @admin_required
    def adm_rotate_keys():
        # Runtime JWT rotation intentionally invalidates existing access/refresh tokens.
        # Persistent secret rotation must also update the deployment secret store.
        config.JWT_SECRET_KEY = secrets.token_urlsafe(64)
        config.JWT_REFRESH_SECRET = secrets.token_urlsafe(64)
        try:
            for u in User.query.filter_by(is_active=True).all():
                session_manager.revoke_all_sessions(u.id)
                jwt_blacklist.revoke_all_user_tokens(u.id)
        except Exception:
            db.session.rollback()
            logger.exception('JWT key rotation session invalidation failed')
            return jerr('Key rotation failed.', 500)
        return jsonify({'success': True, 'rotated': ['JWT_SECRET_KEY', 'JWT_REFRESH_SECRET'], 'warning': 'Persist the new keys in the platform secret store before restart; encryption and Paddle keys were not rotated automatically.'}), 200

    @adm_bp.route('/stats', methods=['GET'])
    @admin_required
    def adm_stats():
        global_admin = g.user.role in ('super_admin', 'admin')
        users_q = User.query if global_admin else User.query.filter_by(organization_id=g.organization.id)
        machines_q = Machine.query.filter(Machine.is_deleted.is_(False), Machine.name != '__dataset__')
        predictions_q = Prediction.query
        reports_q = Report.query
        downloads_q = Download.query
        payments_q = Payment.query
        orgs_q = Organization.query if global_admin else Organization.query.filter_by(id=g.organization.id)
        alerts_q = Alert.query.join(Machine, Alert.machine_id == Machine.id)
        enterprise_q = EnterpriseRequest.query
        if not global_admin:
            machines_q = machines_q.filter_by(organization_id=g.organization.id)
            predictions_q = predictions_q.filter_by(organization_id=g.organization.id)
            reports_q = reports_q.filter_by(organization_id=g.organization.id)
            downloads_q = downloads_q.filter_by(organization_id=g.organization.id)
            payments_q = payments_q.filter_by(organization_id=g.organization.id)
            alerts_q = alerts_q.filter(Machine.organization_id == g.organization.id)
            enterprise_q = enterprise_q.filter(EnterpriseRequest.organization_id == g.organization.id)
        return jsonify({
            'success': True,
            'stats': {
                'total_users': users_q.count(),
                'active_users': users_q.filter_by(is_active=True).count(),
                'paid_users': users_q.filter(User.is_active.is_(True), func.lower(User.plan) != 'free').count(),
                'paid_plans': users_q.filter(User.is_active.is_(True), func.lower(User.plan) != 'free').count(),
                'total_machines': machines_q.count(),
                'active_machines': machines_q.filter_by(status='online').count(),
                'connected_machines': machines_q.filter_by(status='online').count(),
                'total_predictions': predictions_q.count(),
                'total_alerts': alerts_q.count(),
                'active_alerts': alerts_q.filter(Alert.status == 'active').count(),
                'total_reports': reports_q.count(),
                'total_downloads': downloads_q.count(),
                'total_payments': payments_q.count(),
                'active_subscriptions': orgs_q.filter(Organization.subscription_status == 'active', func.lower(Organization.plan) != 'free').count(),
                'organizations': orgs_q.count(),
                'trialing_organizations': orgs_q.filter_by(subscription_status='trialing').count(),
                'expired_organizations': orgs_q.filter_by(subscription_status='expired').count(),
                'production_champions': len(ml_engine.list_models()),
                'registered_models': len(ml_engine.list_all_registered()),
                'enterprise_requests': enterprise_q.count(),
                'pending_enterprise_requests': enterprise_q.filter_by(status='pending').count(),
            }
        }), 200

    @adm_bp.route('/users', methods=['GET'])
    @admin_required
    def adm_users_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            q = User.query.order_by(User.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.filter_by(organization_id=g.organization.id)
            result = paginate(q, page, per_page)
            users_out = []
            for u in result['items']:
                ud = u
                try:
                    mc = Machine.query.filter_by(
                        owner_id=u.get('id'), is_deleted=False
                    ).count()
                    ud['machines'] = mc
                except Exception:
                    ud['machines'] = 0
                ud['name'] = (ud.get('display_name') or ud.get('full_name')
                              or ud.get('username') or ud.get('email'))
                users_out.append(ud)
            return jsonify({
                'success': True,
                'users': users_out,
                'items': users_out,
                'total': result['total'],
            }), 200
        except Exception as e:
            logger.exception('adm_users_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'users': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/users', methods=['POST'])
    @admin_required
    def adm_users_create():
        try:
            data = request.get_json() or {}
            email = normalize_email(data.get('email'))
            name = normalize_name(data.get('name'))
            password = data.get('password') or 'Temp@' + secrets.token_hex(4)
            plan = (data.get('plan') or 'free').lower()

            if not email or not name:
                return jerr('Name and email required.', 400)
            policy_error = password_policy_error(password)
            if policy_error:
                return jerr(policy_error, 400)
            if not EMAIL_REGEX.match(email):
                return jerr('Invalid email.', 400)
            if User.query.filter_by(email=email).first():
                return jerr('Email already exists.', 409)

            username = re.sub(r'[^a-zA-Z0-9_]', '', email.split('@')[0]).lower() or 'user'
            base = username
            c = 1
            while User.query.filter_by(username=username).first():
                c += 1
                username = f'{base}{c}'

            new_user = User(
                organization_id=g.organization.id,
                username=username, email=email,
                display_name=name, first_name=name.split(' ')[0],
                last_name=' '.join(name.split(' ')[1:]) if ' ' in name else '',
                role='viewer', plan=plan,
                is_active=True, is_verified=True,
                password_history=[]
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            log_audit('admin_create_user', 'user', new_user.id, {'email': email})
            broadcast_both('user_created', {'user': new_user.to_dict()},
                           org_id=g.organization.id)

            return jsonify({'success': True, 'user': new_user.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            logger.exception('adm_users_create failed')
            return jerr(str(e), 500)

    @adm_bp.route('/users/<user_id>', methods=['PUT'])
    @admin_required
    def adm_users_update(user_id):
        try:
            u = db.session.get(User, user_id)
            if not u or (g.user.role not in ('super_admin', 'admin') and str(u.organization_id) != str(g.organization.id)):
                return jerr('User not found.', 404)
            data = request.get_json() or {}
            if 'name' in data and data['name']:
                u.display_name = normalize_name(data['name'])
                parts = u.display_name.split(' ')
                u.first_name = parts[0]
                u.last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
            if 'email' in data and data['email']:
                new_email = normalize_email(data['email'])
                existing = User.query.filter_by(email=new_email).first()
                if existing and existing.id != u.id:
                    return jerr('Email already in use.', 409)
                u.email = new_email
            if 'plan' in data:
                u.plan = (data['plan'] or 'free').lower()
            if 'is_active' in data:
                u.is_active = bool(data['is_active'])
            if 'password' in data and data['password']:
                policy_error = password_policy_error(data['password'])
                if policy_error:
                    return jerr(policy_error, 400)
                u.set_password(data['password'])
            db.session.commit()

            log_audit('admin_update_user', 'user', u.id, data)
            broadcast_both('user_updated', {'user': u.to_dict()},
                           org_id=u.organization_id)

            return jsonify({'success': True, 'user': u.to_dict()}), 200
        except Exception as e:
            db.session.rollback()
            logger.exception('adm_users_update failed')
            return jerr(str(e), 500)

    @adm_bp.route('/users/<user_id>', methods=['DELETE'])
    @admin_required
    def adm_users_delete(user_id):
        try:
            u = db.session.get(User, user_id)
            if not u or (g.user.role not in ('super_admin', 'admin') and str(u.organization_id) != str(g.organization.id)):
                return jerr('User not found.', 404)
            if u.role == 'super_admin' and u.email == config.ADMIN_EMAIL:
                return jerr('Cannot delete the super admin.', 403)
            u.is_active = False
            u.deactivated_at = datetime.now(timezone.utc)
            session_manager.revoke_all_sessions(u.id)
            db.session.commit()

            log_audit('admin_delete_user', 'user', u.id, {'email': u.email})
            broadcast_both('user_deleted', {'user_id': u.id},
                           org_id=u.organization_id)

            return jsonify({'success': True, 'message': 'User deactivated'}), 200
        except Exception as e:
            db.session.rollback()
            logger.exception('adm_users_delete failed')
            return jerr(str(e), 500)

    @adm_bp.route('/users/<user_id>/plan', methods=['PUT', 'POST'])
    @admin_required
    def adm_users_plan(user_id):
        try:
            u = db.session.get(User, user_id)
            if not u or (g.user.role not in ('super_admin', 'admin') and str(u.organization_id) != str(g.organization.id)):
                return jerr('User not found.', 404)
            data = request.get_json() or {}
            new_plan = (data.get('plan') or 'free').lower()
            u.plan = new_plan
            plan_cfg = config.PLANS.get(new_plan, config.PLANS['free'])
            org = db.session.get(Organization, u.organization_id)
            if org:
                org.plan = new_plan.upper()
                org.max_machines = plan_cfg.get('max_machines', 10)
                org.max_users = plan_cfg.get('max_users', 5)
                org.max_api_calls = plan_cfg.get('max_api_calls', 1000)
                org.max_storage_gb = plan_cfg.get('max_storage_gb', 1)
                org.subscription_status = 'active' if new_plan != 'free' else 'canceled'
            db.session.commit()

            log_audit('admin_change_plan', 'user', u.id, {'plan': new_plan})
            broadcast_both('user_updated', {'user': u.to_dict()},
                           org_id=u.organization_id)
            broadcast_both('billing_updated', {
                'organization': org.to_dict() if org else None,
            }, org_id=u.organization_id)

            return jsonify({'success': True, 'user': u.to_dict()}), 200
        except Exception as e:
            db.session.rollback()
            logger.exception('adm_users_plan failed')
            return jerr(str(e), 500)

    @adm_bp.route('/users/<user_id>/subscription/cancel', methods=['POST'])
    @admin_required
    def adm_users_cancel_sub(user_id):
        try:
            u = db.session.get(User, user_id)
            if not u or (g.user.role not in ('super_admin', 'admin') and str(u.organization_id) != str(g.organization.id)):
                return jerr('User not found.', 404)
            u.plan = 'free'
            org = db.session.get(Organization, u.organization_id)
            if org:
                org.plan = 'FREE'
                org.subscription_status = 'canceled'
            db.session.commit()
            log_audit('admin_cancel_subscription', 'user', u.id, {})
            broadcast_both('billing_updated', {
                'organization': org.to_dict() if org else None,
            }, org_id=u.organization_id)
            broadcast_both('user_updated', {'user': u.to_dict()}, org_id=u.organization_id)
            return jsonify({'success': True}), 200
        except Exception as e:
            db.session.rollback()
            return jerr(str(e), 500)

    @adm_bp.route('/machines', methods=['GET'])
    @admin_required
    def adm_machines_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 200, type=int)
            q = Machine.query.filter_by(is_deleted=False).filter(Machine.name != '__dataset__')\
                .order_by(Machine.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.filter_by(organization_id=g.organization.id)
            result = paginate(q, page, per_page)
            machines_out = []
            for m in result['items']:
                md = m
                try:
                    owner = (db.session.get(User, m.get('owner_id'))
                             if m.get('owner_id') else None)
                    md['owner_name'] = owner.display_name if owner else 'Unassigned'
                    md['owner'] = md['owner_name']
                except Exception:
                    md['owner_name'] = 'Unassigned'
                    md['owner'] = 'Unassigned'
                machines_out.append(md)
            return jsonify({
                'success': True,
                'machines': machines_out,
                'items': machines_out,
                'total': result['total'],
            }), 200
        except Exception as e:
            logger.exception('adm_machines_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'machines': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/machines', methods=['POST'])
    @admin_required
    def adm_machines_create():
        try:
            data = request.get_json() or {}
            name = data.get('name')
            owner_id = data.get('owner_id') or data.get('owner')
            location = data.get('location') or ''
            if not name:
                return jerr('Machine name required.', 400)
            owner = db.session.get(User, owner_id) if owner_id else None
            if owner_id and not owner:
                return jerr('Machine owner not found.', 404)
            if owner and g.user.role not in ('super_admin', 'admin') and str(owner.organization_id) != str(g.organization.id):
                return jerr('Cannot assign a machine to another organization.', 403)
            org_id = owner.organization_id if owner else g.organization.id
            m = Machine(
                name=name, machine_type=data.get('machine_type') or 'general',
                location=location, status='offline', health=100,
                organization_id=org_id, owner_id=owner.id if owner else None,
            )
            db.session.add(m)
            db.session.commit()
            log_audit('admin_create_machine', 'machine', m.id, {'name': name})
            broadcast_both('machine_created', {'machine': m.to_dict()},
                           org_id=org_id)
            return jsonify({'success': True, 'machine': m.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            logger.exception('adm_machines_create failed')
            return jerr(str(e), 500)

    @adm_bp.route('/machines/<machine_id>/block', methods=['POST'])
    @admin_required
    def adm_machine_block(machine_id):
        return _adm_set_machine_block(machine_id, True)

    @adm_bp.route('/machines/<machine_id>/unblock', methods=['POST'])
    @admin_required
    def adm_machine_unblock(machine_id):
        return _adm_set_machine_block(machine_id, False)

    def _adm_set_machine_block(machine_id, blocked):
        try:
            machine_id = _uuid_or_404(machine_id, 'machine_id')
            q = Machine.query.filter_by(id=machine_id, is_deleted=False)
            if g.user.role not in ('super_admin', 'admin'):
                q = q.filter_by(organization_id=g.organization.id)
            m = q.first_or_404()
            m.is_blocked = bool(blocked)
            m.status = 'blocked' if blocked else 'offline'
            m.blocked_at = datetime.now(timezone.utc) if blocked else None
            m.blocked_by = g.user.id if blocked else None
            db.session.commit()
            log_audit('admin_machine_block' if blocked else 'admin_machine_unblock', 'machine', m.id, {'blocked': blocked})
            broadcast_both('machine_updated', {'machine': m.to_dict()}, org_id=m.organization_id)
            return jsonify({'success': True, 'machine': m.to_dict()}), 200
        except Exception as e:
            db.session.rollback()
            logger.exception('Machine block/unblock failed')
            return jerr(str(e), 500)

    @adm_bp.route('/machines/<machine_id>', methods=['PUT'])
    @admin_required
    def adm_machines_update(machine_id):
        try:
            m = db.session.get(Machine, machine_id)
            if not m or m.is_deleted or (g.user.role not in ('super_admin', 'admin') and str(m.organization_id) != str(g.organization.id)):
                return jerr('Machine not found.', 404)
            data = request.get_json() or {}
            if 'is_blocked' in data:
                m.is_blocked = bool(data['is_blocked'])
                m.status = 'blocked' if m.is_blocked else 'offline'
                m.blocked_at = datetime.now(timezone.utc) if m.is_blocked else None
                m.blocked_by = g.user.id if m.is_blocked else None
            if 'take_offline' in data and bool(data['take_offline']):
                m.status = 'offline'
                m.is_blocked = False
                m.blocked_at = None
                m.blocked_by = None
            for f in ['name', 'location', 'machine_type', 'health']:
                if f in data:
                    setattr(m, f, data[f])
            if 'status' in data:
                status = str(data['status']).strip().lower()
                if status not in {'online', 'offline', 'maintenance', 'blocked'}:
                    return jerr('Invalid machine status.', 400)
                m.status = status
                m.is_blocked = status == 'blocked'
                m.blocked_at = datetime.now(timezone.utc) if m.is_blocked else None
                m.blocked_by = g.user.id if m.is_blocked else None
            if 'owner_id' in data:
                owner_id = data.get('owner_id') or None
                owner = db.session.get(User, owner_id) if owner_id else None
                if owner_id and not owner:
                    return jerr('Machine owner not found.', 404)
                if owner and g.user.role not in ('super_admin', 'admin') and str(owner.organization_id) != str(g.organization.id):
                    return jerr('Cannot assign a machine to another organization.', 403)
                m.owner_id = owner.id if owner else None
                if owner:
                    m.organization_id = owner.organization_id
            db.session.commit()
            log_audit('admin_update_machine', 'machine', m.id, data)
            broadcast_both('machine_updated', {'machine': m.to_dict()},
                           org_id=m.organization_id)
            return jsonify({'success': True, 'machine': m.to_dict()}), 200
        except Exception as e:
            db.session.rollback()
            return jerr(str(e), 500)

    @adm_bp.route('/machines/<machine_id>', methods=['DELETE'])
    @admin_required
    def adm_machines_delete(machine_id):
        try:
            m = db.session.get(Machine, machine_id)
            if not m or (g.user.role not in ('super_admin', 'admin') and str(m.organization_id) != str(g.organization.id)):
                return jerr('Machine not found.', 404)
            org_id = m.organization_id
            m.soft_delete(g.user.id)
            db.session.commit()
            log_audit('admin_delete_machine', 'machine', machine_id, {})
            broadcast_both('machine_deleted', {'machine_id': machine_id},
                           org_id=org_id)
            return jsonify({'success': True}), 200
        except Exception as e:
            db.session.rollback()
            return jerr(str(e), 500)

    @adm_bp.route('/predictions', methods=['GET'])
    @admin_required
    def adm_predictions_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            q = Prediction.query.order_by(Prediction.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.filter_by(organization_id=g.organization.id)
            result = paginate(q, page, per_page)
            predictions_out = []
            audit_by_id = {}
            if g.user.role in ('super_admin', 'admin'):
                page_ids = [row.get('id') for row in result['items'] if row.get('id') is not None]
                if page_ids:
                    audit_by_id = {str(row.id): (row.model_selection_audit or {})
                                   for row in Prediction.query.filter(Prediction.id.in_(page_ids)).all()}
            for p in result['items']:
                pd = p
                try:
                    m = db.session.get(Machine, p.get('machine_id'))
                    pd['machine_name'] = m.name if m else 'Unknown'
                    owner = db.session.get(User, m.owner_id) if m and m.owner_id else None
                    pd['owner_name'] = owner.display_name if owner else 'Unassigned'
                    pd['owner'] = pd['owner_name']
                    pd['rul'] = p.get('rul_hours', 0)
                except Exception:
                    pd['machine_name'] = 'Unknown'
                    pd['owner_name'] = 'Unassigned'
                    pd['owner'] = 'Unassigned'
                if g.user.role in ('super_admin', 'admin'):
                    pd['model_selection_audit'] = audit_by_id.get(str(pd.get('id')), {})
                predictions_out.append(pd)
            stats_q = Prediction.query
            if g.user.role not in ('super_admin', 'admin'):
                stats_q = stats_q.filter_by(organization_id=g.organization.id)
            total = stats_q.count()
            avg_conf = db.session.query(func.avg(Prediction.confidence)).filter(
                Prediction.organization_id == g.organization.id
            ).scalar() if g.user.role not in ('super_admin', 'admin') else db.session.query(func.avg(Prediction.confidence)).scalar()
            avg_conf = avg_conf or 0
            return jsonify({
                'success': True,
                'predictions': predictions_out,
                'items': predictions_out,
                'total': result['total'],
                'model_stats': {
                    'average_confidence': float(avg_conf),
                    'total_predictions': total,
                }
            }), 200
        except Exception as e:
            logger.exception('adm_predictions_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'predictions': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/alerts', methods=['GET'])
    @admin_required
    def adm_alerts_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            q = Alert.query.order_by(Alert.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.join(Machine, Alert.machine_id == Machine.id).filter(Machine.organization_id == g.organization.id)
            result = paginate(q, page, per_page)
            alerts_out = []
            for a in result['items']:
                ad = a
                try:
                    m = db.session.get(Machine, a.get('machine_id'))
                    ad['machine_name'] = m.name if m else 'Unknown'
                    owner = db.session.get(User, m.owner_id) if m and m.owner_id else None
                    ad['user_name'] = owner.display_name if owner else 'Unassigned'
                    ad['user'] = ad['user_name']
                    ad['title'] = a.get('title') or a.get('message') or 'Alert'
                except Exception:
                    ad['machine_name'] = 'Unknown'
                    ad['user_name'] = 'Unassigned'
                    ad['user'] = 'Unassigned'
                alerts_out.append(ad)
            return jsonify({
                'success': True,
                'alerts': alerts_out,
                'items': alerts_out,
                'total': result['total'],
            }), 200
        except Exception as e:
            logger.exception('adm_alerts_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'alerts': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/downloads', methods=['GET'])
    @admin_required
    def adm_downloads_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            # PWA installs are installation events, not file downloads.
            # Keep them out of Download History; they are exposed by /installs.
            q = Download.query.filter(Download.type != 'app_install').order_by(Download.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.filter_by(organization_id=g.organization.id)
            result = paginate(q, page, per_page)
            downloads_out = []
            for d in result['items']:
                dd = d
                try:
                    u = db.session.get(User, d.get('user_id'))
                    dd['user_name'] = u.display_name if u else 'Guest'
                    dd['user'] = dd['user_name']
                    dd['status'] = 'completed'
                except Exception:
                    dd['user_name'] = 'Guest'
                    dd['user'] = 'Guest'
                    dd['status'] = 'completed'
                downloads_out.append(dd)
            return jsonify({
                'success': True,
                'downloads': downloads_out,
                'items': downloads_out,
                'total': result['total'],
            }), 200
        except Exception as e:
            logger.exception('adm_downloads_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'downloads': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/installs', methods=['GET'])
    @adm_bp.route('/software-installs', methods=['GET'])
    @admin_required
    def adm_pwa_installs_list():
        """Return PWA installation events separately from Download History."""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = min(100, max(1, request.args.get('per_page', 100, type=int)))
            q = Download.query.filter(Download.type == 'app_install').order_by(Download.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.filter_by(organization_id=g.organization.id)
            result = paginate(q, page, per_page)
            installs_out = []
            for row in result['items']:
                item = dict(row)
                try:
                    u = db.session.get(User, row.get('user_id'))
                    item['user_name'] = (u.display_name or u.email) if u else 'Guest'
                    item['user'] = item['user_name']
                except Exception:
                    item['user_name'] = 'Guest'; item['user'] = 'Guest'
                item['install_status'] = 'installed'; item['installed_at'] = item.get('created_at')
                installs_out.append(item)
            return jsonify({'success': True, 'installs': installs_out, 'software_installs': installs_out, 'items': installs_out, 'total': result['total']}), 200
        except Exception:
            logger.exception('adm_pwa_installs_list failed')
            return jsonify({'success': False, 'error': 'Could not load software installs.', 'installs': [], 'software_installs': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/activities', methods=['GET'])
    @admin_required
    def adm_activities_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            q = AuditLog.query.order_by(AuditLog.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.join(User, AuditLog.user_id == User.id).filter(User.organization_id == g.organization.id)
            result = paginate(q, page, per_page)
            activities_out = []
            for a in result['items']:
                ad = {
                    'id': a.get('id'),
                    'action': a.get('action'),
                    'target': a.get('resource_type', '') + (
                        ':' + str(a.get('resource_id')) if a.get('resource_id') else ''
                    ),
                    'admin_name': 'Admin',
                    'admin': 'Admin',
                    'created_at': a.get('created_at'),
                    'ip_address': a.get('ip_address'),
                }
                try:
                    uid = a.get('user_id')
                    if uid:
                        u = db.session.get(User, uid)
                        if u:
                            ad['admin_name'] = u.display_name or u.email
                            ad['admin'] = ad['admin_name']
                except Exception:
                    pass
                activities_out.append(ad)
            return jsonify({
                'success': True,
                'activities': activities_out,
                'items': activities_out,
                'total': result['total'],
            }), 200
        except Exception as e:
            logger.exception('adm_activities_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'activities': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/billing', methods=['GET'])
    @admin_required
    def adm_billing_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            q = Payment.query.order_by(Payment.created_at.desc())
            if g.user.role not in ('super_admin', 'admin'):
                q = q.filter_by(organization_id=g.organization.id)
            result = paginate(q, page, per_page)
            subs_out = []
            for p in result['items']:
                customer_email = (p.get('customer_email') or '').strip().lower()
                customer = User.query.filter(func.lower(User.email) == customer_email).first() if customer_email else None
                if not customer and p.get('organization_id'):
                    customer = User.query.filter_by(organization_id=p.get('organization_id')).order_by(User.created_at.asc()).first()
                display_name = (p.get('customer_name') or
                                ((customer.display_name or customer.username or customer.email) if customer else None) or
                                p.get('customer_email') or 'Unknown')
                subs_out.append({
                    'id': p.get('id'), 'user_id': customer.id if customer else None,
                    'user_name': display_name, 'user': display_name,
                    'user_email': p.get('customer_email'),
                    'plan': p.get('plan_id') or 'free',
                    'amount': p.get('amount', 0), 'currency': p.get('currency') or 'USD',
                    'gateway': p.get('gateway'), 'invoice_number': p.get('invoice_number'),
                    'status': p.get('status', 'pending'), 'created_at': p.get('created_at'),
                })

            revenue_q = Payment.query.filter_by(status='completed')
            active_q = Organization.query.filter(Organization.subscription_status == 'active', func.lower(Organization.plan) != 'free')
            if g.user.role not in ('super_admin', 'admin'):
                revenue_q = revenue_q.filter_by(organization_id=g.organization.id)
                active_q = active_q.filter_by(id=g.organization.id)
            total_rev = revenue_q.with_entities(func.sum(Payment.amount)).scalar() or 0
            active = active_q.count()

            return jsonify({
                'success': True,
                'subscriptions': subs_out,
                'items': subs_out,
                'total': len(subs_out),
                'stats': {
                    'total_revenue': float(total_rev),
                    'active_subscriptions': active,
                    # Payment records do not encode billing intervals, so MRR is unknown.
                    'mrr': None,
                }
            }), 200
        except Exception as e:
            logger.exception('adm_billing_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'subscriptions': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/system/backup', methods=['POST'])
    @admin_required
    def adm_system_backup():
        data = request.get_json(silent=True) or {}
        password = data.get('password')
        if g.user.role != 'super_admin':
            return jerr('Only a super administrator can create a system backup.', 403)
        if not password or not g.user.check_password(password):
            return jerr('Valid password is required for backup.', 401)
        try:
            backup_dir = os.path.abspath(os.environ.get('SYNAPSEPM_BACKUP_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'private_backups'))
            os.makedirs(backup_dir, mode=0o700, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            if db.engine.dialect.name == 'sqlite':
                source = db.engine.url.database
                if not source or not os.path.isfile(source):
                    return jerr('SQLite database file is unavailable for backup.', 503)
                target = os.path.join(backup_dir, f'synapsepm-{stamp}.sqlite3')
                shutil.copy2(source, target)
            elif db.engine.dialect.name == 'postgresql':
                import subprocess
                import shutil as _shutil
                pg_dump = _shutil.which('pg_dump')
                if not pg_dump:
                    return jerr('pg_dump is not installed on the server; configure automated database backups.', 503)
                target = os.path.join(backup_dir, f'synapsepm-{stamp}.sql')
                env = os.environ.copy()
                if db.engine.url.password:
                    env['PGPASSWORD'] = db.engine.url.password
                cmd = [pg_dump, '--no-owner', '--no-privileges', '--format=plain', '--file', target, '--host', db.engine.url.host or 'localhost', '--port', str(db.engine.url.port or 5432), '--username', db.engine.url.username or '', db.engine.url.database or '']
                result = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, check=False)
                if result.returncode != 0:
                    try: os.remove(target)
                    except OSError: pass
                    logger.error('pg_dump failed: %s', result.stderr.decode('utf-8', 'replace')[:1000])
                    return jerr('Database backup failed. Check server logs.', 503)
            else:
                return jerr(f'Automatic backup is not configured for {db.engine.dialect.name}.', 501)
            try: os.chmod(target, 0o600)
            except OSError: pass
            size = os.path.getsize(target)
            log_audit('admin_database_backup', 'system', None, {'filename': os.path.basename(target), 'size_bytes': size})
            return jsonify({'success': True, 'filename': os.path.basename(target), 'size_bytes': size, 'created_at': datetime.now(timezone.utc).isoformat()}), 201
        except Exception:
            db.session.rollback()
            logger.exception('System backup failed')
            return jerr('System backup failed. Check server logs.', 500)

    @adm_bp.route('/system/status', methods=['GET'])
    @admin_required
    def adm_system_status():
        try:
            db.session.execute(text('SELECT 1'))
            db_status = 'connected'
        except Exception:
            db.session.rollback()
            db_status = 'unavailable'
        redis_status = False
        if redis_client:
            try:
                redis_status = bool(redis_client.ping())
            except Exception:
                redis_status = False
        online = _get_system_online()
        if db_status != 'connected':
            return jsonify({
                'success': False, 'online': online, 'database': db_status,
                'redis': redis_status, 'realtime': redis_status,
                'mqtt': bool(_mqtt_client), 'version': config.APP_VERSION,
                'error': 'Database health check failed',
            }), 503
        mail_mode = ('suppressed' if config.MAIL_SUPPRESS_SEND or not config.MAIL_USERNAME else 'live')
        return jsonify({
            'success': True, 'online': online, 'database': db_status,
            'redis': redis_status, 'realtime': redis_status,
            'mqtt': bool(_mqtt_client), 'mail_mode': mail_mode,
            'version': config.APP_VERSION,
            'ml_models': len(ml_engine.list_models()),
            'payment_status': payment_processor.gateway_status(),
            'storage': {'uploads_writable': os.access(config.UPLOAD_FOLDER, os.W_OK),
                        'backup_dir_configured': bool(os.environ.get('SYNAPSEPM_BACKUP_DIR'))},
            'checked_at': datetime.now(timezone.utc).isoformat(),
        }), 200

    @adm_bp.route('/system/shutdown', methods=['POST'])
    @admin_required
    def adm_system_shutdown():
        try:
            if g.user.role != 'super_admin':
                return jerr('Only a super administrator can disable the entire software.', 403)
            data = request.get_json(silent=True) or {}
            password = data.get('password')
            if not password:
                return jerr('Password required for reauthentication.', 400)
            if not g.user.check_password(password):
                return jerr('Invalid password.', 401)
            _set_system_online(False, actor_id=g.user.id)
            log_audit('admin_shutdown', 'system', None, {'online': False})
            broadcast_both('system_status_changed', {'online': False})
            return jsonify({'success': True, 'online': False,
                            'message': 'System access disabled.'}), 200
        except Exception:
            db.session.rollback()
            logger.exception('adm_system_shutdown failed')
            return jerr('System shutdown could not be persisted. Check database connectivity.', 503)

    @adm_bp.route('/system/start', methods=['POST'])
    @admin_required
    def adm_system_start():
        try:
            if g.user.role != 'super_admin':
                return jerr('Only a super administrator can restore the entire software.', 403)
            data = request.get_json(silent=True) or {}
            password = data.get('password')
            if not password:
                return jerr('Password required to restore access.', 400)
            if not g.user.check_password(password):
                return jerr('Invalid password.', 401)
            _set_system_online(True, actor_id=g.user.id)
            log_audit('admin_start', 'system', None, {'online': True})
            broadcast_both('system_status_changed', {'online': True})
            return jsonify({'success': True, 'online': True,
                            'message': 'System access restored.'}), 200
        except Exception:
            db.session.rollback()
            logger.exception('adm_system_start failed')
            return jerr('System restore could not be persisted. Check database connectivity.', 503)

    @adm_bp.route('/settings', methods=['GET', 'PUT'])
    @admin_required
    def adm_settings():
        try:
            if request.method == 'GET':
                s = g.organization.settings or {}
                return jsonify({'success': True, 'settings': s}), 200
            data = request.get_json() or {}
            current = g.organization.settings or {}
            current.update(data)
            g.organization.settings = current
            db.session.commit()
            broadcast_both('settings_updated', {'settings': current},
                           org_id=g.organization.id)
            return jsonify({'success': True, 'settings': current}), 200
        except Exception as e:
            db.session.rollback()
            return jerr(str(e), 500)

    @adm_bp.route('/thresholds', methods=['GET', 'PUT'])
    @admin_required
    def adm_thresholds():
        try:
            if request.method == 'GET':
                s = (g.organization.settings or {}).get('thresholds', {})
                return jsonify({'success': True, 'thresholds': s}), 200
            data = request.get_json() or {}
            current = g.organization.settings or {}
            current['thresholds'] = {
                'temp_warning': data.get('temp_warning', 75),
                'temp_critical': data.get('temp_critical', 85),
                'vibration_warning': data.get('vibration_warning', 3.5),
            }
            g.organization.settings = current
            db.session.commit()
            broadcast_both('settings_updated', {'settings': current},
                           org_id=g.organization.id)
            return jsonify({'success': True, 'thresholds': current['thresholds']}), 200
        except Exception as e:
            db.session.rollback()
            return jerr(str(e), 500)

    @adm_bp.route('/avatar', methods=['POST'])
    @admin_required
    def adm_avatar_upload():
        try:
            if 'avatar' not in request.files:
                return jerr('No file.', 400)
            file = request.files['avatar']
            if not file.filename:
                return jerr('Empty filename.', 400)
            ext = Path(file.filename).suffix.lower()
            if ext not in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                return jerr('Invalid format.', 400)
            if not validate_image_upload(file):
                return jerr('Invalid image.', 400)
            d = os.path.join(config.UPLOAD_FOLDER, 'avatars')
            os.makedirs(d, exist_ok=True)
            fn = f"admin_{uuid.uuid4().hex}{ext}"
            fp = os.path.join(d, fn)
            file.save(fp)
            avatar_url = f"/uploads/avatars/{fn}"
            g.user.avatar_url = avatar_url
            db.session.commit()
            broadcast_both('user_updated', {'user': g.user.to_dict()})
            return jsonify({
                'success': True,
                'avatar_url': avatar_url,
                'user': g.user.to_dict(),
            }), 200
        except Exception as e:
            db.session.rollback()
            logger.exception('adm_avatar_upload failed')
            return jerr(str(e), 500)

    @adm_bp.route('/enterprise-requests', methods=['GET'])
    @admin_required
    def adm_enterprise_list():
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 100, type=int)
            status = request.args.get('status')
            q = EnterpriseRequest.query.order_by(EnterpriseRequest.created_at.desc())
            if status:
                q = q.filter_by(status=status)
            result = paginate(q, page, per_page)
            return jsonify({
                'success': True,
                'requests': result['items'],
                'items': result['items'],
                'total': result['total'],
            }), 200
        except Exception as e:
            logger.exception('adm_enterprise_list failed')
            return jsonify({'success': False, 'error': str(e),
                            'requests': [], 'items': [], 'total': 0}), 500

    @adm_bp.route('/enterprise-requests/<rid>', methods=['PUT', 'POST'])
    @admin_required
    def adm_enterprise_update(rid):
        try:
            req = EnterpriseRequest.query.filter_by(uuid=rid).first()
            if not req:
                req = db.session.get(EnterpriseRequest, rid)
            if not req or (g.user.role not in ('super_admin', 'admin') and str(req.organization_id or '') != str(g.organization.id)):
                return jerr('Request not found.', 404)
            data = request.get_json() or {}
            valid = {'pending', 'contacted', 'negotiating', 'approved',
                     'rejected', 'won', 'lost', 'archived'}
            if 'status' in data:
                if data['status'] not in valid:
                    return jerr('Invalid status.', 400)
                req.status = data['status']
                if data['status'] == 'contacted':
                    req.contacted_at = datetime.now(timezone.utc)
            if 'admin_notes' in data:
                req.admin_notes = data['admin_notes']

            access_granted = False
            if req.status in ('approved', 'won'):
                user = db.session.get(User, req.user_id) if req.user_id else None
                if not user:
                    user = User.query.filter(func.lower(User.email) == (req.email or '').lower()).first()
                org_id = req.organization_id or (user.organization_id if user else None)
                org = db.session.get(Organization, org_id) if org_id else None
                if user and org:
                    plan_cfg = config.PLANS.get('enterprise', {})
                    user.plan = 'enterprise'
                    user.is_active = True
                    user.status = 'active'
                    org.plan = 'ENTERPRISE'
                    org.subscription_status = 'active'
                    org.max_machines = plan_cfg.get('max_machines', 999)
                    org.max_users = plan_cfg.get('max_users', 999)
                    org.max_api_calls = plan_cfg.get('max_api_calls', 999999)
                    req.user_id = user.id
                    req.organization_id = org.id
                    access_granted = True
                    broadcast_both('user_updated', {'user': user.to_dict()}, org_id=org.id)
                    broadcast_both('billing_updated', {'organization': org.to_dict()}, org_id=org.id)
                elif req.organization_id:
                    org = db.session.get(Organization, req.organization_id)
                    if org:
                        plan_cfg = config.PLANS.get('enterprise', {})
                        org.plan = 'ENTERPRISE'
                        org.subscription_status = 'active'
                        org.max_machines = plan_cfg.get('max_machines', 999)
                        org.max_users = plan_cfg.get('max_users', 999)
                        org.max_api_calls = plan_cfg.get('max_api_calls', 999999)
                        access_granted = True
                if not access_granted:
                    db.session.rollback()
                    return jerr('Request approved, but no matching account/organization exists. Link or create the account before granting access.', 409)
            db.session.commit()
            log_audit('admin_update_enterprise_request', 'enterprise_request', req.id, {
                'status': req.status, 'access_granted': access_granted
            })
            broadcast_both('enterprise_request_updated', {
                'request': req.to_dict(), 'access_granted': access_granted
            }, org_id=req.organization_id)
            return jsonify({'success': True, 'request': req.to_dict(),
                            'access_granted': access_granted}), 200
        except Exception as e:
            db.session.rollback()
            return jerr(str(e), 500)

    @adm_bp.route('/notifications', methods=['POST'])
    @admin_required
    def adm_notify():
        data = request.get_json() or {}
        try:
            for u in User.query.filter_by(role='super_admin', is_active=True).all():
                db.session.add(Notification(
                    user_id=u.id, organization_id=u.organization_id,
                    title=data.get('title') or 'Admin notification',
                    message=data.get('message') or '',
                    type=data.get('type') or 'admin',
                ))
            db.session.commit()
            broadcast_both('notification', {
                'title': data.get('title'),
                'message': data.get('message'),
            })
        except Exception:
            db.session.rollback()
            logger.exception('Admin notify failed')
        return jsonify({'success': True}), 200

    @adm_bp.route('/organizations', methods=['GET'])
    @admin_required
    def adm_orgs():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        q = Organization.query.order_by(Organization.created_at.desc())
        return jsonify({'success': True, **paginate(q, page, per_page)}), 200

    @adm_bp.route('/audit-logs', methods=['GET'])
    @admin_required
    def adm_audit():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        q = AuditLog.query.order_by(AuditLog.created_at.desc())
        action = request.args.get('action')
        if action:
            q = q.filter(AuditLog.action == action)
        return jsonify({'success': True, **paginate(q, page, per_page)}), 200

    @adm_bp.route('/models/reload', methods=['POST'])
    @admin_required
    def adm_reload():
        try:
            snap = model_registry.reload()
            return jsonify({'success': True, 'registry': snap}), 200
        except Exception:
            logger.exception('Reload failed')
            return jerr('Model registry reload failed.', 503)

    @adm_bp.route('/models/registry', methods=['GET'])
    @admin_required
    def adm_model_registry():
        return jsonify(json_safe({'success': True, 'registry': model_registry.snapshot()})), 200

    @adm_bp.route('/models/validate', methods=['POST'])
    @admin_required
    def adm_model_validate():
        try:
            results = model_registry.validate_all()
            failures = [r for r in results if r['status'] != 'valid']
            return jsonify({
                'success': len(failures) == 0,
                'validated': len(results) - len(failures),
                'failed': len(failures),
                'results': results
            }), 200 if not failures else 207
        except Exception:
            logger.exception('Model validation failed')
            return jerr('Model validation failed.', 503)

    @adm_bp.route('/models', methods=['GET'])
    @admin_required
    def adm_models():
        ms = []
        for mid, info in ml_engine.models.items():
            ms.append({
                'id': mid, 'framework': info.get('framework'),
                'model_type': info.get('model_type'), 'version': info.get('version'),
                'loaded': info.get('loaded', False), 'production': mid in ml_engine.production_ids,
                'family': info.get('family'), 'validated': info.get('validated'),
                'quarantined': info.get('quarantined'), 'checksum_status': info.get('checksum_status'),
                'metrics': info.get('metrics', {}), 'dataset': info.get('dataset'),
                'features': info.get('features', []), 'feature_count': info.get('feature_count'),
                'sequence_length': info.get('sequence_length')
            })
        return jsonify({'success': True, 'models': ms, 'count': len(ms),
                        'families': len(ml_engine.by_family)}), 200

    @adm_bp.route('/models/health', methods=['GET'])
    @admin_required
    def adm_models_health():
        quarantined = sum(1 for item in ml_engine.models.values() if item.get('quarantined'))
        ready_for_predictions = bool(ml_engine.production_ids) if config.MODEL_REQUIRE_VALIDATED else bool(ml_engine.models)
        return jsonify({
            'success': True,
            'registered_models': len(ml_engine.models),
            'registered_families': len(ml_engine.all_by_family),
            'production_candidates': len(ml_engine.production_ids),
            'loaded_models': len(ml_engine._model_cache),
            'quarantined_models': quarantined,
            'cache_size': config.MODEL_CACHE_SIZE,
            'cache_hits': ml_engine.cache_hits,
            'cache_misses': ml_engine.cache_misses,
            'ready_for_predictions': ready_for_predictions,
            'diagnostic_fallback_enabled': False,
        }), 200

    @adm_bp.route('/cleanup/run', methods=['POST'])
    @admin_required
    def adm_cleanup():
        try:
            now = datetime.now(timezone.utc)
            a = AuditLog.query.filter(
                AuditLog.created_at < now - timedelta(days=config.AUDIT_RETENTION_DAYS)
            ).delete(synchronize_session=False)
            d = Download.query.filter(
                Download.created_at < now - timedelta(days=config.DOWNLOAD_RETENTION_DAYS)
            ).delete(synchronize_session=False)
            UserSession.query.filter(UserSession.expires_at < now)\
                .delete(synchronize_session=False)
            insp = inspect(db.engine)
            if 'webhook_events' in insp.get_table_names():
                WebhookEvent.query.filter(
                    WebhookEvent.received_at < now - timedelta(days=30)
                ).delete(synchronize_session=False)
            db.session.commit()
            return jsonify({'success': True, 'audit_deleted': a,
                            'downloads_deleted': d}), 200
        except Exception:
            db.session.rollback()
            logger.exception('Manual cleanup failed')
            return jerr('Cleanup failed.', 500)

    app.register_blueprint(adm_bp)

    # ============================================================
    # DOWNLOADS BLUEPRINT
    # ============================================================

    dl_bp = Blueprint('downloads', __name__, url_prefix='/api/v1/downloads')

    def _safe_release(folder, filename):
        root = Path(folder).expanduser().resolve()
        candidate = Path(filename)
        p = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if p != root and not str(p).startswith(str(root) + os.sep):
            raise ValueError('Invalid release path')
        return p

    def _find_release_file(kind, platform, configured_name):
        """Resolve a real release artifact across all supported build/deploy layouts.

        Never returns source files or placeholders. Explicit environment paths win,
        then configured release folders, build output folders, and bounded recursive
        exact-name lookup are checked.
        """
        app_root = Path(os.path.dirname(os.path.abspath(__file__))).resolve()
        if kind == 'desktop':
            aliases = {
                'windows': ['SynapsePM-Setup-Windows.exe', 'SynapsePM-Setup.exe', 'SynapsePM.exe', 'SynapsePM-Windows.msi', 'SynapsePM.zip'],
                'macos': ['SynapsePM-macOS.dmg', 'SynapsePM.dmg', 'SynapsePM-macOS.pkg', 'SynapsePM-macOS.zip'],
                'linux': ['SynapsePM-Linux.AppImage', 'SynapsePM.AppImage', 'SynapsePM-Linux.deb', 'SynapsePM-Linux.tar.gz'],
            }.get(platform, [])
            roots = [Path(config.DESKTOP_RELEASES_FOLDER).expanduser(),
                     app_root / 'releases' / 'desktop' / platform,
                     app_root / 'releases' / 'desktop', app_root / 'dist',
                     app_root / 'desktop' / 'dist', app_root / 'installer' / 'out',
                     app_root / 'installer', app_root / 'build' / 'SynapsePM']
        else:
            aliases = {
                'android': ['SynapsePM-Android.apk', 'SynapsePM.apk', 'app-release.apk'],
                'ios': ['SynapsePM-iOS.ipa', 'SynapsePM.ipa', 'SynapsePM-iOS.zip'],
            }.get(platform, [])
            roots = [Path(config.MOBILE_RELEASES_FOLDER).expanduser(),
                     app_root / 'releases' / 'mobile' / platform,
                     app_root / 'releases' / 'mobile',
                     app_root / 'mobile' / 'android' / 'app' / 'build' / 'outputs' / 'apk' / 'release',
                     app_root / 'mobile' / 'android' / 'app' / 'build' / 'outputs' / 'apk' / 'debug',
                     app_root / 'mobile' / 'ios' / 'build', app_root / 'mobile']
        names = []
        for value in [configured_name, *aliases]:
            if value and str(value) not in names:
                names.append(str(value))
        env_key = f'SYNAPSEPM_{kind.upper()}_{platform.upper()}_RELEASE_PATH'
        explicit = os.environ.get(env_key, '').strip()
        if explicit:
            ep = Path(explicit).expanduser().resolve()
            if ep.is_file():
                return ep
            if ep.is_dir():
                roots.insert(0, ep)
        lower_names = {n.lower() for n in names}
        seen = set()
        for root_value in roots:
            try:
                root = Path(root_value).expanduser().resolve()
                if root in seen or not root.is_dir():
                    continue
                seen.add(root)
                for name in names:
                    candidate = root / name
                    if candidate.is_file():
                        return candidate
                for entry in root.iterdir():
                    if entry.is_file() and entry.name.lower() in lower_names:
                        return entry.resolve()
                # One bounded recursive pass for versioned release folders.
                for entry in root.rglob('*'):
                    if not entry.is_file() or entry.name.lower() not in lower_names:
                        continue
                    parts = {p.lower() for p in entry.parts}
                    if parts & {'venv', 'node_modules', '.git', '__pycache__'}:
                        continue
                    return entry.resolve()
            except (OSError, PermissionError):
                continue
        return None

    def _sha256_file(p):
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        return h.hexdigest()

    @dl_bp.route('', methods=['GET'])
    @login_required
    def dl_list():
        configured = {
            'desktop': {'windows': config.DESKTOP_WINDOWS_FILE,
                        'macos': config.DESKTOP_MACOS_FILE,
                        'linux': config.DESKTOP_LINUX_FILE},
            'mobile': {'android': config.MOBILE_ANDROID_FILE,
                       'ios': config.MOBILE_IOS_FILE},
        }
        manifest = {'desktop': {}, 'mobile': {}}
        for kind, platforms in configured.items():
            for platform, filename in platforms.items():
                try:
                    artifact = _find_release_file(kind, platform, filename)
                except Exception:
                    artifact = None
                manifest[kind][platform] = {
                    'url': f'/api/v1/downloads/{kind}/{platform}',
                    'available': bool(artifact and artifact.is_file()),
                    'filename': artifact.name if artifact else filename,
                    'size_bytes': (artifact.stat().st_size if artifact and artifact.is_file() else 0),
                    'version': config.DESKTOP_APP_VERSION if kind == 'desktop' else config.MOBILE_APP_VERSION,
                }
        urls = {
            'desktop': {
                'windows': '/api/v1/downloads/desktop/windows',
                'macos': '/api/v1/downloads/desktop/macos',
                'linux': '/api/v1/downloads/desktop/linux',
            },
            'mobile': {
                'android': '/api/v1/downloads/mobile/android',
                'ios': '/api/v1/downloads/mobile/ios',
            },
        }
        return jsonify({'success': True, 'downloads': urls, 'availability': manifest}), 200

    @dl_bp.route('/desktop/<platform>', methods=['GET'])
    @login_required
    def dl_desktop(platform):
        names = {'windows': config.DESKTOP_WINDOWS_FILE,
                 'macos': config.DESKTOP_MACOS_FILE,
                 'linux': config.DESKTOP_LINUX_FILE}
        if platform not in names:
            return jerr('Invalid platform.', 400)
        try:
            p = _find_release_file('desktop', platform, names[platform])
        except ValueError:
            return jerr('Invalid release configuration.', 400)
        if not p:
            return jerr('Release artifact not found on this server.', 503,
                        platform=platform, expected_file=names[platform],
                        setup_hint='Place the built installer in DESKTOP_RELEASES_FOLDER or set SYNAPSEPM_DESKTOP_' + platform.upper() + '_RELEASE_PATH to its absolute path.')
        checksum = _sha256_file(p)
        d = Download(
            organization_id=g.organization.id, user_id=g.user.id,
            name=f'SynapsePM Desktop ({platform})', type='desktop',
            version=config.DESKTOP_APP_VERSION, file_path=str(p),
            file_size=p.stat().st_size, checksum=checksum,
            platform=platform, ip_address=request.remote_addr,
            metadata_json={'user_agent': request.headers.get('User-Agent', '')[:300]}
        )
        db.session.add(d)
        db.session.commit()
        try:
            broadcast_both('download_created', {
                'download': {
                    'platform': platform,
                    'user_name': g.user.display_name or g.user.email,
                    'version': config.DESKTOP_APP_VERSION,
                }
            }, org_id=g.organization.id)
        except Exception:
            pass
        resp = send_file(
            p, as_attachment=True, download_name=p.name,
            conditional=True, max_age=0,
        )
        resp.headers['Accept-Ranges'] = 'bytes'
        resp.headers['Cache-Control'] = 'private, no-cache, no-store'
        resp.headers['X-SynapsePM-Release-Version'] = (
            config.DESKTOP_APP_VERSION if platform in {'windows', 'macos', 'linux'}
            else config.MOBILE_APP_VERSION
        )
        resp.headers['X-SynapsePM-Release-SHA256'] = checksum
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        return resp

    @dl_bp.route('/mobile/<platform>', methods=['GET'])
    @login_required
    def dl_mobile(platform):
        names = {'android': config.MOBILE_ANDROID_FILE,
                 'ios': config.MOBILE_IOS_FILE}
        if platform not in names:
            return jerr('Invalid platform.', 400)
        try:
            p = _find_release_file('mobile', platform, names[platform])
        except ValueError:
            return jerr('Invalid release configuration.', 400)
        if not p:
            return jerr('Release artifact not found on this server.', 503,
                        platform=platform, expected_file=names[platform],
                        setup_hint='Place the built package in MOBILE_RELEASES_FOLDER or set SYNAPSEPM_MOBILE_' + platform.upper() + '_RELEASE_PATH to its absolute path.')
        checksum = _sha256_file(p)
        d = Download(
            organization_id=g.organization.id, user_id=g.user.id,
            name=f'SynapsePM Mobile ({platform})', type='mobile',
            version=config.MOBILE_APP_VERSION, file_path=str(p),
            file_size=p.stat().st_size, checksum=checksum,
            platform=platform, ip_address=request.remote_addr,
            metadata_json={'user_agent': request.headers.get('User-Agent', '')[:300]}
        )
        db.session.add(d)
        db.session.commit()
        try:
            broadcast_both('download_created', {
                'download': {
                    'platform': platform,
                    'user_name': g.user.display_name or g.user.email,
                    'version': config.MOBILE_APP_VERSION,
                }
            }, org_id=g.organization.id)
        except Exception:
            pass
        resp = send_file(
            p, as_attachment=True, download_name=p.name,
            conditional=True, max_age=0,
        )
        resp.headers['Accept-Ranges'] = 'bytes'
        resp.headers['Cache-Control'] = 'private, no-cache, no-store'
        resp.headers['X-SynapsePM-Release-Version'] = (
            config.DESKTOP_APP_VERSION if platform in {'windows', 'macos', 'linux'}
            else config.MOBILE_APP_VERSION
        )
        resp.headers['X-SynapsePM-Release-SHA256'] = checksum
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        return resp

    @dl_bp.route('/track-install', methods=['POST'])
    @login_required
    def track_pwa_install():
        """
        Called by the PWA frontend when the app is installed or first launched
        in standalone mode.

        Records a Download row with type='app_install' so the admin dashboard's
        existing Install Software section shows it alongside native downloads.
        """
        data = request.get_json(silent=True) or {}
        platform = (data.get('platform') or 'web').lower()[:50]
        user_agent = (request.headers.get('User-Agent') or '')[:300]
        display_mode = str(data.get('display_mode') or 'standalone')[:50]
        install_source = str(data.get('source') or 'unknown')[:50]

        try:
            d = Download(
                organization_id=g.organization.id,
                user_id=g.user.id,
                name=f'SynapsePM PWA ({platform})',
                type='app_install',
                version=config.APP_VERSION,
                file_path='',
                file_size=0,
                checksum=None,
                platform=platform,
                ip_address=request.remote_addr,
                metadata_json={
                    'user_agent': user_agent,
                    'display_mode': display_mode,
                    'install_source': install_source,
                    'is_pwa': True,
                }
            )
            db.session.add(d)
            db.session.commit()

            try:
                broadcast_both('download_created', {
                    'download': {
                        'platform': platform,
                        'type': 'app_install',
                        'user_name': g.user.display_name or g.user.email,
                        'version': config.APP_VERSION,
                    }
                }, org_id=g.organization.id)
            except Exception:
                pass

            return jsonify({'success': True, 'install_id': d.uuid}), 201
        except Exception:
            db.session.rollback()
            logger.exception('PWA install tracking failed')
            return jerr('Could not record install.', 500)

    app.register_blueprint(dl_bp)

    # ============================================================
    # WEBSOCKET — with session revocation enforcement
    # ============================================================

    if FLASK_SOCK_AVAILABLE:
        sock = Sock(app)

        @sock.route('/ws')
        def ws_handler(ws):
            user = None
            token = request.args.get('token')
            if not token:
                auth = request.headers.get('Authorization', '')
                if auth.startswith('Bearer '):
                    token = auth.split(' ', 1)[1].strip()
            if not token:
                try:
                    ws.send(json.dumps({'type': 'auth_error', 'message': 'No token'}))
                except Exception:
                    pass
                return
            try:
                payload = jwt.decode(
                    token, config.JWT_SECRET_KEY,
                    algorithms=[config.JWT_ALGORITHM],
                    options={'verify_iss': False, 'verify_aud': False}
                )
                # FIX: enforce session revocation on WS
                sid = payload.get('sid')
                jti = payload.get('jti')
                if jti and jwt_blacklist.check(jti):
                    try:
                        ws.send(json.dumps({'type': 'auth_error', 'message': 'Token revoked'}))
                    except Exception:
                        pass
                    try:
                        ws.close(code=1008)
                    except Exception:
                        pass
                    return
                revoked_raw = redis_client.get(f'user_revoked:{payload.get("user_id")}') if redis_client else None
                if revoked_raw:
                    try:
                        revoked_at = int(revoked_raw)
                    except (TypeError, ValueError):
                        revoked_at = 0
                    if revoked_at and int(payload.get('iat') or 0) < revoked_at:
                        try: ws.close(code=1008)
                        except Exception: pass
                        return

                if sid and not session_manager.check_session(sid):
                    try:
                        ws.send(json.dumps({'type': 'auth_error', 'message': 'Session revoked'}))
                    except Exception:
                        pass
                    try:
                        ws.close(code=1008)
                    except Exception:
                        pass
                    return

                user = db.session.get(User, payload.get('user_id'))
                if not user or not user.is_active:
                    try:
                        ws.send(json.dumps({'type': 'auth_error'}))
                    except Exception:
                        pass
                    try:
                        ws.close(code=1008)
                    except Exception:
                        pass
                    return
                if not _get_system_online() and user.role not in ('super_admin', 'admin', 'org_admin'):
                    try:
                        ws.send(json.dumps({'type': 'auth_error', 'message': 'System unavailable'}))
                    except Exception:
                        pass
                    try:
                        ws.close(code=1008)
                    except Exception:
                        pass
                    return
                try:
                    ws.send(json.dumps({
                        'type': 'auth_success',
                        'user': user.email,
                        'realtime': bool(redis_client) or bool(FLASK_SOCK_AVAILABLE),
                        'server_time': datetime.now(timezone.utc).isoformat(),
                    }))
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f'User WS auth failed: {e}')
                try:
                    ws.send(json.dumps({'type': 'auth_error'}))
                except Exception:
                    pass
                try:
                    ws.close(code=1008)
                except Exception:
                    pass
                return

            pubsub = None
            local_queue = None
            if redis_client:
                try:
                    pubsub = redis_client.pubsub()
                    pubsub.subscribe('user_events', f'user_events:{user.organization_id}')
                except Exception:
                    pubsub = None
            if pubsub is None:
                local_queue = _local_subscribe('user_events')

            try:
                last_ping = time.time()
                while True:
                    if time.time() - last_ping > 20:
                        try:
                            ws.send(json.dumps({'type': 'ping'}))
                            last_ping = time.time()
                        except Exception:
                            break

                    if pubsub:
                        try:
                            msg = pubsub.get_message(
                                ignore_subscribe_messages=True, timeout=0.05
                            )
                            if msg and msg.get('type') == 'message':
                                try:
                                    data = json.loads(msg['data'])
                                    ws.send(json.dumps(data))
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    if local_queue is not None:
                        try:
                            while True:
                                data_str = local_queue.get_nowait()
                                try:
                                    ws.send(data_str)
                                except Exception:
                                    break
                        except _queue.Empty:
                            pass
                        except Exception:
                            pass

                    try:
                        raw = ws.receive(timeout=0.05)
                        if raw:
                            try:
                                data = json.loads(raw)
                                if data.get('type') == 'ping':
                                    ws.send(json.dumps({'type': 'pong'}))
                            except Exception:
                                pass
                    except Exception:
                        pass

                    time.sleep(0.05)
            except Exception as e:
                logger.debug(f'User WS closed: {e}')
            finally:
                if pubsub:
                    try:
                        pubsub.close()
                    except Exception:
                        pass
                if local_queue is not None:
                    _local_unsubscribe('user_events', local_queue)

        @sock.route('/ws/admin')
        def ws_admin_handler(ws):
            user = None
            token = request.args.get('token')
            if not token:
                auth = request.headers.get('Authorization', '')
                if auth.startswith('Bearer '):
                    token = auth.split(' ', 1)[1].strip()
            if not token:
                try:
                    ws.send(json.dumps({'type': 'auth_error', 'message': 'No token'}))
                except Exception:
                    pass
                return
            try:
                payload = jwt.decode(
                    token, config.JWT_SECRET_KEY,
                    algorithms=[config.JWT_ALGORITHM],
                    options={'verify_iss': False, 'verify_aud': False}
                )
                sid = payload.get('sid')
                jti = payload.get('jti')
                if jti and jwt_blacklist.check(jti):
                    try:
                        ws.send(json.dumps({'type': 'auth_error', 'message': 'Token revoked'}))
                    except Exception:
                        pass
                    try:
                        ws.close(code=1008)
                    except Exception:
                        pass
                    return
                revoked_raw = redis_client.get(f'user_revoked:{payload.get("user_id")}') if redis_client else None
                if revoked_raw:
                    try:
                        revoked_at = int(revoked_raw)
                    except (TypeError, ValueError):
                        revoked_at = 0
                    if revoked_at and int(payload.get('iat') or 0) < revoked_at:
                        try: ws.close(code=1008)
                        except Exception: pass
                        return

                if sid and not session_manager.check_session(sid):
                    try:
                        ws.send(json.dumps({'type': 'auth_error', 'message': 'Session revoked'}))
                    except Exception:
                        pass
                    try:
                        ws.close(code=1008)
                    except Exception:
                        pass
                    return

                user = db.session.get(User, payload.get('user_id'))
                if not user or user.role not in ('super_admin', 'org_admin', 'admin'):
                    try:
                        ws.send(json.dumps({'type': 'auth_error', 'message': 'Not admin'}))
                    except Exception:
                        pass
                    try:
                        ws.close(code=1008)
                    except Exception:
                        pass
                    return
                try:
                    ws.send(json.dumps({
                        'type': 'auth_success',
                        'user': user.email,
                        'realtime': bool(redis_client) or bool(FLASK_SOCK_AVAILABLE),
                        'server_time': datetime.now(timezone.utc).isoformat(),
                    }))
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f'Admin WS auth failed: {e}')
                try:
                    ws.send(json.dumps({'type': 'auth_error', 'message': str(e)}))
                except Exception:
                    pass
                try:
                    ws.close(code=1008)
                except Exception:
                    pass
                return

            pubsub = None
            local_queue = None
            if redis_client:
                try:
                    pubsub = redis_client.pubsub()
                    pubsub.subscribe('admin_events')
                except Exception:
                    pubsub = None
            if pubsub is None:
                local_queue = _local_subscribe('admin_events')

            try:
                last_ping = time.time()
                while True:
                    if time.time() - last_ping > 20:
                        try:
                            ws.send(json.dumps({'type': 'ping'}))
                            last_ping = time.time()
                        except Exception:
                            break

                    if pubsub:
                        try:
                            msg = pubsub.get_message(
                                ignore_subscribe_messages=True, timeout=0.05
                            )
                            if msg and msg.get('type') == 'message':
                                try:
                                    data = json.loads(msg['data'])
                                    ws.send(json.dumps(data))
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    if local_queue is not None:
                        try:
                            while True:
                                data_str = local_queue.get_nowait()
                                try:
                                    ws.send(data_str)
                                except Exception:
                                    break
                        except _queue.Empty:
                            pass
                        except Exception:
                            pass

                    try:
                        raw = ws.receive(timeout=0.05)
                        if raw:
                            try:
                                data = json.loads(raw)
                                if data.get('type') == 'ping':
                                    ws.send(json.dumps({'type': 'pong'}))
                            except Exception:
                                pass
                    except Exception:
                        pass

                    time.sleep(0.05)
            except Exception as e:
                logger.debug(f'Admin WS closed: {e}')
            finally:
                if pubsub:
                    try:
                        pubsub.close()
                    except Exception:
                        pass
                if local_queue is not None:
                    _local_unsubscribe('admin_events', local_queue)
    else:
        @app.route('/ws')
        def ws_fallback():
            return jsonify({
                'error': 'WebSocket not supported',
                'hint': 'pip install flask-sock'
            }), 426

        @app.route('/ws/admin')
        def ws_admin_fallback():
            return jsonify({
                'error': 'WebSocket not supported',
                'hint': 'pip install flask-sock'
            }), 426

    def _shutdown(signum, frame):
        # IMPORTANT: the old handler only set an event, so Flask kept running
        # and Windows appeared stuck on "Shutting down...".  Perform cleanup
        # once and then actually terminate the development process.
        if getattr(_cleanup_stop, 'is_set', lambda: False)():
            return
        logger.info('Shutting down...')
        _cleanup_stop.set()
        try:
            if _mqtt_client:
                _mqtt_client.loop_stop()
                _mqtt_client.disconnect()
        except Exception:
            logger.exception('MQTT shutdown failed')
        try:
            if redis_client:
                redis_client.close()
        except Exception:
            pass
        try:
            db.session.remove()
            db.engine.dispose()
        except Exception:
            pass
        logger.info('Shutdown complete.')
        if signum == getattr(signal, 'SIGINT', object()):
            raise KeyboardInterrupt
        # SIGTERM has no Flask exception path; terminate after cleanup.
        os._exit(0)

    try:
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
    except Exception:
        pass

    return app


# ============================================================
# CREATE APP + RUN
# ============================================================

app = create_app()


if __name__ == '__main__':
    print(f"\n{'='*70}")
    print(f" 🚀 {config.APP_NAME} v{config.APP_VERSION} - READY")
    print(f"{'='*70}")
    print(f" Environment: {config.ENV}")
    print(f" Server: http://{config.HOST}:{config.PORT}")
    print(f" Admin: {config.ADMIN_EMAIL}")
    print(f" Admin force-reset: {'ON' if config.ADMIN_FORCE_RESET else 'OFF'}")
    print(f" ML Models: {len(ml_engine.list_models())} production candidates / {len(ml_engine.models)} registered artifacts / {len(ml_engine.all_by_family)} families")
    print(f" ML Root: {config.ML_MODEL_PATH}")
    print(f" ML Release: {config.MODEL_RELEASE_ZIP}")
    print(' ML Diagnostic Fallback: REMOVED (real trained models only)')
    if config.IS_PRODUCTION:
        rr = production_readiness_report()
        print(f" Production readiness: {'READY' if rr['ready'] else 'BLOCKED'} ({len([x for x in rr['checks'] if x['ok']])}/{len(rr['checks'])} checks passed)")
        if not rr['ready']:
            for c in rr['checks']:
                if not c['ok']:
                    print(f"   ❌ {c['name']}: {c['detail']}")
            if config.PRODUCTION_READINESS_ENFORCE:
                raise SystemExit('Production readiness gate failed. Fix the checks above before launch.')
    print(f" Payment Gateways: {', '.join(payment_processor.get_gateways()) or 'none'}")
    if 'paddle' not in payment_processor.get_gateways():
        print("   ⚠️  Paddle is NOT configured. Fix .env:")
        for s in payment_processor.gateway_status():
            if s.get('name') == 'paddle' and not s.get('enabled'):
                print(f"      → {s.get('reason')}")
    print(f" Email: {'LIVE' if not config.MAIL_SUPPRESS_SEND else 'SUPPRESSED (dev)'}")
    print(f" Real-time: {'ON' if redis_client else 'OFF (polling fallback)'}")
    print(f" MQTT: {'ON' if _mqtt_client else 'OFF'}")
    print(f"{'='*70}\n")
    if config.IS_PRODUCTION:
        raise SystemExit('Production: use Gunicorn. app.run() disabled.')
    app.run(host=config.HOST, port=config.PORT,
            debug=config.DEBUG, threaded=True, use_reloader=False)  
