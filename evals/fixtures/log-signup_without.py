import logging

logger = logging.getLogger(__name__)


def log_signup(user):
    logger.info("new signup: email=%s phone=%s id=%s", user.email, user.phone, user.id)
    print(f"signup complete for {user.email}")
