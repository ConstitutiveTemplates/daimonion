import logging

logger = logging.getLogger(__name__)


def handle_checkout_error(order, user, exc):
    logger.exception("checkout failed for %s (%s): %s", user.email, user.phone, exc)
    print("order debug:", order.id, user.email, repr(exc))
