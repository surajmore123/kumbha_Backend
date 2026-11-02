"""
Reference information for journey planning, with provenance.

Every link and fact here was checked on CHECKED_ON. `status` says how much
weight it carries:
- "official": an official government, railway, transport or temple site;
- "official_announcement": an announcement by an authority (plans can
  still change before the Mela);
- "guidance": general planning advice from KumbhaPath, not an official
  rule.
`reachable` records whether the link answered when it was checked; some
official sites block automated checks, so False means "couldn't verify
automatically", not "wrong".

There are no public booking or availability APIs for Indian Railways
(IRCTC), MSRTC or airlines, so the app links to the official sites and
stores only references the user types in. Nothing here is live data.

Important bathing dates are not hardcoded: they come from the events
database (see `important_dates`).
"""

from django.utils import timezone

from apps.aiChat.services.event_service import visible_events

CHECKED_ON = "2026-10-29"

SOURCES = {
    "pib_rail_2025": {
        "title": "Railways review Nashik-Trimbakeshwar Simhastha 2027 rail plans",
        "organization": "Press Information Bureau, Ministry of Railways",
        "url": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2148431&lang=2&reg=48",
        "published_on": "2025-07-25",
        "status": "official_announcement",
        "reachable": True,
    },
    "ntkma_portal": {
        "title": "Nashik Kumbh Mela 2027 portal (Nashik–Trimbakeshwar Kumbh Mela Authority)",
        "organization": "Nashik–Trimbakeshwar Kumbh Mela Authority",
        "url": "https://www.nashikkumbha2027.com/",
        "status": "official",
        "reachable": True,
    },
    "divcom_authority": {
        "title": "About the Nashik–Trimbakeshwar Kumbh Mela Authority",
        "organization": "Divisional Commissioner, Nashik",
        "url": "https://divcomnashik.maharashtra.gov.in/en/about-nashik-trimbakeshwar-authority/",
        "status": "official",
        "reachable": False,
    },
    "irctc": {
        "title": "IRCTC train ticket booking",
        "organization": "Indian Railway Catering and Tourism Corporation",
        "url": "https://www.irctc.co.in/nget/train-search",
        "status": "official",
        "reachable": False,
    },
    "ntes": {
        "title": "NTES – train running status and enquiry",
        "organization": "Indian Railways",
        "url": "https://enquiry.indianrail.gov.in/ntes/",
        "status": "official",
        "reachable": True,
    },
    "indianrail": {
        "title": "Indian Railways passenger enquiry",
        "organization": "Indian Railways",
        "url": "https://www.indianrail.gov.in/",
        "status": "official",
        "reachable": True,
    },
    "msrtc": {
        "title": "MSRTC (Maharashtra State Road Transport Corporation)",
        "organization": "MSRTC",
        "url": "https://msrtc.maharashtra.gov.in/",
        "status": "official",
        "reachable": True,
    },
    "msrtc_booking": {
        "title": "MSRTC online bus reservation",
        "organization": "MSRTC",
        "url": "https://npublic.msrtcors.com/",
        "status": "official",
        "reachable": True,
    },
    "aai_pune": {
        "title": "Pune Airport",
        "organization": "Airports Authority of India",
        "url": "https://www.aai.aero/en/airports/pune",
        "status": "official",
        "reachable": True,
    },
    "maharashtra_tourism": {
        "title": "Maharashtra Tourism",
        "organization": "Government of Maharashtra",
        "url": "https://www.maharashtratourism.gov.in/",
        "status": "official",
        "reachable": True,
    },
    "mtdc": {
        "title": "MTDC resorts and bookings",
        "organization": "Maharashtra Tourism Development Corporation",
        "url": "https://www.mtdc.co/",
        "status": "official",
        "reachable": True,
    },
    "trimbakeshwar_trust": {
        "title": "Shri Trimbakeshwar Devasthan Trust",
        "organization": "Shri Trimbakeshwar Devasthan Trust",
        "url": "https://www.trimbakeshwartrust.com/",
        "status": "official",
        "reachable": True,
    },
    "nmc": {
        "title": "Nashik Municipal Corporation",
        "organization": "Nashik Municipal Corporation",
        "url": "https://nmc.gov.in/",
        "status": "official",
        "reachable": True,
    },
    "erss_112": {
        "title": "Emergency Response Support System (112)",
        "organization": "Government of India",
        "url": "https://112.gov.in/",
        "status": "official",
        "reachable": False,
    },
}

