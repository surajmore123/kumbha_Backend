"""
Starting data for `manage.py seed_bookings`, checked 2026-10-30. Only stays with
an official published source are included. Rates are ordinary published rates,
not Kumbh rates. No property photograph has confirmed rights, so stays fall back
to a labelled area photograph.
"""

from datetime import date

CHECKED = date(2026, 10, 30)
RAMKUND = ("19.997500", "73.791000")

AREAS = [
    # slug, English, Hindi, Marathi, seed image, coordinates
    ("ramkund", "Ramkund", "रामकुंड", "रामकुंड", "ramkund-sankranti", RAMKUND),
    ("panchavati", "Panchavati", "पंचवटी", "पंचवटी", "kalaram", "temple:Kala Rama"),
    ("trimbakeshwar", "Trimbakeshwar", "त्र्यंबकेश्वर", "त्र्यंबकेश्वर", "trimbakeshwar-mist", "temple:Trimbakeshwar"),
    ("tapovan", "Tapovan", "तपोवन", "तपोवन", "tapovan-rama", None),
    ("nashik", "Nashik city", "नाशिक शहर", "नाशिक शहर", "kumbh-panorama", None),
]

AMENITIES = [
    ("hot-water", "Hot water", "गरम पानी", "गरम पाणी"),
    ("attached-bath", "Attached bathroom", "संलग्न स्नानघर", "जोडलेले स्नानगृह"),
    ("ac", "Air conditioning", "वातानुकूलन", "वातानुकूलन"),
    ("parking", "Parking", "पार्किंग", "पार्किंग"),
    ("food", "Food available", "भोजन उपलब्ध", "जेवण उपलब्ध"),
]

SOURCES = {
    "trust_rooms": {
        "title": "Shivprasad Bhaktniwas: online booking and rules",
        "url": "https://trimbakeshwartrust.com/bhaktniwas",
        "organization": "Shri Trimbakeshwar Devasthan Trust", "source_type": "official_akhada",
    },
    "mtdc": {
        "title": "MTDC Grape Park", "url": "https://mtdc.co/en/stays/mtdc-grape-park",
        "organization": "Maharashtra Tourism Development Corporation", "source_type": "government",
        "verification_notes": "Found through search; the page refused automated reading. Confirm rooms, rates and contact.",
    },
}

STAYS = [
    {
        "name": "Shivprasad Bhaktniwas", "type_label": "Bhaktniwas", "stay_type": "dharamshala",
        "area": "trimbakeshwar", "town": "Trimbakeshwar", "area_text": "Near Trimbakeshwar Bus Stand, Mahadevi Road",
        "address": "Near Trimbakeshwar Bus Stand, Mahadevi Road, Trimbakeshwar 422112",
        "price_from": 1333, "unit": "room per day, plus 5% GST", "price_status": "verified",
        "phone": "02594-234251", "email": "trimbakeshwartrust2015@gmail.com",
        "website_url": "https://trimbakeshwartrust.com/", "booking_url": "https://trimbakeshwartrust.com/bhaktniwas",
        "verified": True, "amenities": ["hot-water", "ac"], "sources": ["trust_rooms"],
        "rooms": [
            ("AC 2-bed room", "एसी 2-बेड कमरा", "एसी 2-बेड खोली", 1714),
            ("Non-AC 2-bed room", "नॉन-एसी 2-बेड कमरा", "नॉन-एसी 2-बेड खोली", 1333),
        ],
        "en": (
            "Pilgrim rooms run by the Shri Trimbakeshwar Devasthan Trust, near the Trimbakeshwar bus stand.",
            "Book on the Trust's website after signing in with Google. You'll need ID (PAN card or driving licence) and at least two guests per room, for 1 to 10 days. Check-in from 1 pm, check-out by noon.",
            "The Trust says bookings are non-refundable, can't be cancelled or transferred, and dates can't be changed.",
            "Ordinary published rates. Kumbh rates may differ.",
        ),
        "hi": (
            "श्री त्र्यंबकेश्वर देवस्थान ट्रस्ट द्वारा संचालित श्रद्धालु कक्ष, त्र्यंबकेश्वर बस स्टैंड के पास।",
            "गूगल से साइन इन करके ट्रस्ट की वेबसाइट पर बुक करें। पहचान पत्र (पैन कार्ड या ड्राइविंग लाइसेंस) चाहिए और हर कमरे में कम से कम दो अतिथि, 1 से 10 दिन के लिए। चेक-इन दोपहर 1 बजे से, चेक-आउट दोपहर 12 बजे तक।",
            "ट्रस्ट के अनुसार बुकिंग की राशि वापस नहीं होती, इसे रद्द या हस्तांतरित नहीं किया जा सकता और तिथियाँ नहीं बदलतीं।",
            "सामान्य प्रकाशित दरें। कुंभ में दरें अलग हो सकती हैं।",
        ),
        "mr": (
            "श्री त्र्यंबकेश्वर देवस्थान ट्रस्टतर्फे चालवल्या जाणाऱ्या भाविक खोल्या, त्र्यंबकेश्वर बसस्थानकाजवळ.",
            "गुगलने साइन इन करून ट्रस्टच्या संकेतस्थळावर आरक्षण करा. ओळखपत्र (पॅन कार्ड किंवा वाहन परवाना) आवश्यक आहे आणि प्रत्येक खोलीत किमान दोन पाहुणे, 1 ते 10 दिवसांसाठी. चेक-इन दुपारी 1 पासून, चेक-आउट दुपारी 12 पर्यंत.",
            "ट्रस्टनुसार आरक्षणाची रक्कम परत मिळत नाही, ते रद्द किंवा हस्तांतरित करता येत नाही आणि तारखा बदलता येत नाहीत.",
            "सामान्य प्रकाशित दर. कुंभात दर वेगळे असू शकतात.",
        ),
    },
    {
        "name": "MTDC Grape Park", "type_label": "State tourism resort", "stay_type": "hotel",
        "area": "nashik", "town": "Nashik", "area_text": "Next to the MTDC Boat Club",
        "address": "", "price_from": 0, "unit": "", "price_status": "on_request",
        "website_url": "https://mtdc.co/en/stays/mtdc-grape-park",
        "verified": False, "amenities": [], "sources": ["mtdc"], "rooms": [],
        "en": ("A resort run by the Maharashtra Tourism Development Corporation in Nashik, beside its Boat Club.",
               "Check rooms and rates with MTDC directly.", "", ""),
        "hi": ("नाशिक में महाराष्ट्र पर्यटन विकास निगम का रिसॉर्ट, उसके बोट क्लब के पास।",
               "कमरे और दरें सीधे एमटीडीसी से जाँचें।", "", ""),
        "mr": ("नाशिकमधील महाराष्ट्र पर्यटन विकास महामंडळाचा रिसॉर्ट, त्याच्या बोट क्लबजवळ.",
               "खोल्या आणि दर थेट एमटीडीसीकडे तपासा.", "", ""),
    },
]

