"""
Shared utilities for the vd-speed-test project.

This module provides centralized:
- Configuration management
- Logging setup
- AWS client factories
- Constants and thresholds
"""

from .config import Config, get_config
from .logging import get_logger, CustomLogger
from .aws import get_s3_client, get_logs_client, list_hosts
from .constants import (
    AWS_REGION,
    S3_BUCKETS,
    LOG_GROUPS,
    CACHE_TTL,
    AGGREGATION_SCHEDULES,
    ANOMALY_THRESHOLDS,
)

__all__ = [
    # Config
    "Config",
    "get_config",
    # Logging
    "get_logger",
    "CustomLogger",
    # AWS
    "get_s3_client",
    "get_logs_client",
    "list_hosts",
    # Constants
    "AWS_REGION",
    "S3_BUCKETS",
    "LOG_GROUPS",
    "CACHE_TTL",
    "AGGREGATION_SCHEDULES",
    "ANOMALY_THRESHOLDS",
]
