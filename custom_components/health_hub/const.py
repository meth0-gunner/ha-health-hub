"""Constants for Health Hub."""

DOMAIN = "health_hub"
NAME = "Health Hub"

CONF_RETENTION_DAYS = "retention_days"
CONF_OVERLAP_HOURS = "overlap_hours"
DEFAULT_RETENTION_DAYS = 90
DEFAULT_OVERLAP_HOURS = 48

STORE_FILE = "health_hub/health_hub.db"

SIGNAL_UPDATED = f"{DOMAIN}_updated"