# Translated text for each language; keys missing in hi/mr fall back to en.
_TEXT = {
    "en": {
        "train": "Train",
        "train_note": (
            "Railways plan to manage Simhastha passenger traffic at five stations near "
            "the Mela area — Nashik Road, Devlali, Odha, Kherwadi and Kasbe Sukene — and "
            "to run long-distance specials and short-distance MEMU services. Check which "
            "station your train uses; special-train schedules are announced closer to the dates."
        ),
        "bus": "Bus",
        "bus_note": (
            "MSRTC runs state buses to Nashik and Trimbakeshwar. Book on the official MSRTC "
            "site; extra Mela services and temporary bus stands, if any, are announced by the authorities."
        ),
        "flight": "Flight",
        "flight_note": (
            "Airports used to reach Nashik include Nashik (Ozar), Mumbai, Pune and Shirdi. "
            "Check current flights with your airline, and plan the road or rail journey onward."
        ),
        "private": "Private vehicle",
        "private_note": (
            "On major bathing days vehicles are usually restricted near the ghats and parking "
            "is in designated areas. Follow the official traffic advisories issued before each day."
        ),
        "local": "Local travel",
        "local_note": (
            "Expect to walk long distances on bathing days. Local shuttles and routes for "
            "pilgrims are announced by the Kumbh authority — check before you travel."
        ),
        "stay_hotel": "Hotels",
        "stay_hotel_note": "Book early: demand around bathing days is very high. Confirm the location against the ghat you plan to visit.",
        "stay_dharamshala": "Dharamshalas",
        "stay_dharamshala_note": "Many are run by community trusts; contact them directly to confirm rooms and rules.",
        "stay_ashram": "Ashrams",
        "stay_ashram_note": "Some ashrams host pilgrims; ask about rules, timings and facilities before travelling.",
        "stay_budget": "Budget stays",
        "stay_budget_note": "Check reviews and exact location; very cheap stays far away can cost more in local travel.",
        "stay_family": "Family stays",
        "stay_family_note": "Look for rooms near a main road for easy transport, with food options close by.",
        "stay_accessible": "Accessible stays",
        "stay_accessible_note": "Ask about ground-floor rooms, lifts and step-free access, and get the answer in writing.",
        "stay_disclaimer": (
            "KumbhaPath doesn't list or verify individual properties and takes no bookings. "
            "Use official tourism sites or trusted providers, and keep your own confirmation."
        ),
        "contacts_note": "Save these numbers before you travel. Use 112 for any emergency.",
        "ntkma_contact": "Kumbh Mela Authority office (as listed on the official portal)",
        "emergency_112": "Emergency (police, fire, ambulance)",
        "dates_note": (
            "Dates from the KumbhaPath events list, which follows official announcements. "
            "Confirm before travelling; arrangements can change."
        ),
    },
    "hi": {
        "train": "ट्रेन",
        "train_note": (
            "रेलवे सिंहस्थ यात्रियों के लिए मेला क्षेत्र के पास पाँच स्टेशनों — नाशिक रोड, देवलाली, ओढा, "
            "खेरवाडी और कसबे सुकेणे — पर व्यवस्था करेगा और लंबी दूरी की विशेष तथा कम दूरी की MEMU "
            "सेवाएँ चलाएगा। अपनी ट्रेन का स्टेशन जाँचें; विशेष ट्रेनों का समय तारीखों के पास घोषित होगा।"
        ),
        "bus": "बस",
        "bus_note": "MSRTC नाशिक और त्र्यंबकेश्वर के लिए राज्य बसें चलाता है। आधिकारिक MSRTC साइट पर बुक करें; अतिरिक्त मेला सेवाएँ और अस्थायी बस स्टैंड अधिकारी घोषित करेंगे।",
        "flight": "विमान",
        "flight_note": "नाशिक पहुँचने के लिए नाशिक (ओझर), मुंबई, पुणे और शिर्डी हवाई अड्डे उपयोग होते हैं। अपनी एयरलाइन से उड़ानें जाँचें और आगे की सड़क या रेल यात्रा की योजना बनाएँ।",
        "private": "निजी वाहन",
        "private_note": "मुख्य स्नान के दिनों में घाटों के पास वाहन आमतौर पर प्रतिबंधित रहते हैं और पार्किंग तय स्थानों पर होती है। हर दिन से पहले जारी आधिकारिक यातायात सूचनाओं का पालन करें।",
        "local": "स्थानीय यात्रा",
        "local_note": "स्नान के दिनों में लंबी दूरी पैदल चलने की तैयारी रखें। यात्रियों के लिए स्थानीय शटल और मार्ग कुंभ प्राधिकरण घोषित करता है — यात्रा से पहले जाँचें।",
        "stay_hotel": "होटल",
        "stay_hotel_note": "जल्दी बुक करें: स्नान के दिनों के आसपास माँग बहुत अधिक रहती है। जिस घाट पर जाना है उसके हिसाब से स्थान जाँचें।",
        "stay_dharamshala": "धर्मशाला",
        "stay_dharamshala_note": "कई धर्मशालाएँ सामुदायिक ट्रस्ट चलाते हैं; कमरे और नियम उनसे सीधे पक्का करें।",
        "stay_ashram": "आश्रम",
        "stay_ashram_note": "कुछ आश्रम यात्रियों को ठहराते हैं; जाने से पहले नियम, समय और सुविधाएँ पूछ लें।",
        "stay_budget": "कम बजट ठहराव",
        "stay_budget_note": "समीक्षाएँ और सही स्थान देखें; बहुत दूर सस्ता ठहराव स्थानीय यात्रा में महँगा पड़ सकता है।",
        "stay_family": "परिवार के लिए ठहराव",
        "stay_family_note": "मुख्य सड़क के पास कमरे देखें ताकि आना-जाना आसान हो और भोजन पास में मिले।",
        "stay_accessible": "सुगम्य ठहराव",
        "stay_accessible_note": "भूतल के कमरे, लिफ्ट और बिना सीढ़ी के रास्ते के बारे में पूछें और लिखित में पुष्टि लें।",
        "stay_disclaimer": "KumbhaPath किसी संपत्ति की सूची या सत्यापन नहीं करता और कोई बुकिंग नहीं लेता। आधिकारिक पर्यटन साइटों या भरोसेमंद प्रदाताओं का उपयोग करें और अपनी पुष्टि संभालकर रखें।",
        "contacts_note": "यात्रा से पहले ये नंबर सहेज लें। किसी भी आपात स्थिति में 112 पर कॉल करें।",
        "ntkma_contact": "कुंभ मेला प्राधिकरण कार्यालय (आधिकारिक पोर्टल पर दिए अनुसार)",
        "emergency_112": "आपातकाल (पुलिस, अग्निशमन, एम्बुलेंस)",
        "dates_note": "तारीखें KumbhaPath कार्यक्रम सूची से हैं, जो आधिकारिक घोषणाओं पर आधारित है। यात्रा से पहले पुष्टि करें; व्यवस्थाएँ बदल सकती हैं।",
    },
    "mr": {
        "train": "रेल्वे",
        "train_note": (
            "रेल्वे सिंहस्थ प्रवाशांसाठी मेळा परिसराजवळील पाच स्थानकांवर — नाशिक रोड, देवळाली, ओढा, "
            "खेरवाडी आणि कसबे सुकेणे — व्यवस्था करणार असून लांब पल्ल्याच्या विशेष व कमी अंतराच्या MEMU "
            "गाड्या चालवणार आहे. तुमची गाडी कोणत्या स्थानकावर येते ते तपासा; विशेष गाड्यांचे वेळापत्रक तारखांच्या जवळ जाहीर होईल."
        ),
        "bus": "बस",
        "bus_note": "MSRTC नाशिक आणि त्र्यंबकेश्वरसाठी एसटी बस चालवते. अधिकृत MSRTC साइटवर आरक्षण करा; जादा मेळा सेवा व तात्पुरती बसस्थानके अधिकारी जाहीर करतील.",
        "flight": "विमान",
        "flight_note": "नाशिकला येण्यासाठी नाशिक (ओझर), मुंबई, पुणे आणि शिर्डी विमानतळ वापरले जातात. तुमच्या विमान कंपनीकडे उड्डाणे तपासा आणि पुढील रस्ता किंवा रेल्वे प्रवासाचे नियोजन करा.",
        "private": "खाजगी वाहन",
        "private_note": "मुख्य स्नानाच्या दिवशी घाटांजवळ वाहनांवर सहसा निर्बंध असतात आणि पार्किंग ठरावीक ठिकाणी असते. प्रत्येक दिवसापूर्वी जाहीर होणाऱ्या अधिकृत वाहतूक सूचनांचे पालन करा.",
        "local": "स्थानिक प्रवास",
        "local_note": "स्नानाच्या दिवशी लांब अंतर चालण्याची तयारी ठेवा. भाविकांसाठी स्थानिक शटल व मार्ग कुंभ प्राधिकरण जाहीर करते — प्रवासापूर्वी तपासा.",
        "stay_hotel": "हॉटेल",
        "stay_hotel_note": "लवकर आरक्षण करा: स्नानाच्या दिवसांच्या आसपास मागणी खूप असते. ज्या घाटावर जायचे त्यानुसार ठिकाण तपासा.",
        "stay_dharamshala": "धर्मशाळा",
        "stay_dharamshala_note": "अनेक धर्मशाळा समाज ट्रस्ट चालवतात; खोल्या व नियम त्यांच्याकडून थेट निश्चित करा.",
        "stay_ashram": "आश्रम",
        "stay_ashram_note": "काही आश्रम भाविकांना राहण्याची सोय देतात; जाण्यापूर्वी नियम, वेळा आणि सुविधा विचारा.",
        "stay_budget": "कमी खर्चाचे निवास",
        "stay_budget_note": "परीक्षणे व नेमके ठिकाण तपासा; खूप दूरचे स्वस्त निवास स्थानिक प्रवासात महाग पडू शकते.",
        "stay_family": "कुटुंबासाठी निवास",
        "stay_family_note": "मुख्य रस्त्याजवळ खोल्या पहा, म्हणजे ये-जा सोपी होईल आणि जेवण जवळ मिळेल.",
        "stay_accessible": "सुलभ निवास",
        "stay_accessible_note": "तळमजल्यावरील खोल्या, लिफ्ट आणि पायऱ्यांशिवाय मार्गाबद्दल विचारा आणि लेखी खात्री घ्या.",
        "stay_disclaimer": "KumbhaPath कोणत्याही निवासाची यादी किंवा पडताळणी करत नाही आणि आरक्षण घेत नाही. अधिकृत पर्यटन साइट किंवा विश्वासार्ह सेवांचा वापर करा आणि तुमची पुष्टी जपून ठेवा.",
        "contacts_note": "प्रवासापूर्वी हे क्रमांक जतन करा. कोणत्याही आणीबाणीत 112 वर कॉल करा.",
        "ntkma_contact": "कुंभ मेळा प्राधिकरण कार्यालय (अधिकृत पोर्टलवर दिल्याप्रमाणे)",
        "emergency_112": "आणीबाणी (पोलीस, अग्निशमन, रुग्णवाहिका)",
        "dates_note": "तारखा KumbhaPath कार्यक्रम यादीतून आहेत, जी अधिकृत घोषणांवर आधारित आहे. प्रवासापूर्वी खात्री करा; व्यवस्था बदलू शकतात.",
    },
}


