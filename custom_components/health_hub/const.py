"""Constants for Health Hub."""

DOMAIN = "health_hub"
NAME = "Health Hub"

CONF_RETENTION_DAYS = "retention_days"
CONF_OVERLAP_HOURS = "overlap_hours"
DEFAULT_RETENTION_DAYS = 90
DEFAULT_OVERLAP_HOURS = 48

CONF_REVIEW_ENABLED = "review_enabled"
CONF_REVIEW_TIME = "review_time"
DEFAULT_REVIEW_ENABLED = True
DEFAULT_REVIEW_TIME = "10:00:00"  # review anyway if no night has synced by then

CONF_SYNC_PHONE = "sync_phone"  # the notify service of the phone running the Health Hub app

# The phone app listens for this broadcast (sent through the HA Companion app).
APP_PACKAGE = "io.github.meth0gunner.healthhub"
SYNC_NOW_ACTION = f"{APP_PACKAGE}.SYNC_NOW"

STORE_FILE = "health_hub/health_hub.db"
REVIEW_DIR = "health_hub/review"

SIGNAL_UPDATED = f"{DOMAIN}_updated"
SIGNAL_REVIEW = f"{DOMAIN}_review"
