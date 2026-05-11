from .tasks import process_payment_notifications


def queue_payment_notifications(payment_pk, actor_pk=None):
    process_payment_notifications.delay(payment_pk, actor_pk)
