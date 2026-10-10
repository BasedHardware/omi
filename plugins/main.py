import os
from flask import Flask, render_template, request, jsonify
from .iq_rating import bp as iq_rating_bp
from .iq_rating.iq_auth import require_iq_auth

# This would be imported from your main app config
app = Flask(__name__, template_folder='templates')

# Register the blueprint
app.register_blueprint(iq_rating_bp, url_prefix='/iq-rating')

@app.route('/iq')
def iq_rating_landing():
    return render_template('iq.html')

@app.route('/iq/setup-status')
def iq_setup_status():
    return jsonify({"status": "configured" if os.environ.get("IQ_RATING_SECRET") else "not configured"})

# Add the auth decorator to all uid-keyed routes
# This would be applied to the routes in iq_rating.py
# For demonstration, showing how it would be applied:
# @app.route('/iq-rating/iq/preload')
# @require_iq_auth
# def iq_preload():
#     uid = request.args.get('uid')
#     # ... rest of the function
#     pass