"""
Rules-based itinerary and checklist suggestions for a JourneyPlan.

Deterministic and independent of any AI service: the same inputs give the
same plan. It uses the plan's dates and preferences, active temples from
the temples app and visible events (bathing days, milestones) from the
events app. It never states travel times, crowd forecasts, fares or
closures: where those matter it says to check official advisories.

Regenerating keeps what the user made: items they added, suggestions they
edited, and checklist items they added or ticked. Only untouched
suggestions are replaced.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.aiChat.services.event_service import visible_events
from apps.aiChat.services.geo import distance_km, valid_coordinates
from apps.journeys.models import (
    JourneyChecklistItem,
    JourneyDay,
    JourneyItem,
    JourneyPlan,
)
from apps.temples.models import Temple

LANGUAGES = ("en", "hi", "mr")

# Suggested split of the pilgrim's own budget. A planning assumption, not
# price data: KumbhaPath has no verified fares or room rates.
BUDGET_SPLIT = (
    ("travel", 35),
    ("stay", 30),
    ("food", 15),
    ("local_transport", 10),
    ("offerings_misc", 10),
)

_T = {
    "en": {
        "day_arrival": "Arrival in Nashik",
        "day_nashik": "Nashik temples and Panchavati",
        "day_trimbak": "Trimbakeshwar",
        "day_bathing": "Sacred bathing day",
        "day_akhadas": "Akhadas and spiritual learning",
        "day_sightseeing": "Around Nashik",
        "day_rest": "Rest and free time",
        "day_departure": "Departure",
        "day_single": "Day visit",
        "arrive": "Arrive in Nashik",
        "arrive_train": "Simhastha trains are planned to use Nashik Road, Devlali, Odha, Kherwadi and Kasbe Sukene stations. Check which station your train uses and how you'll get to your stay.",
        "arrive_bus": "Check the MSRTC stand on your ticket; extra Mela services and temporary stands are announced by the authorities.",
        "arrive_flight": "Plan the road or rail journey from the airport. Allow generous time — travel takes much longer during the Mela.",
        "arrive_private": "Follow official traffic advisories; vehicles are often restricted near the ghats and parking is in designated areas.",
        "arrive_undecided": "Allow generous time — travel takes much longer during the Mela.",
        "checkin": "Check in and rest",
        "checkin_details": "Rest after the journey. Keep your stay's address saved on your phone and on paper.",
        "ramkund_aarti": "Evening aarti at Ramkund",
        "ramkund_aarti_details": "The Godavari aarti at Ramkund is traditionally held in the evening. Timings vary — confirm locally.",
        "temple_visit": "Darshan at {name}",
        "temple_details": "Queues can be long; go early and keep water with you.",
        "meal_rest": "Meal and rest",
        "meal_rest_details": "Eat at a busy, clean place and rest before the afternoon.",
        "panchavati": "Panchavati area",
        "panchavati_details": "Walk around the Panchavati area near Ramkund at an easy pace.",
        "to_trimbak": "Travel to Trimbakeshwar",
        "to_trimbak_details": "Trimbakeshwar is a separate town near Nashik. Leave early and allow plenty of extra time on crowded days.",
        "kushavarta": "Kushavarta Kund",
        "kushavarta_details": "The sacred tank in Trimbak, regarded as the source of the Godavari.",
        "back_nashik": "Return to your stay",
        "back_nashik_details": "Start back before dark; transport fills up in the evening.",
        "bathing": "{name}",
        "bathing_details": "Very large crowds are expected. Go early, keep your group together, and follow police and volunteer directions — bathing ghats and routes are allotted by the authority.",
        "bathing_rest": "Rest after the bath",
        "bathing_rest_details": "Keep the rest of the day light; avoid crowded routes.",
        "event": "{name}",
        "event_details": "Listed in the KumbhaPath events schedule. Confirm timing and place before going.",
        "akhadas": "Visit akhada camps",
        "akhadas_details": "Akhada camps host pravachans and darshan of sadhus. Camp locations are announced by the Kumbh authority.",
        "pravachan": "Pravachan or kirtan",
        "pravachan_details": "Join a discourse or kirtan at a camp or temple that welcomes visitors.",
        "sightseeing": "Explore Nashik",
        "sightseeing_details": "Choose places that suit your group; keep travel short on busy days.",
        "rest_day": "Free time",
        "rest_day_details": "Rest, revisit a favourite place or spend time with family.",
        "pack": "Pack and check out",
        "pack_details": "Check rooms for chargers, documents and medicines.",
        "leave": "Leave for your onward journey",
        "leave_details": "Leave early and keep a large time buffer — roads and stations are very busy during the Mela.",
        "senior_rest": "Rest break",
        "senior_rest_details": "A short rest in the shade for senior travellers.",
        "pace_senior": "Senior travellers are in your group: keep a slower pace, carry water and medicines, and plan seated rest.",
        "pace_access": "Plan step-free routes and wheelchair or other assistance in advance where possible.",
        "pace_children": "Agree on a meeting point and keep a contact card in each child's pocket.",
        "check_id": "Photo ID for every traveller",
        "check_tickets": "Tickets and booking confirmations (printed or saved offline)",
        "check_medicines": "Regular medicines and a small first-aid kit",
        "check_water": "Water bottle and ORS",
        "check_footwear": "Comfortable footwear for long walks",
        "check_clothes": "Light clothes and rain protection (July–September is monsoon season)",
        "check_power": "Phone, charger and power bank",
        "check_offline": "Save this itinerary offline (use Share)",
        "check_advisory": "Check official traffic and train advisories the day before travel",
        "check_meeting": "Agree on a meeting point if anyone gets separated",
        "check_numbers": "Save emergency number 112 and the Kumbh authority helpline",
        "check_child_card": "A card with your phone number in each child's pocket",
        "check_senior_meds": "A list of each senior traveller's medicines and doctor's number",
        "check_assistance": "Arrange wheelchair or assistance with your train, bus or stay",
        "check_bath_clothes": "Change of clothes and a towel for the sacred bath",
        "check_diet": "Snacks that suit your dietary needs",
        "budget_assumption": "A suggested way to divide your own budget — not a price estimate. KumbhaPath has no verified fares or room rates; prices rise sharply around bathing days.",
        "travel": "Travel to and from Nashik",
        "stay": "Stay",
        "food": "Food",
        "local_transport": "Local transport",
        "offerings_misc": "Offerings and other",
    },
    "hi": {
        "day_arrival": "नाशिक आगमन",
        "day_nashik": "नाशिक के मंदिर और पंचवटी",
        "day_trimbak": "त्र्यंबकेश्वर",
        "day_bathing": "पवित्र स्नान का दिन",
        "day_akhadas": "अखाड़े और आध्यात्मिक ज्ञान",
        "day_sightseeing": "नाशिक दर्शन",
        "day_rest": "विश्राम और खाली समय",
        "day_departure": "प्रस्थान",
        "day_single": "एक दिन की यात्रा",
        "arrive": "नाशिक पहुँचें",
        "arrive_train": "सिंहस्थ ट्रेनें नाशिक रोड, देवलाली, ओढा, खेरवाडी और कसबे सुकेणे स्टेशनों से चलाने की योजना है। अपनी ट्रेन का स्टेशन और ठहरने की जगह तक पहुँचने का तरीका जाँचें।",
        "arrive_bus": "टिकट पर MSRTC स्टैंड जाँचें; अतिरिक्त मेला सेवाएँ और अस्थायी स्टैंड अधिकारी घोषित करते हैं।",
        "arrive_flight": "हवाई अड्डे से आगे की सड़क या रेल यात्रा की योजना बनाएँ। पर्याप्त समय रखें — मेले में यात्रा बहुत अधिक समय लेती है।",
        "arrive_private": "आधिकारिक यातायात सूचनाओं का पालन करें; घाटों के पास वाहन अक्सर प्रतिबंधित रहते हैं और पार्किंग तय स्थानों पर होती है।",
        "arrive_undecided": "पर्याप्त समय रखें — मेले में यात्रा बहुत अधिक समय लेती है।",
        "checkin": "चेक-इन और विश्राम",
        "checkin_details": "यात्रा के बाद आराम करें। ठहरने का पता फ़ोन और कागज़ दोनों पर रखें।",
        "ramkund_aarti": "रामकुंड पर संध्या आरती",
        "ramkund_aarti_details": "रामकुंड पर गोदावरी आरती परंपरागत रूप से शाम को होती है। समय बदल सकता है — स्थानीय रूप से पुष्टि करें।",
        "temple_visit": "{name} में दर्शन",
        "temple_details": "कतारें लंबी हो सकती हैं; जल्दी जाएँ और पानी साथ रखें।",
        "meal_rest": "भोजन और विश्राम",
        "meal_rest_details": "भीड़ वाली, साफ़ जगह पर भोजन करें और दोपहर से पहले आराम करें।",
        "panchavati": "पंचवटी क्षेत्र",
        "panchavati_details": "रामकुंड के पास पंचवटी क्षेत्र में आराम से घूमें।",
        "to_trimbak": "त्र्यंबकेश्वर की यात्रा",
        "to_trimbak_details": "त्र्यंबकेश्वर नाशिक के पास एक अलग शहर है। जल्दी निकलें और भीड़ वाले दिनों में बहुत अतिरिक्त समय रखें।",
        "kushavarta": "कुशावर्त कुंड",
        "kushavarta_details": "त्र्यंबक का पवित्र कुंड, जिसे गोदावरी का उद्गम माना जाता है।",
        "back_nashik": "ठहरने की जगह पर वापसी",
        "back_nashik_details": "अंधेरा होने से पहले लौटना शुरू करें; शाम को वाहन भर जाते हैं।",
        "bathing": "{name}",
        "bathing_details": "बहुत भारी भीड़ की संभावना है। जल्दी जाएँ, अपने समूह को साथ रखें और पुलिस व स्वयंसेवकों के निर्देशों का पालन करें — स्नान घाट और मार्ग प्राधिकरण तय करता है।",
        "bathing_rest": "स्नान के बाद विश्राम",
        "bathing_rest_details": "बाकी दिन हल्का रखें; भीड़ वाले रास्तों से बचें।",
        "event": "{name}",
        "event_details": "KumbhaPath कार्यक्रम सूची में दर्ज। जाने से पहले समय और स्थान की पुष्टि करें।",
        "akhadas": "अखाड़ा शिविरों का दर्शन",
        "akhadas_details": "अखाड़ा शिविरों में प्रवचन और साधुओं के दर्शन होते हैं। शिविरों के स्थान कुंभ प्राधिकरण घोषित करता है।",
        "pravachan": "प्रवचन या कीर्तन",
        "pravachan_details": "ऐसे शिविर या मंदिर में प्रवचन या कीर्तन में शामिल हों जहाँ आगंतुकों का स्वागत है।",
        "sightseeing": "नाशिक घूमें",
        "sightseeing_details": "अपने समूह के अनुसार स्थान चुनें; भीड़ वाले दिनों में यात्रा छोटी रखें।",
        "rest_day": "खाली समय",
        "rest_day_details": "आराम करें, पसंदीदा स्थान फिर देखें या परिवार के साथ समय बिताएँ।",
        "pack": "सामान बाँधें और चेक-आउट करें",
        "pack_details": "चार्जर, दस्तावेज़ और दवाइयाँ कमरे में न छूटें, जाँच लें।",
        "leave": "आगे की यात्रा के लिए निकलें",
        "leave_details": "जल्दी निकलें और बहुत अतिरिक्त समय रखें — मेले में सड़कें और स्टेशन बहुत व्यस्त रहते हैं।",
        "senior_rest": "विश्राम",
        "senior_rest_details": "वरिष्ठ यात्रियों के लिए छाँव में थोड़ा आराम।",
        "pace_senior": "आपके समूह में वरिष्ठ यात्री हैं: धीमी गति रखें, पानी और दवाइयाँ साथ रखें और बैठकर आराम की योजना बनाएँ।",
        "pace_access": "जहाँ संभव हो, बिना सीढ़ी वाले रास्ते और व्हीलचेयर या अन्य सहायता पहले से तय करें।",
        "pace_children": "मिलने की जगह तय करें और हर बच्चे की जेब में संपर्क कार्ड रखें।",
        "check_id": "हर यात्री का फ़ोटो पहचान पत्र",
        "check_tickets": "टिकट और बुकिंग की पुष्टि (छपी हुई या ऑफ़लाइन सहेजी)",
        "check_medicines": "नियमित दवाइयाँ और छोटा प्राथमिक उपचार किट",
        "check_water": "पानी की बोतल और ORS",
        "check_footwear": "लंबी दूरी चलने के लिए आरामदायक जूते-चप्पल",
        "check_clothes": "हल्के कपड़े और बारिश से बचाव (जुलाई–सितंबर मानसून है)",
        "check_power": "फ़ोन, चार्जर और पावर बैंक",
        "check_offline": "यह यात्रा योजना ऑफ़लाइन सहेजें (शेयर का उपयोग करें)",
        "check_advisory": "यात्रा से एक दिन पहले आधिकारिक यातायात और ट्रेन सूचनाएँ जाँचें",
        "check_meeting": "कोई बिछड़ जाए तो मिलने की जगह तय करें",
        "check_numbers": "आपातकालीन नंबर 112 और कुंभ प्राधिकरण हेल्पलाइन सहेजें",
        "check_child_card": "हर बच्चे की जेब में आपके फ़ोन नंबर वाला कार्ड",
        "check_senior_meds": "हर वरिष्ठ यात्री की दवाइयों और डॉक्टर के नंबर की सूची",
        "check_assistance": "ट्रेन, बस या ठहरने की जगह पर व्हीलचेयर या सहायता तय करें",
        "check_bath_clothes": "पवित्र स्नान के लिए बदलने के कपड़े और तौलिया",
        "check_diet": "आपकी आहार आवश्यकता के अनुसार नाश्ता",
        "budget_assumption": "अपने बजट को बाँटने का सुझाया गया तरीका — कीमत का अनुमान नहीं। KumbhaPath के पास सत्यापित किराए या कमरों की दरें नहीं हैं; स्नान के दिनों के आसपास कीमतें बहुत बढ़ जाती हैं।",
        "travel": "नाशिक आने-जाने का किराया",
        "stay": "ठहराव",
        "food": "भोजन",
        "local_transport": "स्थानीय यात्रा",
        "offerings_misc": "चढ़ावा और अन्य",
    },
    "mr": {
        "day_arrival": "नाशिक आगमन",
        "day_nashik": "नाशिकची मंदिरे आणि पंचवटी",
        "day_trimbak": "त्र्यंबकेश्वर",
        "day_bathing": "पवित्र स्नानाचा दिवस",
        "day_akhadas": "आखाडे आणि आध्यात्मिक ज्ञान",
        "day_sightseeing": "नाशिक दर्शन",
        "day_rest": "विश्रांती आणि मोकळा वेळ",
        "day_departure": "परतीचा प्रवास",
        "day_single": "एक दिवसाची भेट",
        "arrive": "नाशिकला पोहोचा",
        "arrive_train": "सिंहस्थ गाड्या नाशिक रोड, देवळाली, ओढा, खेरवाडी आणि कसबे सुकेणे स्थानकांवरून चालवण्याचे नियोजन आहे. तुमची गाडी कोणत्या स्थानकावर येते आणि निवासापर्यंत कसे जाल ते तपासा.",
        "arrive_bus": "तिकिटावरील MSRTC स्थानक तपासा; जादा मेळा सेवा व तात्पुरती स्थानके अधिकारी जाहीर करतात.",
        "arrive_flight": "विमानतळावरून पुढील रस्ता किंवा रेल्वे प्रवासाचे नियोजन करा. पुरेसा वेळ ठेवा — मेळ्यात प्रवासाला खूप जास्त वेळ लागतो.",
        "arrive_private": "अधिकृत वाहतूक सूचनांचे पालन करा; घाटांजवळ वाहनांवर अनेकदा निर्बंध असतात आणि पार्किंग ठरावीक ठिकाणी असते.",
        "arrive_undecided": "पुरेसा वेळ ठेवा — मेळ्यात प्रवासाला खूप जास्त वेळ लागतो.",
        "checkin": "चेक-इन आणि विश्रांती",
        "checkin_details": "प्रवासानंतर विश्रांती घ्या. निवासाचा पत्ता फोनवर आणि कागदावर ठेवा.",
        "ramkund_aarti": "रामकुंडावरील सायंकाळची आरती",
        "ramkund_aarti_details": "रामकुंडावर गोदावरीची आरती परंपरेने सायंकाळी होते. वेळ बदलू शकते — स्थानिक पातळीवर खात्री करा.",
        "temple_visit": "{name} येथे दर्शन",
        "temple_details": "रांगा लांब असू शकतात; लवकर जा आणि पाणी सोबत ठेवा.",
        "meal_rest": "जेवण आणि विश्रांती",
        "meal_rest_details": "गर्दीच्या, स्वच्छ ठिकाणी जेवा आणि दुपारपूर्वी विश्रांती घ्या.",
        "panchavati": "पंचवटी परिसर",
        "panchavati_details": "रामकुंडाजवळील पंचवटी परिसरात निवांतपणे फिरा.",
        "to_trimbak": "त्र्यंबकेश्वरला प्रवास",
        "to_trimbak_details": "त्र्यंबकेश्वर हे नाशिकजवळचे वेगळे गाव आहे. लवकर निघा आणि गर्दीच्या दिवशी भरपूर जादा वेळ ठेवा.",
        "kushavarta": "कुशावर्त कुंड",
        "kushavarta_details": "त्र्यंबकमधील पवित्र कुंड, ज्याला गोदावरीचे उगमस्थान मानले जाते.",
        "back_nashik": "निवासाकडे परत",
        "back_nashik_details": "अंधार पडण्यापूर्वी परत निघा; सायंकाळी वाहने भरून जातात.",
        "bathing": "{name}",
        "bathing_details": "खूप मोठी गर्दी अपेक्षित आहे. लवकर जा, तुमचा गट एकत्र ठेवा आणि पोलीस व स्वयंसेवकांच्या सूचनांचे पालन करा — स्नानाचे घाट आणि मार्ग प्राधिकरण ठरवते.",
        "bathing_rest": "स्नानानंतर विश्रांती",
        "bathing_rest_details": "उरलेला दिवस हलका ठेवा; गर्दीचे मार्ग टाळा.",
        "event": "{name}",
        "event_details": "KumbhaPath कार्यक्रम यादीत नोंद. जाण्यापूर्वी वेळ आणि ठिकाणाची खात्री करा.",
        "akhadas": "आखाडा शिबिरांना भेट",
        "akhadas_details": "आखाडा शिबिरांत प्रवचने आणि साधूंचे दर्शन होते. शिबिरांची ठिकाणे कुंभ प्राधिकरण जाहीर करते.",
        "pravachan": "प्रवचन किंवा कीर्तन",
        "pravachan_details": "अभ्यागतांचे स्वागत करणाऱ्या शिबिरात किंवा मंदिरात प्रवचन किंवा कीर्तनाला जा.",
        "sightseeing": "नाशिक फिरा",
        "sightseeing_details": "तुमच्या गटाला योग्य अशी ठिकाणे निवडा; गर्दीच्या दिवशी प्रवास कमी ठेवा.",
        "rest_day": "मोकळा वेळ",
        "rest_day_details": "विश्रांती घ्या, आवडते ठिकाण पुन्हा पहा किंवा कुटुंबासोबत वेळ घालवा.",
        "pack": "सामान भरा आणि चेक-आउट करा",
        "pack_details": "चार्जर, कागदपत्रे आणि औषधे खोलीत राहिली नाहीत ना ते तपासा.",
        "leave": "पुढील प्रवासासाठी निघा",
        "leave_details": "लवकर निघा आणि भरपूर जादा वेळ ठेवा — मेळ्यात रस्ते आणि स्थानके खूप गर्दीची असतात.",
        "senior_rest": "विश्रांती",
        "senior_rest_details": "ज्येष्ठ प्रवाशांसाठी सावलीत थोडी विश्रांती.",
        "pace_senior": "तुमच्या गटात ज्येष्ठ प्रवासी आहेत: सावकाश चाला, पाणी व औषधे सोबत ठेवा आणि बसून विश्रांतीचे नियोजन करा.",
        "pace_access": "शक्य तिथे पायऱ्यांशिवायचे मार्ग आणि व्हीलचेअर किंवा इतर मदत आधीच ठरवा.",
        "pace_children": "भेटण्याचे ठिकाण ठरवा आणि प्रत्येक मुलाच्या खिशात संपर्क कार्ड ठेवा.",
        "check_id": "प्रत्येक प्रवाशाचे फोटो ओळखपत्र",
        "check_tickets": "तिकिटे आणि आरक्षणाची पुष्टी (छापलेली किंवा ऑफलाइन जतन केलेली)",
        "check_medicines": "नेहमीची औषधे आणि छोटी प्रथमोपचार पेटी",
        "check_water": "पाण्याची बाटली आणि ORS",
        "check_footwear": "लांब चालण्यासाठी आरामदायक पादत्राणे",
        "check_clothes": "हलके कपडे आणि पावसापासून संरक्षण (जुलै–सप्टेंबर पावसाळा असतो)",
        "check_power": "फोन, चार्जर आणि पॉवर बँक",
        "check_offline": "हा प्रवास आराखडा ऑफलाइन जतन करा (शेअर वापरा)",
        "check_advisory": "प्रवासाच्या आदल्या दिवशी अधिकृत वाहतूक व रेल्वे सूचना तपासा",
        "check_meeting": "कोणी हरवल्यास भेटण्याचे ठिकाण ठरवा",
        "check_numbers": "आणीबाणी क्रमांक 112 आणि कुंभ प्राधिकरणाची हेल्पलाइन जतन करा",
        "check_child_card": "प्रत्येक मुलाच्या खिशात तुमचा फोन नंबर असलेले कार्ड",
        "check_senior_meds": "प्रत्येक ज्येष्ठ प्रवाशाच्या औषधांची व डॉक्टरच्या क्रमांकाची यादी",
        "check_assistance": "रेल्वे, बस किंवा निवासाकडे व्हीलचेअर किंवा मदत ठरवा",
        "check_bath_clothes": "पवित्र स्नानासाठी बदलायचे कपडे आणि टॉवेल",
        "check_diet": "तुमच्या आहाराच्या गरजेनुसार खाऊ",
        "budget_assumption": "तुमचे स्वतःचे बजेट विभागण्याची सुचवलेली पद्धत — किमतीचा अंदाज नाही. KumbhaPath कडे पडताळलेली भाडी किंवा खोल्यांचे दर नाहीत; स्नानाच्या दिवसांच्या आसपास किमती खूप वाढतात.",
        "travel": "नाशिकला येण्या-जाण्याचे भाडे",
        "stay": "निवास",
        "food": "जेवण",
        "local_transport": "स्थानिक प्रवास",
        "offerings_misc": "अर्पण आणि इतर",
    },
}


def t(language: str, key: str, **params) -> str:
    template = _T.get(language, _T["en"]).get(key) or _T["en"][key]
    return template.format(**params) if params else template


def _language(plan: JourneyPlan) -> str:
    return plan.language if plan.language in LANGUAGES else "en"


def recommended_days(plan: JourneyPlan) -> int:
    """A comfortable length: Nashik, Trimbakeshwar and a buffer day,
    plus a day for akhadas/learning and a slower pace for seniors."""
    days = 3
    interests = set(plan.interests or [])
    if interests & {"akhadas", "learning"}:
        days += 1
    if plan.seniors or plan.needs_accessibility:
        days += 1
    return min(days, JourneyPlan.MAX_DAYS)


def day_count(plan: JourneyPlan) -> int:
    if plan.arrival_date and plan.departure_date:
        span = (plan.departure_date - plan.arrival_date).days + 1
        return max(1, min(span, JourneyPlan.MAX_DAYS))
    if plan.duration_days:
        return max(1, min(plan.duration_days, JourneyPlan.MAX_DAYS))
    return recommended_days(plan)


def budget_plan(plan: JourneyPlan) -> dict | None:
    if plan.budget_amount is None:
        return None
    total = plan.budget_amount
    if plan.budget_basis == JourneyPlan.BudgetBasis.PER_PERSON:
        total = total * plan.travellers
    language = _language(plan)
    lines = []
    for category, percent in BUDGET_SPLIT:
        amount = (total * Decimal(percent) / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP,
        )
        lines.append({
            "category": category,
            "label": t(language, category),
            "percent": percent,
            "amount": str(amount),
        })
    return {
        "total": str(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "per_person": str((total / max(plan.travellers, 1)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "basis": plan.budget_basis,
        "currency": "INR",
        "assumption": t(language, "budget_assumption"),
        "is_estimate": False,
        "lines": lines,
    }


# ---- itinerary ----------------------------------------------------------------

# Ramkund, the centre of the Nashik bathing area (Panchavati).
_RAMKUND = (19.9975, 73.7910)


def _temples():
    """Trimbakeshwar, and Nashik temples nearest Ramkund first, so a day's
    visits stay within the Panchavati area."""
    temples = list(Temple.objects.filter(is_active=True, del_flag=0).order_by("name"))
    trimbak = next((x for x in temples if "trimbak" in x.name.lower()), None)
    nashik = [x for x in temples if x is not trimbak]

    def from_ramkund(temple):
        if not valid_coordinates(temple.latitude, temple.longitude):
            return float("inf")
        return distance_km(_RAMKUND[0], _RAMKUND[1], temple.latitude, temple.longitude)

    nashik.sort(key=from_ramkund)
    return trimbak, nashik


def _events_by_date(start, days):
    if not start:
        return {}
    end = start + timedelta(days=days - 1)
    found = {}
    for event in visible_events().filter(event_date__gte=start, event_date__lte=end).order_by("start_time"):
        found.setdefault(event.event_date, []).append(event)
    return found


def _themes(plan: JourneyPlan, middle_days: int) -> list[str]:
    interests = set(plan.interests or [])
    everything = not interests
    queue = []
    if everything or interests & {"temples", "bathing"}:
        queue += ["nashik", "trimbak"]
    if interests & {"akhadas", "learning"}:
        queue.append("akhadas")
    if "sightseeing" in interests:
        queue.append("sightseeing")
    if not queue:
        queue = ["nashik"]
    # Seniors or accessibility needs: a rest day after every two busy days.
    if (plan.seniors or plan.needs_accessibility) and middle_days >= 4:
        queue.insert(2, "rest")
    return queue


class _DayBuilder:
    def __init__(self, plan, language, trimbak, nashik_temples):
        self.plan = plan
        self.language = language
        self.trimbak = trimbak
        self.nashik_temples = nashik_temples
        self.slow = bool(plan.seniors or plan.needs_accessibility)
        self.items: list[dict] = []

    def add(self, period, kind, key, *, temple=None, event=None, name=None, details_key=None):
        params = {"name": name} if name else {}
        details_key = details_key or f"{key}_details"
        self.items.append({
            "period": period,
            "kind": kind,
            "title": t(self.language, key, **params)[:150],
            "details": t(self.language, details_key, **params) if details_key in _T["en"] else "",
            "temple": temple,
            "event": event,
        })

    def rest_if_slow(self, period):
        if self.slow:
            self.add(period, JourneyItem.Kind.REST, "senior_rest")

    def arrival(self, evening_ghat=True):
        mode = self.plan.transport_mode or "undecided"
        self.add("morning", JourneyItem.Kind.TRAVEL, "arrive", details_key=f"arrive_{mode}")
        self.add("afternoon", JourneyItem.Kind.REST, "checkin")
        if evening_ghat:
            self.add("evening", JourneyItem.Kind.GHAT, "ramkund_aarti")

    def nashik(self):
        temples = self.nashik_temples[:3]
        periods = ["morning", "morning", "afternoon"]
        for temple, period in zip(temples[:2], periods):
            self.add(period, JourneyItem.Kind.TEMPLE, "temple_visit", temple=temple, name=temple.name, details_key="temple_details")
        self.add("afternoon", JourneyItem.Kind.MEAL, "meal_rest")
        self.rest_if_slow("afternoon")
        if len(temples) > 2:
            self.add("afternoon", JourneyItem.Kind.TEMPLE, "temple_visit", temple=temples[2], name=temples[2].name, details_key="temple_details")
        self.add("evening", JourneyItem.Kind.SIGHTSEEING, "panchavati")

    def trimbak_day(self):
        self.add("early_morning", JourneyItem.Kind.TRAVEL, "to_trimbak")
        if self.trimbak:
            self.add("morning", JourneyItem.Kind.TEMPLE, "temple_visit", temple=self.trimbak, name=self.trimbak.name, details_key="temple_details")
        self.add("morning", JourneyItem.Kind.GHAT, "kushavarta")
        self.add("afternoon", JourneyItem.Kind.MEAL, "meal_rest")
        self.rest_if_slow("afternoon")
        self.add("evening", JourneyItem.Kind.TRAVEL, "back_nashik")

    def bathing(self, events):
        for event in events:
            self.add("early_morning", JourneyItem.Kind.BATHING, "bathing", event=event, name=event.event_name, details_key="bathing_details")
        self.add("afternoon", JourneyItem.Kind.REST, "bathing_rest")

    def akhadas(self):
        self.add("morning", JourneyItem.Kind.AKHADA, "akhadas")
        self.add("afternoon", JourneyItem.Kind.MEAL, "meal_rest")
        self.add("evening", JourneyItem.Kind.EVENT, "pravachan")

    def sightseeing(self):
        self.add("morning", JourneyItem.Kind.SIGHTSEEING, "sightseeing")
        self.add("afternoon", JourneyItem.Kind.MEAL, "meal_rest")

    def rest(self):
        self.add("anytime", JourneyItem.Kind.REST, "rest_day")

    def departure(self):
        self.add("morning", JourneyItem.Kind.TRAVEL, "pack")
        self.add("afternoon", JourneyItem.Kind.TRAVEL, "leave")

    def other_events(self, events):
        for event in events:
            self.add("evening", JourneyItem.Kind.EVENT, "event", event=event, name=event.event_name, details_key="event_details")


def _plan_days(plan: JourneyPlan) -> list[dict]:
    """[{date, title, items:[...]}] without saving anything."""
    language = _language(plan)
    count = day_count(plan)
    dates = [plan.arrival_date + timedelta(days=i) if plan.arrival_date else None for i in range(count)]
    events = _events_by_date(plan.arrival_date, count)
    trimbak, nashik_temples = _temples()
    themes = _themes(plan, max(0, count - 2))
    days = []

    for index in range(count):
        date = dates[index]
        todays = events.get(date, [])
        bathing = [e for e in todays if e.event_category == "SNAN"]
        others = [e for e in todays if e.event_category != "SNAN"]
        builder = _DayBuilder(plan, language, trimbak, nashik_temples)
        first, last = index == 0, index == count - 1

        if count == 1:
            title = "day_single"
            builder.arrival(evening_ghat=False)
            if bathing:
                builder.bathing(bathing)
            else:
                builder.add("afternoon", JourneyItem.Kind.GHAT, "ramkund_aarti")
            builder.items = [i for i in builder.items if i["kind"] != JourneyItem.Kind.REST]
            builder.departure()
        elif first:
            title = "day_arrival"
            builder.arrival(evening_ghat=not bathing)
            if bathing:
                builder.bathing(bathing)
        elif last:
            title = "day_departure"
            builder.departure()
        elif bathing:
            title = "day_bathing"
            builder.bathing(bathing)
        else:
            theme = themes.pop(0) if themes else "rest"
            title = {
                "nashik": "day_nashik", "trimbak": "day_trimbak", "akhadas": "day_akhadas",
                "sightseeing": "day_sightseeing", "rest": "day_rest",
            }[theme]
            {
                "nashik": builder.nashik, "trimbak": builder.trimbak_day, "akhadas": builder.akhadas,
                "sightseeing": builder.sightseeing, "rest": builder.rest,
            }[theme]()
        if not (last and count > 1):  # nothing after "leave" on departure day
            builder.other_events(others)
        days.append({"date": date, "title": t(language, title), "items": builder.items})

    # Pace notes on the first day for groups that need them.
    notes = []
    if plan.seniors:
        notes.append("pace_senior")
    if plan.needs_accessibility:
        notes.append("pace_access")
    if plan.children:
        notes.append("pace_children")
    for key in notes:
        days[0]["items"].insert(0, {
            "period": "anytime", "kind": JourneyItem.Kind.NOTE, "title": t(language, key)[:150],
            "details": "", "temple": None, "event": None,
        })
    return days


def _checklist(plan: JourneyPlan) -> list[tuple[str, str]]:
    C = JourneyChecklistItem.Category
    items = [
        (C.DOCUMENTS, "check_id"), (C.DOCUMENTS, "check_tickets"),
        (C.HEALTH, "check_medicines"), (C.HEALTH, "check_water"),
        (C.PACKING, "check_footwear"), (C.PACKING, "check_clothes"), (C.PACKING, "check_power"),
        (C.TRAVEL, "check_offline"), (C.TRAVEL, "check_advisory"),
        (C.FAMILY, "check_meeting"), (C.FAMILY, "check_numbers"),
    ]
    if plan.children:
        items.append((C.FAMILY, "check_child_card"))
    if plan.seniors:
        items.append((C.HEALTH, "check_senior_meds"))
    if plan.needs_accessibility:
        items.append((C.TRAVEL, "check_assistance"))
    if not plan.interests or "bathing" in (plan.interests or []):
        items.append((C.PACKING, "check_bath_clothes"))
    if plan.dietary_notes.strip():
        items.append((C.HEALTH, "check_diet"))
    language = _language(plan)
    return [(category, t(language, key)) for category, key in items]


@transaction.atomic
def generate(plan: JourneyPlan) -> dict:
    """(Re)build suggestions. Returns counts of what was kept and added."""
    plan = JourneyPlan.objects.select_for_update().get(pk=plan.pk)
    kept = list(
        JourneyItem.objects.filter(day__journey=plan)
        .filter(Q(source=JourneyItem.Source.USER) | Q(is_edited=True))
        .select_related("day")
        .order_by("day__day_number", "position")
    )
    kept_by_day: dict[int, list[JourneyItem]] = {}
    for item in kept:
        kept_by_day.setdefault(item.day.day_number, []).append(item)

    planned = _plan_days(plan)
    # Detach kept items, then rebuild the days.
    JourneyItem.objects.filter(day__journey=plan).exclude(pk__in=[i.pk for i in kept]).delete()
    old_days = {d.day_number: d for d in plan.days.all()}

    new_days = []
    for number, spec in enumerate(planned, start=1):
        day = old_days.pop(number, None) or JourneyDay(journey=plan, day_number=number)
        day.date = spec["date"]
        day.title = spec["title"][:120]
        day.save()
        new_days.append(day)

    added = 0
    for day, spec in zip(new_days, planned):
        position = 0
        for item in spec["items"]:
            JourneyItem.objects.create(
                day=day, position=position, period=item["period"], kind=item["kind"],
                title=item["title"], details=item["details"], temple=item["temple"],
                event=item["event"], source=JourneyItem.Source.SUGGESTED,
            )
            position += 1
            added += 1
        for item in kept_by_day.pop(day.day_number, []):
            item.day, item.position = day, position
            item.save(update_fields=["day", "position", "updated_at"])
            position += 1

    # Kept items from days that no longer exist move to the last day.
    last = new_days[-1]
    position = last.items.count()
    for items in kept_by_day.values():
        for item in items:
            item.day, item.position = last, position
            item.save(update_fields=["day", "position", "updated_at"])
            position += 1
    for day in old_days.values():
        day.delete()

    # Checklist: keep user items and ticked items; refresh the rest.
    plan.checklist.filter(source=JourneyItem.Source.SUGGESTED, is_done=False).delete()
    existing = set(plan.checklist.values_list("text", flat=True))
    position = plan.checklist.count()
    for category, text_value in _checklist(plan):
        if text_value not in existing:
            JourneyChecklistItem.objects.create(
                journey=plan, text=text_value, category=category, position=position,
                source=JourneyItem.Source.SUGGESTED,
            )
            position += 1

    plan.itinerary_generated_at = timezone.now()
    if plan.status == JourneyPlan.Status.DRAFT:
        plan.status = JourneyPlan.Status.PLANNED
    plan.save(update_fields=["itinerary_generated_at", "status", "updated_at"])
    return {"days": len(new_days), "suggested_items": added, "kept_items": len(kept)}
