"""
Register Flask blueprints for auth, catalog, user, and admin routes.
"""

from routes.admin_routes import admin_bp
from routes.auth_routes import auth_bp
from routes.catalog_routes import catalog_bp
from routes.user_routes import user_bp


def register_routes(app):
    """Attach all route blueprints to the Flask app."""
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)
