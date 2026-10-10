"""
SynapsePM - Server Package
Flask application factory
"""

import os
import sys
from pathlib import Path
from flask import Flask
from flask_cors import CORS

# Add project root to path for imports
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Try to import JWT, but make it optional
try:
    from flask_jwt_extended import JWTManager
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("Warning: flask-jwt-extended not installed. JWT features disabled.")

def create_app(config_name=None):
    """
    Application factory function
    """
    app = Flask(__name__)
    
    # Load configuration
    if config_name == 'testing':
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['JWT_SECRET_KEY'] = 'test-jwt-secret-key'
    elif config_name == 'development':
        app.config['DEBUG'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
            'DATABASE_URL',
            'postgresql://postgres:Synapse_pm@localhost:5432/Synapse_pm'
        )
        app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret-key')
    else:
        app.config['DEBUG'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
        app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
    
    # Common configurations
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_TOKEN_LOCATION'] = ['headers']
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 3600
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = 86400
    app.config['JWT_HEADER_NAME'] = 'Authorization'
    app.config['JWT_HEADER_TYPE'] = 'Bearer'
    
    # Initialize extensions
    CORS(app)
    if JWT_AVAILABLE:
        jwt = JWTManager(app)
    
    # Initialize database
    try:
        from services.database import db
        db.init_app(app)
    except ImportError as e:
        print(f"Warning: Could not initialize database: {e}")
    
    # Register blueprints
    try:
        from server.routes.user_routes import bp as user_bp
        app.register_blueprint(user_bp)
        print("✓ User routes registered")
    except ImportError as e:
        print(f"Warning: Could not register user routes: {e}")
    
    # Health check
    @app.route('/health', methods=['GET'])
    def health_check():
        return {'status': 'healthy', 'jwt_available': JWT_AVAILABLE}, 200
    
    return app