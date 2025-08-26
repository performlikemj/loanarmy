import os
import sys
from urllib.parse import quote_plus
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from flask import Flask, send_from_directory, jsonify
from src.models.league import db, League, Team, LoanedPlayer, Newsletter, UserSubscription
from src.routes.api import api_bp
import logging
from flask_migrate import Migrate
import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("🚀 Starting Flask application...")

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

logger.info(f"📁 Static folder: {app.static_folder}")
logger.info(f"🔑 Secret key configured: {'Yes' if app.config['SECRET_KEY'] else 'No'}")

# Suppress repetitive MCP notification validation logs but keep the first one
_seen_mcp_validation = False
class _MCPValidationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        global _seen_mcp_validation
        msg = record.getMessage()
        if "Failed to validate notification" in msg:
            if _seen_mcp_validation:
                return False
            _seen_mcp_validation = True
        return True

root_logger = logging.getLogger()
root_logger.addFilter(_MCPValidationFilter())
for name in ("mcp", "agents.mcp", "mcp.shared.session", "mcp.client"):
    logging.getLogger(name).setLevel(logging.WARNING)

app.register_blueprint(api_bp, url_prefix='/api')

# Database setup
# Check for DATABASE_URL first (for testing with SQLite), then fall back to PostgreSQL components
password = quote_plus(os.getenv("DB_PASSWORD"))
database_url = f"postgresql+psycopg://{os.getenv('DB_USER')}:{password}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

if database_url:
    # Use DATABASE_URL directly (e.g., SQLite for testing)
    db_uri = database_url
    logger.info(f"🗄️ Using DATABASE_URL: {db_uri}")
else:
    # Fall back to PostgreSQL components
    pwd     = quote_plus(os.getenv("DB_PASSWORD"))   # encodes @, !, :, / …
    user    = os.getenv("DB_USER")
    host    = os.getenv("DB_HOST")
    port    = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    
    db_uri = f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{db_name}"
    logger.info(f"🗄️ Using PostgreSQL components: {db_uri}")

app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Add debug endpoint
@app.route('/api/debug/database', methods=['GET'])
def debug_database():
    """Debug endpoint to check database state."""
    try:
        stats = {
            'database_path': db_uri,
            'database_exists': os.path.exists(db_uri),
            'tables': {
                'leagues': League.query.count(),
                'teams': Team.query.count(),
                'active_teams': Team.query.filter_by(is_active=True).count(),
                'loans': LoanedPlayer.query.count(),
                'active_loans': LoanedPlayer.query.filter_by(is_active=True).count(),
                'newsletters': Newsletter.query.count(),
                'subscriptions': UserSubscription.query.count()
            }
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': str(e.__traceback__)}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

migrate = Migrate(app, db)

if __name__ == "__main__":
    # Only run when you execute `python src/main.py`,
    # NOT when Flask CLI imports the app.
    with app.app_context():
        logger.info("🔨 Creating database tables...")

        # Optional stats
        total_leagues = League.query.count()
        total_teams   = Team.query.count()
        logger.info(f"📊 DB has {total_teams} teams, {total_leagues} leagues")

    app.run(host="0.0.0.0", port=5001, debug=True)