_API_NONE = "No public API found. Partner or agent access only. Opens the provider's site."

TRANSPORT = [
    ("irctc", "train", "IRCTC", True, "https://www.irctc.co.in/", "https://www.irctc.co.in/nget/train-search", True,
     "Book reserved train tickets. Nashik Road is the main station for Nashik.",
     "आरक्षित रेल टिकट बुक करें। नाशिक के लिए मुख्य स्टेशन नाशिक रोड है।",
     "आरक्षित रेल्वे तिकिटे बुक करा. नाशिकसाठी मुख्य स्थानक नाशिक रोड आहे.",
     _API_NONE + " Booking through agents needs IRCTC accreditation."),
    ("ntes", "train", "NTES (National Train Enquiry)", True, "https://enquiry.indianrail.gov.in/ntes/", "", False,
     "Check train schedules and running status.", "ट्रेन की समय-सारणी और चलने की स्थिति देखें।", "गाड्यांचे वेळापत्रक आणि सध्याची स्थिती पहा.",
     "Enquiry site, no public API."),
    ("msrtc-booking", "bus", "MSRTC online reservation", True, "https://msrtc.maharashtra.gov.in/", "https://npublic.msrtcors.com/", True,
     "Reserve Maharashtra state buses to Nashik and Trimbakeshwar.", "नाशिक और त्र्यंबकेश्वर के लिए महाराष्ट्र राज्य परिवहन की बसें आरक्षित करें।", "नाशिक आणि त्र्यंबकेश्वरसाठी एसटी बस आरक्षित करा.",
     _API_NONE + " MSRTC gave IRCTC API access under an MoU; no open partner programme found."),
    ("pune-airport", "flight", "Pune Airport (AAI)", True, "https://www.aai.aero/en/airports/pune", "", False,
     "Airport information. Book flights with your airline, then continue by road or rail.", "हवाई अड्डे की जानकारी। उड़ान अपनी एयरलाइन से बुक करें और आगे सड़क या रेल से जाएँ।", "विमानतळाची माहिती. विमान आपल्या कंपनीकडे आरक्षित करा आणि पुढे रस्ता किंवा रेल्वेने जा.",
     "Flight search APIs (for example Amadeus) need production approval; booking needs a consolidator agreement."),
    ("uber", "taxi", "Uber", False, "https://www.uber.com/in/en/", "", False,
     "App-based cabs. Check coverage in Nashik, and expect road closures on bathing days.", "ऐप आधारित कैब। नाशिक में उपलब्धता जाँचें और स्नान के दिनों में सड़कें बंद रहने की अपेक्षा रखें।", "अॅप आधारित कॅब. नाशिकमधील उपलब्धता तपासा आणि स्नानाच्या दिवशी रस्ते बंद असू शकतात.",
     "Pre-filled deep links need a client_id from a developer account. Not set up."),
    ("ola", "taxi", "Ola", False, "https://www.olacabs.com/", "", False,
     "App-based cabs. Check coverage in Nashik.", "ऐप आधारित कैब। नाशिक में उपलब्धता जाँचें।", "अॅप आधारित कॅब. नाशिकमधील उपलब्धता तपासा.", "No public API found."),
    ("msrtc-local", "local", "MSRTC", True, "https://msrtc.maharashtra.gov.in/", "", False,
     "Local and town buses between Nashik and Trimbakeshwar. Shuttle routes for the Kumbh will be announced by the authority.", "नाशिक और त्र्यंबकेश्वर के बीच स्थानीय बसें। कुंभ के शटल मार्ग प्राधिकरण घोषित करेगा।", "नाशिक आणि त्र्यंबकेश्वर दरम्यान स्थानिक बस. कुंभाचे शटल मार्ग प्राधिकरण जाहीर करेल.",
     "No public API."),
]
