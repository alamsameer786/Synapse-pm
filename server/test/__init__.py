"""
SynapsePM - Routes Package
"""

# Import blueprints
from .user_routes import bp as user_bp

# Export blueprints
__all__ = ['user_bp']