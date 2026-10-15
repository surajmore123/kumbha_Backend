import os
import json
import logging
import firebase_admin
from firebase_admin import credentials
from django.conf import settings

if not firebase_admin._apps:

    firebase_json = os.getenv("FIREBASE_CREDENTIALS")

    if firebase_json:
        # Running on server (Render)
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)

    else:
        # Running locally
        cred_path = os.path.join(
            settings.BASE_DIR,
            "config",
            "credentials",
            "firebase_service_account.json"
        )
        cred = credentials.Certificate(cred_path) if os.path.exists(cred_path) else None

    if cred:
        firebase_admin.initialize_app(cred)
    else:
        logging.getLogger(__name__).warning(
            "Firebase credentials not found: set FIREBASE_CREDENTIALS; push notifications are disabled"
        )