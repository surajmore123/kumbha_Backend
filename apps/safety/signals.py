from django.dispatch import Signal

# Sent once a helper has confirmed a new alert. Lost & Found listens to this, so
# the safety app doesn't need to know about cases. Argument: `alert`.
alert_confirmed = Signal()