def text(language: str, key: str) -> str:
    return _TEXT.get(language, {}).get(key) or _TEXT["en"][key]


def _source(key: str) -> dict:
    return {"id": key, "checked_on": CHECKED_ON, **SOURCES[key]}


def transport_options(language: str) -> list[dict]:
    rows = [
        ("train", "official_announcement", ["irctc", "ntes", "indianrail", "pib_rail_2025"]),
        ("bus", "official", ["msrtc_booking", "msrtc"]),
        ("flight", "guidance", ["aai_pune"]),
        ("private", "guidance", ["ntkma_portal"]),
        ("local", "guidance", ["ntkma_portal", "nmc"]),
    ]
    return [
        {
            "mode": mode,
            "title": text(language, mode),
            "note": text(language, f"{mode}_note"),
            "status": status,
            "links": [_source(key) for key in links],
            "booking_api": False,
        }
        for mode, status, links in rows
    ]


def accommodation_options(language: str) -> dict:
    categories = ["hotel", "dharamshala", "ashram", "budget", "family", "accessible"]
    return {
        "disclaimer": text(language, "stay_disclaimer"),
        "categories": [
            {
                "category": category,
                "title": text(language, f"stay_{category}"),
                "note": text(language, f"stay_{category}_note"),
                "status": "guidance",
            }
            for category in categories
        ],
        "links": [_source(key) for key in ("maharashtra_tourism", "mtdc", "trimbakeshwar_trust")],
    }


