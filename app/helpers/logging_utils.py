import logging

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"


def build_formatter():
    return logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
