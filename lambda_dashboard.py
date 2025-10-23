import os, json, sys, logging, datetime
from logging.handlers import RotatingFileHandler
from functools import wraps

# Import serverless-wsgi or mangum depending on your use case
import serverless_wsgi
from app import app

# --- Optional ASGI adapter (commented) ---
# from asgiref.wsgi import WsgiToAsgi
# from mangum import Mangum
# asgi_app = WsgiToAsgi(app)
# handler = Mangum(asgi_app, lifespan="off")

# ======================================
# CONFIGURATION
# ======================================
LOG_FILE_PATH = os.path.join(os.getcwd(), "lambda_app.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
LOG_BACKUP_COUNT = 5
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
HOSTNAME = os.getenv("HOSTNAME", os.uname().nodename)

# ======================================
# CUSTOM LOGGER
# ======================================
class CustomLogger:
    def __init__(self, name=__name__, level=LOG_LEVEL):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            formatter = self.JsonFormatter()

            # Always log to stdout (CloudWatch)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # Add file rotation handler for local use
            if not self.is_lambda_environment():
                file_handler = RotatingFileHandler(
                    LOG_FILE_PATH,
                    maxBytes=LOG_MAX_BYTES,
                    backupCount=LOG_BACKUP_COUNT,
                    encoding="utf-8"
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

        self.logger.setLevel(level)

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            entry = {
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
                "level": record.levelname,
                "message": record.getMessage(),
                "function": record.funcName,
                "module": record.module,
                "hostname": HOSTNAME,
            }
            if record.exc_info:
                entry["error"] = self.formatException(record.exc_info)
            return json.dumps(entry)

    @staticmethod
    def is_lambda_environment():
        return "AWS_LAMBDA_FUNCTION_NAME" in os.environ

    def info(self, msg, *args): self.logger.info(msg, *args)
    def error(self, msg, *args): self.logger.error(msg, *args)
    def warning(self, msg, *args): self.logger.warning(msg, *args)
    def debug(self, msg, *args): self.logger.debug(msg, *args)
    def exception(self, msg, *args): self.logger.exception(msg, *args)

log = CustomLogger(__name__)

# ======================================
# DECORATOR FOR LOGGING
# ======================================
def log_execution(func):
    """Decorator to log start, success, and failure of Lambda invocations or routes."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        log.info(f"Executing function: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            log.info(f"Completed successfully: {func.__name__}")
            return result
        except Exception as e:
            log.exception(f"Error in {func.__name__}: {e}")
            raise
    return wrapper

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