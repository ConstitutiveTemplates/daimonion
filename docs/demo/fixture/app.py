"""Checkout handler."""

import logging

logger = logging.getLogger(__name__)


def handle_checkout(user):
    logger.info("user_data=%s", user.email)
