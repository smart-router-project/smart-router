"""Logging configuration for Smart Router."""

import logging

def init_logging(level: str):

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )