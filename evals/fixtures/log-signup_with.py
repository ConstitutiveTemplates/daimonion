import hashlib
import logging

logger = logging.getLogger(__name__)


def _mask_email(email):
    local, _, domain = email.partition("@")
    return local[:1] + "***@" + domain


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def log_signup(user):
    logger.info("new signup: email=%s id_hash=%s", _mask_email(user.email), _hash(str(user.id)))
