"""
Starting news, loaded by `manage.py seed_kumbh_content`. Real reports, summarized
in our own words from the articles linked, checked 2026-10-30. Publishers' text
and images aren't reproduced. Nothing is marked official: every report here comes
from a news organization, not from the authority itself.
"""

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

CATEGORIES = [
    ("official", "Official Announcements", "आधिकारिक घोषणाएँ", "अधिकृत घोषणा"),
    ("preparations", "Kumbh Preparations", "कुंभ की तैयारी", "कुंभाची तयारी"),
    ("dates", "Important Dates", "महत्वपूर्ण तिथियाँ", "महत्त्वाच्या तारखा"),
    ("transport", "Transport & Travel", "परिवहन और यात्रा", "वाहतूक आणि प्रवास"),
    ("infrastructure", "Infrastructure", "बुनियादी ढाँचा", "पायाभूत सुविधा"),
    ("safety", "Safety & Advisories", "सुरक्षा और परामर्श", "सुरक्षा आणि सूचना"),
    ("spiritual", "Akhadas & Spiritual Events", "अखाड़े और धार्मिक आयोजन", "आखाडे आणि धार्मिक कार्यक्रम"),
    ("heritage", "Temples & Heritage", "मंदिर और विरासत", "मंदिरे आणि वारसा"),
    ("facilities", "Pilgrim Facilities", "श्रद्धालु सुविधाएँ", "भाविक सुविधा"),
    ("environment", "Environment & Cleanliness", "पर्यावरण और स्वच्छता", "पर्यावरण आणि स्वच्छता"),
]

SOURCES = [
    {
        "name": "Press Information Bureau", "slug": "pib", "publisher_type": "official",
        "website_url": "https://www.pib.gov.in/", "adapter": "rss", "is_active": True,
        "feed_url": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=2&Regid=3&reg=48",
        "terms_notes": "Government of India releases. Feed listed at pib.gov.in/ViewRss.aspx. It has no dates on items, so check it after the first sync.",
    },
    {
        "name": "Nashik–Trimbakeshwar Kumbh Mela Authority", "slug": "ntkma", "publisher_type": "official",
        "website_url": "https://www.nashikkumbha2027.com/",
        "terms_notes": "No feed or API found. Editors add notices by hand.",
    },
    {
        "name": "Divisional Commissioner, Nashik", "slug": "divcom-nashik", "publisher_type": "official",
        "website_url": "https://divcomnashik.maharashtra.gov.in/", "terms_notes": "The /feed/ address returns an error. Editors add notices by hand.",
    },
    {
        "name": "Free Press Journal", "slug": "free-press-journal", "publisher_type": "news",
        "website_url": "https://www.freepressjournal.in/", "adapter": "rss",
        "feed_url": "https://www.freepressjournal.in/stories.rss",
        "terms_notes": "Public feed, but reuse terms not confirmed. Keep off until checked.",
    },
    {
        "name": "Sakal", "slug": "sakal", "publisher_type": "news", "language": "mr",
        "website_url": "https://www.esakal.com/", "adapter": "rss", "feed_url": "https://esakal.com/feed",
        "terms_notes": "Public feed, but reuse terms not confirmed. Keep off until checked.",
    },
    {"name": "Navbharat Live", "slug": "navbharat-live", "publisher_type": "news", "language": "hi", "website_url": "https://navbharatlive.com/"},
    {"name": "PTI via ThePrint", "slug": "pti-theprint", "publisher_type": "news", "website_url": "https://theprint.in/"},
]

