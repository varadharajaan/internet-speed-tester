"""
Centralized configuration management.

Provides a single source of truth for all configuration values.
Supports: config.json → environment variables → defaults (priority order).

Usage:
    from shared import get_config
    config = get_config()
    bucket = config.s3_bucket
    region = config.aws_region
"""
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional


# Find config.json relative to project root
def _find_config_path() -> Path:
    """Find config.json in project root."""
    # Try multiple locations
    candidates = [
        Path(__file__).parent.parent / "config.json",  # shared/../config.json
        Path.cwd() / "config.json",  # current directory
        Path(__file__).parent / "config.json",  # shared/config.json
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]  # Default to first option


@dataclass
class Config:
    """
    Centralized configuration with type hints.
    
    All values can be overridden via environment variables.
    Environment variable names are uppercase with underscores.
    Example: s3_bucket → S3_BUCKET
    """
    
    # Host identification
    host_id: str = "home-primary"
    host_name: str = "Home Primary"
    host_location: str = "Mumbai, India"
    host_isp: str = "Jio Fiber"
    
    # Speed thresholds
    expected_speed_mbps: int = 200
    tolerance_percent: int = 10
    connection_type_thresholds: Dict[str, int] = field(default_factory=lambda: {
        "Wi-Fi 5GHz": 200,
        "Wi-Fi 2.4GHz": 100,
        "Ethernet": 200,
        "Unknown": 150,
    })
    
    # S3 buckets
    s3_bucket: str = "vd-speed-test"
    s3_bucket_hourly: str = "vd-speed-test-hourly-prod"
    s3_bucket_weekly: str = "vd-speed-test-weekly-prod"
    s3_bucket_monthly: str = "vd-speed-test-monthly-prod"
    s3_bucket_yearly: str = "vd-speed-test-yearly-prod"
    
    # AWS settings
    aws_region: str = "ap-south-1"
    
    # Timezone
    timezone: str = "Asia/Kolkata"
    
    # Logging
    log_level: str = "INFO"
    log_max_bytes: int = 10485760  # 10MB
    log_backup_count: int = 5
    
    # Speed test
    speedtest_timeout: int = 180
    public_ip_api: str = "https://api.ipify.org"
    
    # Dashboard/API
    cache_ttl_seconds: int = 120  # 2 minutes
    parallel_fetch_threads: int = 20
    
    def get_bucket(self, period: str) -> str:
        """Get bucket name for a given aggregation period."""
        bucket_map = {
            "raw": self.s3_bucket,
            "minutes": self.s3_bucket,
            "latest": self.s3_bucket,
            "hourly": self.s3_bucket_hourly,
            "daily": self.s3_bucket,
            "weekly": self.s3_bucket_weekly,
            "monthly": self.s3_bucket_monthly,
            "yearly": self.s3_bucket_yearly,
        }
        return bucket_map.get(period, self.s3_bucket)
    
    @classmethod
    def from_file(cls, config_path: Optional[Path] = None) -> "Config":
        """
        Load config from JSON file with environment variable overrides.
        
        Priority: environment variables > config.json > defaults
        """
        if config_path is None:
            config_path = _find_config_path()
        
        # Start with defaults
        config_dict = {}
        
        # Load from file if exists
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_dict = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass  # Use defaults if file is invalid
        
        # Apply environment variable overrides
        env_overrides = {
            "host_id": os.environ.get("HOST_ID"),
            "s3_bucket": os.environ.get("S3_BUCKET"),
            "s3_bucket_hourly": os.environ.get("S3_BUCKET_HOURLY"),
            "s3_bucket_weekly": os.environ.get("S3_BUCKET_WEEKLY"),
            "s3_bucket_monthly": os.environ.get("S3_BUCKET_MONTHLY"),
            "s3_bucket_yearly": os.environ.get("S3_BUCKET_YEARLY"),
            "aws_region": os.environ.get("AWS_REGION"),
            "log_level": os.environ.get("LOG_LEVEL"),
            "timezone": os.environ.get("TIMEZONE") or os.environ.get("TZ"),
        }
        
        for key, value in env_overrides.items():
            if value is not None:
                config_dict[key] = value
        
        # Create config instance with merged values
        return cls(**{k: v for k, v in config_dict.items() if hasattr(cls, k) or k in cls.__dataclass_fields__})


@lru_cache(maxsize=1)
def get_config() -> Config:
    """
    Get the singleton Config instance.
    
    Cached for performance - config is loaded once per process.
    """
    return Config.from_file()


# Convenience function for quick access
def get(key: str, default=None):
    """
    Get a single config value by key.
    
    Example:
        from shared.config import get
        region = get("aws_region")
    """
    config = get_config()
    return getattr(config, key, default)
