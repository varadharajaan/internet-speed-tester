import json

# Import serverless-wsgi for Lambda compatibility
import serverless_wsgi
from app import app

# --- Shared module imports ----------------------------------------------------
from shared import get_logger
from shared.logging import log_execution

log = get_logger(__name__)

# --- Optional ASGI adapter (commented) ---
# from asgiref.wsgi import WsgiToAsgi
# from mangum import Mangum
# asgi_app = WsgiToAsgi(app)
# handler = Mangum(asgi_app, lifespan="off")

# ======================================
# LAMBDA HANDLER
# ======================================
@log_execution
def lambda_handler(event, context):
    """Lambda handler using serverless-wsgi"""
    log.info(f"Incoming event: {json.dumps(event)[:400]} ...")  # truncate large events
    try:
        response = serverless_wsgi.handle_request(app, event, context)
        log.info("Request handled successfully")
        return response
    except Exception as e:
        log.exception(f"Unhandled exception in lambda_handler: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"}
        }

# --- Optional ASGI version ---
# @log_execution
# def lambda_handler(event, context):
#     """Lambda handler for ASGI apps using Mangum"""
#     log.info(f"Incoming event (ASGI): {json.dumps(event)[:400]} ...")
#     return handler(event, context)

# ======================================
# LOCAL TEST ENTRY POINT
# ======================================
if __name__ == "__main__":
    log.info("Starting Flask app locally...")
    app.run(host="0.0.0.0", port=5000, debug=True)