"""Constants for the Jamf Now integration."""

DOMAIN = "jamfnow"
PLATFORMS: list[str] = ["sensor", "select", "button", "switch", "text", "device_tracker"]

CONF_BASE_URL = "base_url"

DEFAULT_BASE_URL = "https://services-api.services.jamfnow.com"
UPDATE_INTERVAL_SECONDS = 300

# Lost Mode takes a short while to be confirmed by the device (PENDING -> ENABLED)
LOST_MODE_WAIT_TIMEOUT = 120
LOST_MODE_POLL_INTERVAL = 5

SERVICE_SET_BLUEPRINT = "set_blueprint"
SERVICE_ENABLE_LOST_MODE = "enable_lost_mode"
SERVICE_DISABLE_LOST_MODE = "disable_lost_mode"
SERVICE_PLAY_SOUND = "play_sound"
SERVICE_RESTART_DEVICE = "restart_device"
SERVICE_SHUTDOWN_DEVICE = "shutdown_device"
SERVICE_SYNC_INVENTORY = "sync_inventory"
