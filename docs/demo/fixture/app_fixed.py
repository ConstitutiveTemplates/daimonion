import hashlib
import logging

logger = logging.getLogger(__name__)


def pseudonym(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def handle_checkout(user):
    logger.info("user_ref=%s", pseudonym(user.email))
