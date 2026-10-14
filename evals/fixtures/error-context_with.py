import hashlib
import logging

logger = logging.getLogger(__name__)


def _hash(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


def handle_checkout_error(order, user, exc):
    logger.exception("checkout failed for order=%s user=%s: %s", order.id, _hash(user.email), exc)
