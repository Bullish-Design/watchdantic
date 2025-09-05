#!/usr/bin/env python3
# /// script
# dependencies = [
#     "watchdantic>=0.2.1",
#     "pydantic>=2.0.0",
#     "tomli>=2.0.0; python_version < '3.11'",
#     "tomli_w>=1.0.0",
# ]
# ///
"""
TOML Configuration File Watcher Example

This script demonstrates how to use Watchdantic to monitor TOML configuration files
and automatically reload application settings when they change.

Usage:
    uv run example_toml_watcher.py

The script will:
1. Create an example config.toml file
2. Set up a watcher for *.toml files
3. Reload and validate configuration when files change
4. Demonstrate atomic writing of configuration updates
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from watchdantic import Watchdantic, WatchdanticConfig


class DatabaseConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    name: str = "myapp"
    ssl: bool = True


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    debug: bool = False


class AppConfig(BaseModel):
    """Application configuration model matching TOML structure."""
    name: str
    version: str
    description: str = ""
    
    # Nested configuration sections
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    
    # Feature flags and settings
    features: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    max_connections: int = 100


def main() -> None:
    print("🔧 TOML Configuration Watcher Example")
    print("=" * 50)
    
    # Create working directory
    config_dir = Path("./toml_config_example")
    config_dir.mkdir(exist_ok=True)
    
    # Initialize Watchdantic with structured logging
    w = Watchdantic(
        WatchdanticConfig(
            default_debounce=0.5,
            enable_logging=True,
            log_level="INFO",
        )
    )
    
    # Global state to track current configuration
    current_config: AppConfig | None = None

    @w.triggers_on(AppConfig, "*.toml", debounce=0.3)
    def handle_config_update(configs: List[AppConfig], file_path: Path) -> None:
        """Handle configuration file updates."""
        nonlocal current_config
        
        config = configs[0]  # TOML files contain single configuration
        current_config = config
        
        print(f"\n📝 Configuration updated from: {file_path.name}")
        print(f"   App: {config.name} v{config.version}")
        print(f"   Database: {config.database.host}:{config.database.port}")
        print(f"   Server: {config.server.host}:{config.server.port}")
        print(f"   Features: {', '.join(config.features) if config.features else 'None'}")
        print(f"   Log Level: {config.log_level}")
        
        # Simulate application reconfiguration
        if config.server.debug:
            print("   🚨 DEBUG MODE ENABLED")
        
        print(f"   ✅ Configuration reloaded successfully!")

    # Create example configuration file
    example_config = AppConfig(
        name="MyWebApp",
        version="1.0.0",
        description="Example web application with TOML configuration",
        database=DatabaseConfig(
            host="localhost",
            port=5432,
            name="webapp_db",
            ssl=True
        ),
        server=ServerConfig(
            host="127.0.0.1",
            port=8080,
            workers=2,
            debug=False
        ),
        features=["authentication", "caching", "metrics"],
        log_level="DEBUG",
        max_connections=50
    )
    
    config_file = config_dir / "config.toml"
    print(f"\n📄 Creating example configuration: {config_file}")
    
    # Use Watchdantic's atomic write to create the file
    w.write_models([example_config], config_file)
    
    print(f"✅ Created {config_file}")
    
    # Start watching
    print(f"\n👀 Watching for TOML changes in: {config_dir}")
    print("   Try editing config.toml to see live updates!")
    print("   Press Ctrl+C to exit")
    
    w.start(config_dir)
    
    try:
        # Demonstrate programmatic configuration updates
        time.sleep(2)
        
        print(f"\n🔄 Demonstrating programmatic update...")
        
        # Update configuration
        if current_config:
            updated_config = current_config.model_copy(deep=True)
            updated_config.server.debug = True
            updated_config.features.append("hot_reload")
            updated_config.version = "1.1.0"
            
            w.write_models([updated_config], config_file)
            print("   Updated config with debug=true and new feature")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Shutting down watcher...")
        w.stop()
        print("   Goodbye!")


if __name__ == "__main__":
    main()