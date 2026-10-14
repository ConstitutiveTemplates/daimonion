import logging

logger = logging.getLogger(__name__)


def log_failed_login(email, ip):
    logger.warning("failed login: email=%s ip=%s", email, ip)