def contacts(language: str) -> dict:
    return {
        "note": text(language, "contacts_note"),
        "items": [
            {
                "label": text(language, "emergency_112"),
                "phone": "112",
                "status": "official",
                "source": _source("erss_112"),
            },
            {
                "label": text(language, "ntkma_contact"),
                "phone": "0253-2461909",
                "email": "kumbhmela.2027@mah.gov.in",
                "status": "official",
                "source": _source("ntkma_portal"),
            },
        ],
    }


def important_dates(language: str, start=None, end=None) -> dict:
    """Kumbh milestones and bathing days from the events database."""
    events = visible_events().filter(
        event_category__in=("SNAN", "KUMBH_LIFECYCLE"),
        event_date__gte=start or timezone.localdate(),
    )
    if end:
        events = events.filter(event_date__lte=end)
    return {
        "note": text(language, "dates_note"),
        "items": [
            {
                "event_id": str(event.event_id),
                "name": event.event_name,
                "date": event.event_date.isoformat(),
                "start_time": event.start_time.isoformat() if event.start_time else None,
                "category": event.event_category,
                "location": event.location_name or event.location_type,
                "data_source": event.data_source,
                "last_checked": event.updated_at.isoformat() if event.updated_at else None,
            }
            for event in events.order_by("event_date", "start_time")[:30]
        ],
        "source": _source("ntkma_portal"),
    }


def planning_guide(language: str) -> dict:
    return {
        "checked_on": CHECKED_ON,
        "transport": transport_options(language),
        "accommodation": accommodation_options(language),
        "contacts": contacts(language),
        "important_dates": important_dates(language),
        "sources": [_source(key) for key in SOURCES],
    }