STORIES = [
    {
        "publisher": "sakal", "category": "spiritual", "featured": True,
        "url": "https://www.esakal.com/uttar-maharashtra/nashik/kumbh-mela-2027-flag-hoisting-nashik",
        "published_at": datetime(2026, 10, 30, 18, 48, tzinfo=IST),
        "en": ("Simhastha opens with twin flag hoistings at Ramtirth and Trimbakeshwar",
               "The flag hoisting is scheduled for 12:02 pm on Saturday, 31 October. Sakal reports that President Droupadi Murmu will hoist the flag at Ramtirth in Nashik, and Chief Minister Devendra Fadnavis at Trimbakeshwar. Saints of the Vaishnava and Shaiva Akhadas are expected, with a Godavari aarti in the evening."),
        "hi": ("रामतीर्थ और त्र्यंबकेश्वर में ध्वजारोहण से सिंहस्थ का आरंभ",
               "ध्वजारोहण शनिवार, 31 अक्टूबर को दोपहर 12:02 बजे निर्धारित है। सकाळ के अनुसार नाशिक के रामतीर्थ पर राष्ट्रपति द्रौपदी मुर्मू और त्र्यंबकेश्वर में मुख्यमंत्री देवेंद्र फडणवीस ध्वजारोहण करेंगे। वैष्णव और शैव अखाड़ों के संतों की उपस्थिति अपेक्षित है और शाम को गोदावरी आरती होगी।"),
        "mr": ("रामतीर्थ आणि त्र्यंबकेश्वर येथे ध्वजारोहणाने सिंहस्थाला प्रारंभ",
               "ध्वजारोहण शनिवार, 31 ऑक्टोबर रोजी दुपारी 12:02 वाजता नियोजित आहे. सकाळच्या वृत्तानुसार नाशिकच्या रामतीर्थावर राष्ट्रपती द्रौपदी मुर्मू आणि त्र्यंबकेश्वर येथे मुख्यमंत्री देवेंद्र फडणवीस ध्वजारोहण करतील. वैष्णव आणि शैव आखाड्यांचे संत अपेक्षित असून सायंकाळी गोदावरी आरती होईल."),
    },
    {
        "publisher": "free-press-journal", "category": "spiritual",
        "url": "https://www.freepressjournal.in/pune/nashik-saints-mahants-and-devotees-take-part-in-nagar-parikrama-ahead-of-simhastha-kumbh",
        "published_at": datetime(2026, 10, 30, 18, 45, tzinfo=IST),
        "en": ("Saints and devotees walk the Nagar Parikrama from Tapovan to Ramkund",
               "A procession set out from Modi Ground in Tapovan on Friday afternoon, passing through Panchavati and the old city to Ramkund. A decorated palanquin carried the religious flag, the sacred Kumbh and an idol of Goddess Godavari, and a Godavari aarti followed on arrival."),
        "hi": ("तपोवन से रामकुंड तक संतों और श्रद्धालुओं की नगर परिक्रमा",
               "शुक्रवार दोपहर तपोवन के मोदी मैदान से शोभायात्रा निकली और पंचवटी व पुराने शहर से होते हुए रामकुंड पहुँची। सजी हुई पालकी में धर्मध्वज, पवित्र कुंभ और देवी गोदावरी की मूर्ति थी। पहुँचने पर गोदावरी आरती हुई।"),
        "mr": ("तपोवन ते रामकुंड संत आणि भाविकांची नगर परिक्रमा",
               "शुक्रवारी दुपारी तपोवनातील मोदी मैदानातून मिरवणूक निघाली आणि पंचवटी व जुन्या शहरातून रामकुंडावर पोहोचली. सजवलेल्या पालखीत धर्मध्वज, पवित्र कुंभ आणि देवी गोदावरीची मूर्ती होती. पोहोचल्यावर गोदावरी आरती झाली."),
    },
    {
        "publisher": "sakal", "category": "transport",
        "url": "https://www.esakal.com/uttar-maharashtra/nashik/nashik-trimbak-traffic-changes",
        "published_at": datetime(2026, 10, 26, 21, 14, tzinfo=IST),
        "en": ("Nashik–Trimbakeshwar road diverted until Saturday evening",
               "Sakal reports traffic changes on the Nashik–Trimbak route from 8 am on Friday to 8 pm on Saturday, 31 October, for the President's visit. Alternative routes run through Govardhan, Girnare and Dhondegaon. Check local instructions before you set out."),
        "hi": ("नाशिक–त्र्यंबकेश्वर मार्ग शनिवार शाम तक परिवर्तित",
               "सकाळ के अनुसार राष्ट्रपति के दौरे के लिए नाशिक–त्र्यंबक मार्ग पर शुक्रवार सुबह 8 बजे से शनिवार, 31 अक्टूबर की रात 8 बजे तक यातायात में बदलाव है। वैकल्पिक मार्ग गोवर्धन, गिरणारे और ढोंडेगाव से जाते हैं। निकलने से पहले स्थानीय निर्देश देख लें।"),
        "mr": ("नाशिक–त्र्यंबकेश्वर मार्गावरील वाहतूक शनिवार सायंकाळपर्यंत वळवली",
               "सकाळच्या वृत्तानुसार राष्ट्रपतींच्या दौऱ्यासाठी नाशिक–त्र्यंबक मार्गावर शुक्रवार सकाळी 8 ते शनिवार, 31 ऑक्टोबर रात्री 8 वाजेपर्यंत वाहतुकीत बदल आहेत. पर्यायी मार्ग गोवर्धन, गिरणारे आणि ढोंडेगाव मार्गे जातात. निघण्यापूर्वी स्थानिक सूचना तपासा."),
    },
    {
        "publisher": "sakal", "category": "environment",
        "url": "https://www.esakal.com/uttar-maharashtra/nashik/water-reservation-kumbh-mela",
        "published_at": datetime(2026, 10, 30, 19, 19, tzinfo=IST),
        "en": ("No separate water reservation for the Kumbh, says minister Girish Mahajan",
               "Kumbh Mela Minister Girish Mahajan said no extra water would be released for the flag hoisting, and that available water has been planned through 31 August 2027. He also said development work would finish on time, with nine months left to the main bathing dates."),
        "hi": ("कुंभ के लिए अलग जल आरक्षण नहीं: मंत्री गिरीश महाजन",
               "कुंभ मेला मंत्री गिरीश महाजन ने कहा कि ध्वजारोहण के लिए अतिरिक्त पानी नहीं छोड़ा जाएगा और उपलब्ध पानी की योजना 31 अगस्त 2027 तक बनाई गई है। उन्होंने यह भी कहा कि मुख्य स्नान तिथियों में नौ महीने शेष हैं और विकास कार्य समय पर पूरे होंगे।"),
        "mr": ("कुंभमेळ्यासाठी स्वतंत्र पाणी आरक्षण नाही: मंत्री गिरीश महाजन",
               "कुंभमेळा मंत्री गिरीश महाजन म्हणाले की ध्वजारोहणासाठी जादा पाणी सोडले जाणार नाही आणि उपलब्ध पाण्याचे नियोजन 31 ऑगस्ट 2027 पर्यंत केले आहे. मुख्य स्नान तारखांना नऊ महिने बाकी असून विकासकामे वेळेत पूर्ण होतील, असेही ते म्हणाले."),
    },
    {
        "publisher": "navbharat-live", "category": "infrastructure",
        "url": "https://navbharatlive.com/maharashtra/nashik/nashik-trimbakeshwar-simhastha-kumbh-flag-hoisting-rehearsal-sadhugram-facilities-mgb06",
        "published_at": datetime(2026, 10, 28, 8, 36, tzinfo=IST),
        "en": ("Nashik approves ₹3.29 crore for basic works at Tapovan Sadhugram",
               "The municipal Standing Committee cleared roads, water supply, drainage, electricity and pavilions for the Digambar, Nirmohi and Nirvani Akhadas at Tapovan, Navbharat reports. The district administration also held a rehearsal for the flag hoisting."),
        "hi": ("तपोवन साधुग्राम के बुनियादी कार्यों के लिए 3.29 करोड़ रुपये मंज़ूर",
               "नवभारत के अनुसार नाशिक मनपा की स्थायी समिति ने तपोवन में दिगंबर, निर्मोही और निर्वाणी अखाड़ों के लिए सड़क, जलापूर्ति, जल निकासी, बिजली और मंडप के कार्य मंज़ूर किए। ज़िला प्रशासन ने ध्वजारोहण का पूर्वाभ्यास भी किया।"),
        "mr": ("तपोवन साधुग्राममधील मूलभूत कामांसाठी 3.29 कोटी रुपये मंजूर",
               "नवभारतच्या वृत्तानुसार नाशिक महापालिकेच्या स्थायी समितीने तपोवनात दिगंबर, निर्मोही आणि निर्वाणी आखाड्यांसाठी रस्ते, पाणीपुरवठा, जलनिस्सारण, वीज आणि मंडपांच्या कामांना मंजुरी दिली. जिल्हा प्रशासनाने ध्वजारोहणाची रंगीत तालीमही घेतली."),
    },
    {
        "publisher": "sakal", "category": "preparations",
        "url": "https://www.esakal.com/uttar-maharashtra/nashik/kumbh-mela-global-welcome",
        "published_at": datetime(2026, 10, 30, 19, 40, tzinfo=IST),
        "en": ("State names a protocol officer to receive foreign guests at the Simhastha",
               "Maharashtra has appointed Milind Hardas as special coordinator for foreign dignitaries and non-resident Indians visiting Nashik and Trimbakeshwar. The role covers coordination with embassies, the Kumbh authority and police."),
        "hi": ("सिंहस्थ में विदेशी अतिथियों के लिए राज्य ने प्रोटोकॉल अधिकारी नियुक्त किया",
               "महाराष्ट्र ने नाशिक और त्र्यंबकेश्वर आने वाले विदेशी गणमान्य अतिथियों और प्रवासी भारतीयों के लिए मिलिंद हर्डास को विशेष समन्वयक नियुक्त किया है। इस भूमिका में दूतावासों, कुंभ प्राधिकरण और पुलिस से समन्वय शामिल है।"),
        "mr": ("सिंहस्थात परदेशी पाहुण्यांसाठी राज्याने राजशिष्टाचार अधिकारी नेमला",
               "महाराष्ट्राने नाशिक आणि त्र्यंबकेश्वरला येणाऱ्या परदेशी मान्यवरांसाठी आणि अनिवासी भारतीयांसाठी मिलिंद हर्डास यांना विशेष समन्वयक नेमले आहे. या भूमिकेत दूतावास, कुंभ प्राधिकरण आणि पोलिसांशी समन्वय समाविष्ट आहे."),
    },
    {
        "publisher": "sakal", "category": "spiritual",
        "url": "https://www.esakal.com/uttar-maharashtra/nashik/kumbh-mela-2027-nashik-flag-hoisting",
        "published_at": datetime(2026, 10, 30, 19, 31, tzinfo=IST),
        "en": ("Flagstaff rites begin at Ramtirth ahead of the hoisting",
               "The Ganga Godavari Purohit Sangh began a three-day flagstaff consecration at Ramtirth, with Godavari worship and the Pradhan Sankalp ritual, working with the Kumbh Mela Authority and the municipal corporation."),
        "hi": ("ध्वजारोहण से पहले रामतीर्थ पर ध्वजस्तंभ अनुष्ठान आरंभ",
               "गंगा गोदावरी पुरोहित संघ ने रामतीर्थ पर तीन दिवसीय ध्वजस्तंभ प्रतिष्ठा आरंभ की, जिसमें गोदावरी पूजन और प्रधान संकल्प अनुष्ठान शामिल हैं। इसमें कुंभ मेला प्राधिकरण और महानगरपालिका का सहयोग है।"),
        "mr": ("ध्वजारोहणापूर्वी रामतीर्थावर ध्वजस्तंभ विधींना प्रारंभ",
               "गंगा गोदावरी पुरोहित संघाने रामतीर्थावर तीन दिवसांचा ध्वजस्तंभ प्रतिष्ठापना सोहळा सुरू केला, ज्यात गोदावरी पूजन आणि प्रधान संकल्प विधी आहेत. यात कुंभमेळा प्राधिकरण आणि महापालिकेचे सहकार्य आहे."),
    },
    {
        "publisher": "free-press-journal", "category": "environment",
        "url": "https://www.freepressjournal.in/pune/nashik-hemantdas-maharaj-demands-pollution-free-godavari-river-ahead-of-simhastha-kumbh-mela-2027",
        "published_at": datetime(2026, 6, 11, 18, 57, tzinfo=IST),
        "en": ("Saints inspect Tapovan and ghats, and call for a clean Godavari",
               "Saints visited proposed Akhada sites at Tapovan Sadhugram and ghats around Ramkund. Hemantdas Maharaj asked that the Godavari be free of pollution before the Simhastha."),
        "hi": ("संतों ने तपोवन और घाटों का निरीक्षण किया, स्वच्छ गोदावरी की माँग",
               "संतों ने तपोवन साधुग्राम में अखाड़ों के प्रस्तावित स्थलों और रामकुंड के घाटों का निरीक्षण किया। हेमंतदास महाराज ने सिंहस्थ से पहले गोदावरी को प्रदूषण मुक्त करने की माँग की।"),
        "mr": ("संतांकडून तपोवन आणि घाटांची पाहणी, स्वच्छ गोदावरीची मागणी",
               "संतांनी तपोवन साधुग्राममधील आखाड्यांच्या प्रस्तावित जागा आणि रामकुंड परिसरातील घाटांची पाहणी केली. हेमंतदास महाराज यांनी सिंहस्थापूर्वी गोदावरी प्रदूषणमुक्त करण्याची मागणी केली."),
    },
    {
        "publisher": "pti-theprint", "category": "dates",
        "url": "https://theprint.in/india/simhastha-kumbh-mela-to-begin-in-nashik-trimbakeshwar-on-oct-31-next-year/2643959",
        "published_at": datetime(2025, 6, 1, 18, 0, tzinfo=IST),
        "en": ("Amrit Snan dates set for August and September 2027",
               "At a planning meeting chaired by the Chief Minister, three main bathing days were announced: 2 August, 31 August and 11 September 2027, with the last at Trimbakeshwar on 12 September. The Kumbh runs until the flag is lowered on 24 July 2028."),
        "hi": ("अमृत स्नान की तिथियाँ अगस्त और सितंबर 2027 में",
               "मुख्यमंत्री की अध्यक्षता वाली योजना बैठक में तीन मुख्य स्नान दिवस घोषित हुए: 2 अगस्त, 31 अगस्त और 11 सितंबर 2027, और अंतिम स्नान त्र्यंबकेश्वर में 12 सितंबर को। कुंभ 24 जुलाई 2028 को ध्वज उतरने तक चलेगा।"),
        "mr": ("अमृत स्नानाच्या तारखा ऑगस्ट आणि सप्टेंबर 2027 मध्ये",
               "मुख्यमंत्र्यांच्या अध्यक्षतेखालील नियोजन बैठकीत तीन मुख्य स्नान दिवस जाहीर झाले: 2 ऑगस्ट, 31 ऑगस्ट आणि 11 सप्टेंबर 2027, तर शेवटचे स्नान त्र्यंबकेश्वर येथे 12 सप्टेंबरला. 24 जुलै 2028 रोजी ध्वज उतरेपर्यंत कुंभ चालेल."),
    },
]
