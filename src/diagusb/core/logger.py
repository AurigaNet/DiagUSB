# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Modulo de logging para DiagUSB."""

import logging
import sys
from pathlib import Path
from datetime import datetime


class DiagUsbLogger:
    """Logger personalizado para DiagUSB."""
    
    def __init__(self, name: str = "diagusb", log_file: Path | None = None, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.handlers.clear()
        
        # Formato con timestamp
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler de consola
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(formatter)
        self.logger.addHandler(console)
        
        # Handler de archivo si se especifica
        if log_file:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, msg: str):
        self.logger.debug(msg)
    
    def info(self, msg: str):
        self.logger.info(msg)
    
    def warning(self, msg: str):
        self.logger.warning(msg)
    
    def error(self, msg: str):
        self.logger.error(msg)
    
    def critical(self, msg: str):
        self.logger.critical(msg)


def get_logger(name: str = "diagusb", log_file: Path | None = None) -> DiagUsbLogger:
    """Obtiene una instancia del logger."""
    return DiagUsbLogger(name, log_file)
