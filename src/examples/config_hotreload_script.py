"""Configuration hot-reload example with Watchdantic."""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict
import json

from pydantic import BaseModel, Field
from watchdantic import Watchdantic, WatchdanticConfig
from watchdantic.core.logging import WatchdanticLogger

WatchdanticLogger.model_rebuild()


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    host: str = Field(default="localhost")
    port: int = Field(default=5432, ge=1, le=65535)
    database: str
    username: str
    password: str = Field(exclude=True)  # Don't log passwords
    pool_size: int = Field(default=10, ge=1, le=100)


class AppConfig(BaseModel):
    """Main application configuration."""

    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARN|ERROR)$")
    api_keys: Dict[str, str] = Field(default_factory=dict)
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    database: DatabaseConfig
    max_concurrent_requests: int = Field(default=100, ge=1)


# Mock application state
class MockApp:
    """Simulated application for demonstration."""

    def __init__(self):
        self.config: AppConfig | None = None
        self.is_running = False

    def update_config(self, new_config: AppConfig):
        """Update application configuration."""
        old_debug = self.config.debug if self.config else None
        old_log_level = self.config.log_level if self.config else None

        self.config = new_config

        print(f"🔧 Configuration updated:")
        print(f"   Debug mode: {new_config.debug}")
        print(f"   Log level: {new_config.log_level}")
        print(f"   Database: {new_config.database.host}:{new_config.database.port}/{new_config.database.database}")
        print(f"   Feature flags: {len(new_config.feature_flags)} enabled")
        print(f"   API keys: {len(new_config.api_keys)} configured")

        # Simulate configuration changes
        if old_debug is not None and old_debug != new_config.debug:
            if new_config.debug:
                print("   🔍 Debug mode ENABLED - verbose logging activated")
            else:
                print("   🔇 Debug mode DISABLED - production logging")

        if old_log_level is not None and old_log_level != new_config.log_level:
            print(f"   📝 Log level changed: {old_log_level} → {new_config.log_level}")

    def start(self):
        """Start the mock application."""
        self.is_running = True
        print("🚀 Mock application started")


def main():
    """Configuration hot-reload example."""
    app = MockApp()
    watcher = Watchdantic()

    @watcher.triggers_on(
        AppConfig,
        "config.json",
        debounce=0.5,  # Quick reload for config changes
    )
    def reload_config(configs: List[AppConfig], file_path: Path):
        """Hot-reload application configuration."""
        config = configs[0]  # Single config expected in JSON file

        print(f"\n📡 Config file changed: {file_path}")
        app.update_config(config)

        # Validate critical settings
        if config.database.pool_size > 50:
            print("   ⚠️  Warning: Large database pool size may impact memory")

        if config.max_concurrent_requests > 1000:
            print("   ⚠️  Warning: High concurrent request limit")

        print("   ✅ Configuration reload complete\n")

    # Create initial configuration
    initial_config = AppConfig(
        debug=False,
        log_level="INFO",
        api_keys={"external_api": "key123", "payment_gateway": "key456"},
        feature_flags={"new_ui": False, "beta_features": False, "advanced_analytics": True},
        database=DatabaseConfig(
            host="localhost", port=5432, database="myapp", username="app_user", password="secret123", pool_size=20
        ),
        max_concurrent_requests=200,
    )

    # Write initial config
    config_path = Path("config.json")
    print(f"Creating initial configuration: {config_path}")

    # Write config manually to show JSON format
    config_dict = initial_config.model_dump()
    with open(config_path, "w") as f:
        json.dump(config_dict, f, indent=2)

    print("Starting configuration monitor...")
    watcher.start(".")

    # Start mock app
    app.start()

    print(f"""
📋 Configuration hot-reload active!

Current config file: {config_path.absolute()}

Try editing the config file to see hot-reload in action:
  - Change debug: true/false
  - Modify log_level: "DEBUG", "INFO", "WARN", "ERROR"
  - Update feature_flags
  - Adjust database settings

Changes will be automatically detected and applied.
Press Ctrl+C to stop.
""")

    try:
        import time

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Stopping configuration monitor...")
        watcher.stop()
        print("Configuration monitor stopped.")


if __name__ == "__main__":
    main()

