import hashlib
import logging

logger = logging.getLogger(__name__)


def log_failed_login(email, ip):
    digest = hashlib.sha256(email.encode()).hexdigest()[:12]
    logger.warning("failed login: user=%s ip=%s", digest, ip)
