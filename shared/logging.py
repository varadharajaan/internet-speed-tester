"""
Centralized logging with JSON format for CloudWatch compatibility.

Provides:
- JSON structured logging (CloudWatch/ELK compatible)
- File rotation for local development
- Lambda environment detection
- log_execution decorator for function timing

Usage:
    from shared import get_logger
    log = get_logger(__name__)
    log.info("Processing data", extra={"count": 42})
"""
import datetime
import json
import logging
import os
import socket
import sys
from functools import wraps
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional

from .config import get_config


# Cache hostname for performance
_HOSTNAME = socket.gethostname()


def is_lambda_environment() -> bool:
    """Check if running in AWS Lambda."""
    return "AWS_LAMBDA_FUNCTION_NAME" in os.environ


class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Output format compatible with CloudWatch Logs Insights and ELK.
    """
    
    def __init__(self, hostname: str = None):
        super().__init__()
        self.hostname = hostname or _HOSTNAME
    
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "function": record.funcName,
            "module": record.module,
            "hostname": self.hostname,
        }
        
        # Add request ID if available (Lambda)
        if hasattr(record, "aws_request_id"):
            entry["requestId"] = record.aws_request_id
        
        # Add extra fields if provided
        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        
        return json.dumps(entry)


class CustomLogger:
    """
    Custom logger with JSON formatting and environment-aware handlers.
    
    - In Lambda: Logs to stdout (captured by CloudWatch)
    - In local dev: Logs to stdout + rotating file
    """
    
    def __init__(
        self,
        name: str = __name__,
        level: Optional[str] = None,
        log_file: Optional[str] = None,
    ):
        config = get_config()
        
        self.logger = logging.getLogger(name)
        
        # Only add handlers if not already configured
        if not self.logger.handlers:
            formatter = JsonFormatter()
            
            # Console handler (CloudWatch captures stdout)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
            
            # File handler (only for local development)
            if not is_lambda_environment():
                log_file = log_file or f"{name.split('.')[-1]}.log"
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=config.log_max_bytes,
                    backupCount=config.log_backup_count,
                    encoding="utf-8",
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
        
        # Set log level
        log_level = level or config.log_level
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.logger.propagate = False
    
    def _log(self, level: int, msg: str, *args, **kwargs):
        """Internal log method with extra fields support."""
        extra = kwargs.pop("extra", None)
        if extra:
            # Store extra fields for JsonFormatter
            kwargs["extra"] = {"extra_fields": extra}
        self.logger.log(level, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, exc_info=True, **kwargs)


# Logger cache to avoid creating duplicates
_loggers: dict = {}


def get_logger(name: str = __name__) -> CustomLogger:
    """
    Get or create a logger instance.
    
    Cached to ensure single logger per module.
    
    Usage:
        from shared import get_logger
        log = get_logger(__name__)
        log.info("Hello world")
    """
    if name not in _loggers:
        _loggers[name] = CustomLogger(name)
    return _loggers[name]


def log_execution(func: Callable) -> Callable:
    """
    Decorator to log function execution time.
    
    Usage:
        @log_execution
        def my_function():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        log = get_logger(func.__module__)
        log.info(f"Executing function: {func.__name__}")
        start = datetime.datetime.now(datetime.UTC)
        try:
            result = func(*args, **kwargs)
            elapsed = (datetime.datetime.now(datetime.UTC) - start).total_seconds()
            log.info(f"Completed successfully: {func.__name__}", extra={"elapsed_seconds": elapsed})
            return result
        except Exception as e:
            elapsed = (datetime.datetime.now(datetime.UTC) - start).total_seconds()
            log.error(f"Failed: {func.__name__} - {e}", extra={"elapsed_seconds": elapsed})
            raise
    return wrapper
