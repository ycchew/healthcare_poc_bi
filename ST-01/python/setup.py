"""
ST-01: Data Foundation & Infrastructure
Configuration and setup utilities.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database configuration dataclass."""

    host: str
    port: str
    database: str
    user: str
    password: str

    @property
    def connection_string(self) -> str:
        """Generate PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class ProjectConfig:
    """Project configuration dataclass."""

    project_root: Path
    data_dir: Path
    output_dir: Path
    logs_dir: Path

    @classmethod
    def from_env(cls) -> "ProjectConfig":
        """Create config from environment."""
        root = Path(__file__).parent.parent.parent
        return cls(
            project_root=root,
            data_dir=root / "data",
            output_dir=root / "docs" / "output",
            logs_dir=root / "logs",
        )


class ConfigManager:
    """Configuration manager for the healthcare analytics project."""

    def __init__(self):
        """Initialize configuration manager."""
        self.project_config = ProjectConfig.from_env()
        self.db_config = self._load_db_config()

    def _load_db_config(self) -> DatabaseConfig:
        """Load database configuration from environment."""
        return DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "healthcare"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )

    def get_db_config(self) -> DatabaseConfig:
        """Get database configuration."""
        return self.db_config

    def get_project_paths(self) -> Dict[str, Path]:
        """Get project directory paths."""
        return {
            "root": self.project_config.project_root,
            "data": self.project_config.data_dir,
            "output": self.project_config.output_dir,
            "logs": self.project_config.logs_dir,
            "st01_sql": self.project_config.project_root / "ST-01" / "sql",
            "st01_python": self.project_config.project_root / "ST-01" / "python",
        }

    def ensure_directories(self) -> None:
        """Create project directories if they don't exist."""
        paths = self.get_project_paths()
        for name, path in paths.items():
            if name != "root":
                path.mkdir(parents=True, exist_ok=True)


# Global config instance
_config: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get or create configuration manager."""
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config


def setup_project() -> None:
    """Setup project directories and environment."""
    config = get_config()
    config.ensure_directories()
    print("Project directories created successfully")


if __name__ == "__main__":
    setup_project()
