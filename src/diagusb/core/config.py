# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Modulo de configuracion para DiagUSB."""

import configparser
from pathlib import Path
from typing import Any

class Config:
    """Gestor de configuracion de DiagUSB."""
    
    DEFAULT_CONFIG = {
        'general': {
            'language': 'es-AR',
            'log_level': 'INFO',
        },
        'collectors': {
            'timeout_seconds': '15',
            'connectivity_timeout': '2',
            'max_events': '20',
        },
        'reports': {
            'output_dir': 'reports',
            'date_format': '%Y-%m-%d %H:%M:%S',
            'include_context': 'true',
            'include_timestamps': 'true',
        },
        'snapshots': {
            'snapshots_dir': 'snapshots',
            'filename_format': 'snapshot_%Y%m%d_%H%M%S.json',
        },
    }
    
    def __init__(self, config_path: Path | None = None):
        self.config = configparser.ConfigParser()
        self.config_path = config_path
        self._load()
    
    def _load(self):
        """Carga la configuracion desde archivo o usa valores por defecto."""
        if self.config_path and self.config_path.exists():
            self.config.read(self.config_path, encoding='utf-8')
        else:
            for section, values in self.DEFAULT_CONFIG.items():
                self.config[section] = values
    
    def get(self, section: str, key: str, fallback: Any = None) -> str:
        """Obtiene un valor de configuracion."""
        return self.config.get(section, key, fallback=fallback)
    
    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        """Obtiene un valor entero de configuracion."""
        return self.config.getint(section, key, fallback=fallback)
    
    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        """Obtiene un valor booleano de configuracion."""
        return self.config.getboolean(section, key, fallback=fallback)
    
    def get_path(self, section: str, key: str, fallback: str = '') -> Path:
        """Obtiene un valor de ruta de configuracion."""
        return Path(self.config.get(section, key, fallback=fallback))
    
    def set(self, section: str, key: str, value: str):
        """Establece un valor de configuracion."""
        if not self.config.has_section(section):
            self.config[section] = {}
        self.config[section][key] = str(value)
    
    def save(self, path: Path | None = None):
        """Guarda la configuracion a archivo."""
        save_path = path or self.config_path
        if save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                self.config.write(f)

def get_config(config_path: Path | None = None) -> Config:
    """Obtiene una instancia de configuracion."""
    return Config(config_path)
