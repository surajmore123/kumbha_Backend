import os
import json
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
        cred = credentials.Certificate(
            os.path.join(
                settings.BASE_DIR,
                "config",
                "credentials",
                "firebase_service_account.json"
            )
        )

    firebase_admin.initialize_app(cred)