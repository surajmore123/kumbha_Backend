import os
import firebase_admin
from firebase_admin import credentials
from django.conf import settings

if not firebase_admin._apps:
    cred = credentials.Certificate(
        os.path.join(
            settings.BASE_DIR,
            "config",
            "credentials",
            "firebase_service_account.json"
        )
    )
    firebase_admin.initialize_app(cred)