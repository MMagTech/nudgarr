"""
nudgarr/routes/__init__.py

Registers all route blueprints with the Flask app.
Called once from main.py before app.run().
"""

from nudgarr.globals import app
from nudgarr.routes import arr, auth, config, cf_scores, diagnostics, intel, notifications, state, stats, sweep


def register_blueprints() -> None:
    app.register_blueprint(arr.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(cf_scores.bp)
    app.register_blueprint(config.bp)
    app.register_blueprint(diagnostics.bp)
    app.register_blueprint(intel.bp)
    app.register_blueprint(notifications.bp)
    app.register_blueprint(state.bp)
    app.register_blueprint(stats.bp)
    app.register_blueprint(sweep.bp)
