"""Logging configuration for the application."""

import logging

def setup_logging(filename="logs.txt"):
    """Set up logging configuration."""
    # File handler
    logging.basicConfig(
        filename=filename,
        filemode="a",
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)