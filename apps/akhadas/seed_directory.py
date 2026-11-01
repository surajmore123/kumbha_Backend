"""
Starting content for the directory, loaded by `manage.py seed_akhadas`.

Every statement here traces to a listed source (checked 2026-10-30). Fields are
left out where sources were weak or disagreed: for example headquarters and
founding years, which vary between reference sites. Editors take over in admin.
"""

from datetime import date

ACCESSED = date(2026, 10, 30)
_VIA_SEARCH = "Site blocks automated reading; checked through its search excerpt. Re-read in a browser."
_VIA_CITATION = "Cited through Wikipedia's reference; the book itself was not read."

SOURCES = {
    "pib_akharas": {
        "title": "Spiritual Powerhouses: Akharas at the Forefront of Maha Kumbh 2025",
        "url": "https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/jan/doc2025122488401.pdf",
        "organization": "Press Information Bureau, Ministry of Culture",
        "source_type": "government", "published_on": date(2025, 1, 22),
        "verification_notes": "Dates Akhara origins to the 6th century; Britannica dates Shankara to the 8th.",
    },
    "kumbh_gurus": {
        "title": "Spiritual Gurus", "url": "https://kumbh.gov.in/en/spiritualgurus",
        "organization": "Maha Kumbh Mela 2025, Government of Uttar Pradesh", "source_type": "government",
    },
    "kumbh_pauranic": {
        "title": "Pauranic Significance", "url": "https://www.kumbh.gov.in/en/pauranicsignificance",
        "organization": "Maha Kumbh Mela 2025, Government of Uttar Pradesh", "source_type": "government",
        "verification_notes": _VIA_SEARCH,
    },
    "fpj_13": {
        "title": "13 akhadas with army of Sadhus are the grandeur of the Mela",
        "url": "https://www.freepressjournal.in/ujjain/13-akhadas-with-army-of-sadhus-are-the-grandeur-of-the-mela",
        "organization": "Free Press Journal", "source_type": "news", "published_on": date(2019, 5, 31),
    },
    "ani_2025": {
        "title": "Maha Kumbh: Swami Kailashanand Giri leads Niranjani Akhara as first Amrit Snan begins",
        "url": "https://www.latestly.com/agency-news/india-news-maha-kumbh-swami-kailashanand-giri-leads-niranjani-akhara-as-first-amrit-snan-begins-6563235.html",
        "organization": "ANI via LatestLY", "source_type": "news", "published_on": date(2025, 1, 14),
    },
    "britannica_dashnami": {
        "title": "Dashnami sannyasin", "url": "https://www.britannica.com/topic/dashnami-sannyasin",
        "organization": "Encyclopaedia Britannica", "source_type": "reference", "verification_notes": _VIA_SEARCH,
    },
    "britannica_naga": {
        "title": "Naga sannyasin", "url": "https://www.britannica.com/topic/naga-sannyasin",
        "organization": "Encyclopaedia Britannica", "source_type": "reference", "verification_notes": _VIA_SEARCH,
    },
    "britannica_shankara": {
        "title": "Shankara", "url": "https://www.britannica.com/biography/Shankara",
        "organization": "Encyclopaedia Britannica", "source_type": "reference", "verification_notes": _VIA_SEARCH,
    },
    "jacobsen": {
        "title": "South Asian Religions on Display: Religious Processions in South Asia and in the Diaspora (pp. 32–34)",
        "url": "https://books.google.com/books?id=WT2odZ7_d7MC&pg=PA32",
        "organization": "Knut A. Jacobsen (ed.), Routledge", "source_type": "academic",
        "published_on": date(2008, 1, 1), "verification_notes": _VIA_CITATION,
    },
    "lochtefeld": {
        "title": "God's Gateway: Identity and Meaning in a Hindu Pilgrimage Place (pp. 252–253)",
        "url": "https://books.google.com/books?id=V1L99XsB1gkC&pg=PA252",
        "organization": "James Lochtefeld, Oxford University Press", "source_type": "academic",
        "published_on": date(2009, 1, 1), "verification_notes": _VIA_CITATION,
    },
    "nirmal_eos": {
        "title": "Nirmal Panchaiti Akhara", "url": "https://eos.learnpunjabi.org/NIRMAL%20PANCHAITI%20AKHARA.html",
        "organization": "Punjabi University (learnpunjabi.org)", "source_type": "reference",
        "verification_notes": "Publisher isn't named on the page; attribution inferred from the site.",
    },
    "etv_agni": {
        "title": "Gymnasium founded by Adi Guru Shankaracharya still functioning at Bhavnath",
        "url": "https://www.etvbharat.com/amp/english/state/gujarat/gymnasium-founded-by-adi-guru-shankaracharya-still-functioning-at-bhavnath/na20201214072640168",
        "organization": "ETV Bharat", "source_type": "news", "published_on": date(2020, 12, 14),
    },
    "etv_parishad": {
        "title": "Uttarakhand: Feud Intensifies In Akhara Parishad Ahead Of 2027 Haridwar Ardh Kumbh",
        "url": "https://www.etvbharat.com/en/state/feud-intensifies-in-akhara-parishad-ahead-of-2027-haridwar-ardh-kumbh-enn26062804042",
        "organization": "ETV Bharat", "source_type": "news", "published_on": date(2026, 6, 28),
        "verification_notes": "Two rival leaders, both named Mahant Ravindra Puri (Mahanirvani and Niranjani). Why the app names neither as Parishad head.",
    },
    "hinduism_today": {
        "title": "Swami Avdheshananda Giri, Hindu of the Year",
        "url": "https://www.hinduismtoday.com/magazine/january-february-march-2009/2009-01-swami-avdheshananda-giri-hindu-of-the-year/",
        "organization": "Hinduism Today", "source_type": "news", "published_on": date(2009, 1, 1),
    },
    "republic_kailash": {
        "title": "Kailashanand Giri installed Acharya Mahamandaleshwar of Niranjani Akhada",
        "url": "https://www.republicworld.com/india/kailashanand-giri-installed-acharya-mahamandaleshwar-of-niranjani-akhada",
        "organization": "Republic World", "source_type": "news", "published_on": date(2021, 1, 14),
    },
    "pti_dates": {
        "title": "Simhastha Kumbh Mela to begin in Nashik-Trimbakeshwar on Oct 31 next year",
        "url": "https://theprint.in/india/simhastha-kumbh-mela-to-begin-in-nashik-trimbakeshwar-on-oct-31-next-year/2643959",
        "organization": "PTI via ThePrint", "source_type": "news", "published_on": date(2025, 6, 1),
    },
    "sarkarnama_dates": {
        "title": "Nashik Kumbh Mela dates announced",
        "url": "https://sarkarnama.esakal.com/maharashtra/uttar-maharashtra/nashik-kumbh-mela-2026-dates-trimbakeshwar-holy-bath-schedule-mahaparv-gs97",
        "organization": "Sarkarnama", "source_type": "news", "published_on": date(2025, 6, 1),
        "verification_notes": "Calls the Amrit Snan dates probable. Only source found for the 24 July 2027 Akhada flag hoisting.",
    },
    "navbharat_flag": {
        "title": "Nashik Simhastha Kumbh preparations: Mahadhwajarohan rehearsal and Sadhugram facilities",
        "url": "https://navbharatlive.com/maharashtra/nashik/nashik-trimbakeshwar-simhastha-kumbh-flag-hoisting-rehearsal-sadhugram-facilities-mgb06",
        "organization": "Navbharat Live", "source_type": "news", "published_on": date(2026, 10, 28),
    },
    "fpj_inspection": {
        "title": "Nashik: Hemantdas Maharaj Demands Pollution-Free Godavari River Ahead Of Simhastha Kumbh Mela 2027",
        "url": "https://www.freepressjournal.in/pune/nashik-hemantdas-maharaj-demands-pollution-free-godavari-river-ahead-of-simhastha-kumbh-mela-2027",
        "organization": "Free Press Journal", "source_type": "news", "published_on": date(2026, 6, 11),
    },
    "sarkarnama_land": {
        "title": "Sadhugram land still unresolved as Kumbh flag hoisting nears",
        "url": "https://sarkarnama.esakal.com/maharashtra/uttar-maharashtra/nashik-simhastha-kumbh-mela-sadhu-gram-land-dispute-farmers-compensation-pg00-sd67",
        "organization": "Sarkarnama", "source_type": "news", "verification_notes": _VIA_SEARCH,
    },
    "dh_reels": {
        "title": "No reels, no selfies: officials ban making of videos at Mahakumbh",
        "url": "https://www.deccanherald.com/amp/story/india%2Futtar-pradesh%2Fno-reels-no-selfies-officials-ban-making-of-videos-at-mahakumbh-3264901",
        "organization": "Deccan Herald", "source_type": "news", "verification_notes": _VIA_SEARCH,
    },
}

TRADITIONS = [
    {
        "slug": "shaiva", "sources": ["kumbh_gurus", "pib_akharas", "britannica_dashnami"],
        "en": {
            "name": "Shaiva (Sannyasi)",
            "summary": "Akhadas devoted to Lord Shiva. Their ascetics, called sannyasis, belong to the Dashnami tradition of ten orders attributed to Adi Shankaracharya.",
            "philosophy": "Renunciation and devotion to Shiva in his various forms. Shankara's ten orders include names you may recognise from saints: Giri, Puri, Bharati and Saraswati.",
            "practices": "Naga sannyasis of these Akhadas are known for rigorous ascetic discipline. They carry traditional weapons such as spears and swords in Kumbh processions.",
        },
        "hi": {
            "name": "शैव (संन्यासी)",
            "summary": "भगवान शिव को समर्पित अखाड़े। इनके साधु संन्यासी कहलाते हैं और आदि शंकराचार्य से जोड़ी जाने वाली दस शाखाओं की दशनामी परंपरा से जुड़े हैं।",
            "philosophy": "त्याग और शिव के विभिन्न रूपों की भक्ति। शंकराचार्य की दस शाखाओं में गिरि, पुरी, भारती और सरस्वती जैसे नाम आते हैं, जो संतों के नामों में दिखते हैं।",
            "practices": "इन अखाड़ों के नागा संन्यासी कठोर तपस्या के लिए जाने जाते हैं। कुंभ की शोभायात्राओं में वे भाले और तलवार जैसे पारंपरिक शस्त्र लेकर चलते हैं।",
        },
        "mr": {
            "name": "शैव (संन्यासी)",
            "summary": "भगवान शिवांना समर्पित आखाडे. त्यांचे साधू संन्यासी म्हणवले जातात आणि आदि शंकराचार्यांशी जोडल्या जाणाऱ्या दहा शाखांच्या दशनामी परंपरेतील असतात.",
            "philosophy": "त्याग आणि शिवांच्या विविध रूपांची भक्ती. शंकराचार्यांच्या दहा शाखांमध्ये गिरी, पुरी, भारती आणि सरस्वती अशी नावे येतात, जी संतांच्या नावांत दिसतात.",
            "practices": "या आखाड्यांचे नागा संन्यासी कठोर तपश्चर्येसाठी ओळखले जातात. कुंभाच्या मिरवणुकांत ते भाले आणि तलवारी अशी पारंपरिक शस्त्रे घेऊन चालतात.",
        },
    },
    {
        "slug": "vaishnava", "sources": ["kumbh_gurus", "pib_akharas", "fpj_13"],
        "en": {
            "name": "Vaishnava (Bairagi)",
            "summary": "Akhadas devoted to Lord Vishnu in his various forms. Three Akhadas make up this tradition: Nirmohi, Nirvani and Digambar.",
            "philosophy": "Devotion to Vishnu. These Akhadas are also described as Ramanandiya.",
            "practices": "They raise religious flags (Dharm Dhwaj) bearing the image of Lord Hanuman. At Prayagraj, the Khak Chowk gathers mahants and mandaleshwars of the three Akhadas.",
        },
        "hi": {
            "name": "वैष्णव (बैरागी)",
            "summary": "भगवान विष्णु के विभिन्न रूपों को समर्पित अखाड़े। इस परंपरा में तीन अखाड़े हैं: निर्मोही, निर्वाणी और दिगंबर।",
            "philosophy": "विष्णु की भक्ति। इन अखाड़ों को रामानंदीय भी कहा जाता है।",
            "practices": "ये भगवान हनुमान की छवि वाले धर्म ध्वज फहराते हैं। प्रयागराज में खाक चौक इन तीनों अखाड़ों के महंतों और मंडलेश्वरों को एक साथ लाता है।",
        },
        "mr": {
            "name": "वैष्णव (बैरागी)",
            "summary": "भगवान विष्णूंच्या विविध रूपांना समर्पित आखाडे. या परंपरेत तीन आखाडे आहेत: निर्मोही, निर्वाणी आणि दिगंबर.",
            "philosophy": "विष्णूंची भक्ती. या आखाड्यांना रामानंदीय असेही म्हटले जाते.",
            "practices": "ते भगवान हनुमानांची प्रतिमा असलेले धर्मध्वज उभारतात. प्रयागराज येथे खाक चौक या तिन्ही आखाड्यांच्या महंतांना आणि मंडलेश्वरांना एकत्र आणतो.",
        },
    },
    {
        "slug": "udasin", "sources": ["kumbh_gurus", "fpj_13", "nirmal_eos"],
        "en": {
            "name": "Udasin",
            "summary": "Akhadas that trace their tradition to Chandra Dev (Sri Chand), described as the son of the first Sikh Guru. Their followers offer devotion to the sacred sound Om.",
            "philosophy": "The Maha Kumbh portal describes Udasin devotion as centred on Om.",
        },
        "hi": {
            "name": "उदासीन",
            "summary": "ये अखाड़े अपनी परंपरा चंद्र देव (श्री चंद) से जोड़ते हैं, जिन्हें प्रथम सिख गुरु का पुत्र बताया जाता है। इनके अनुयायी पवित्र ध्वनि ॐ की उपासना करते हैं।",
            "philosophy": "महाकुंभ पोर्टल के अनुसार उदासीन भक्ति का केंद्र ॐ है।",
        },
        "mr": {
            "name": "उदासीन",
            "summary": "हे आखाडे आपली परंपरा चंद्र देव (श्री चंद) यांच्याशी जोडतात, ज्यांना पहिल्या शीख गुरूंचे पुत्र मानले जाते. त्यांचे अनुयायी पवित्र ध्वनी ॐ ची उपासना करतात.",
            "philosophy": "महाकुंभ पोर्टलनुसार उदासीन भक्तीचे केंद्र ॐ आहे.",
        },
    },
    {
        "slug": "nirmal", "sources": ["nirmal_eos", "fpj_13"],
        "en": {
            "name": "Nirmal",
            "summary": "A tradition of saints linked to Guru Gobind Singh, with one Akhada. Some counts group it with the two Udasin Akhadas, which is why you may read that there are three 'Udasin' Akhadas.",
            "practices": "Under its founding rules, members wear ochre, remain celibate and take their vow on the Guru Granth Sahib.",
        },
        "hi": {
            "name": "निर्मल",
            "summary": "गुरु गोबिंद सिंह से जुड़ी संत परंपरा, जिसका एक अखाड़ा है। कुछ गणनाओं में इसे दो उदासीन अखाड़ों के साथ गिना जाता है, इसलिए कहीं-कहीं तीन 'उदासीन' अखाड़े लिखे मिलते हैं।",
            "practices": "इसके स्थापना नियमों के अनुसार सदस्य गेरुआ वस्त्र पहनते हैं, ब्रह्मचर्य रखते हैं और गुरु ग्रंथ साहिब की शपथ लेते हैं।",
        },
        "mr": {
            "name": "निर्मल",
            "summary": "गुरु गोबिंद सिंह यांच्याशी जोडलेली संत परंपरा, जिचा एक आखाडा आहे. काही गणनांत तो दोन उदासीन आखाड्यांसोबत मोजला जातो, म्हणून कधी कधी तीन 'उदासीन' आखाडे असे लिहिलेले दिसते.",
            "practices": "स्थापनेच्या नियमांनुसार सदस्य भगवी वस्त्रे घालतात, ब्रह्मचर्य पाळतात आणि गुरु ग्रंथ साहिबची शपथ घेतात.",
        },
    },
]

TITLES = [
    {
        "slug": "acharya-mahamandaleshwar", "sources": ["hinduism_today", "republic_kailash"],
        "en": {"name": "Acharya Mahamandaleshwar", "meaning": "The senior spiritual head of an Akhada, chosen by its assembled saints. Installation is a formal public ceremony."},
        "hi": {"name": "आचार्य महामंडलेश्वर", "meaning": "अखाड़े के वरिष्ठ आध्यात्मिक प्रमुख, जिन्हें अखाड़े के संत मिलकर चुनते हैं। इनका पट्टाभिषेक एक औपचारिक सार्वजनिक समारोह होता है।"},
        "mr": {"name": "आचार्य महामंडलेश्वर", "meaning": "आखाड्याचे ज्येष्ठ आध्यात्मिक प्रमुख, ज्यांची निवड आखाड्यातील संत एकत्रितपणे करतात. त्यांचा पट्टाभिषेक हा औपचारिक सार्वजनिक सोहळा असतो."},
    },
    {
        "slug": "mahamandaleshwar", "sources": ["pib_akharas", "kumbh_gurus"],
        "en": {"name": "Mahamandaleshwar", "meaning": "A senior leader within an Akhada who guides its spiritual and organizational life. The Maha Kumbh portal says they alone may give the Guru-mantra to new saints."},
        "hi": {"name": "महामंडलेश्वर", "meaning": "अखाड़े के वरिष्ठ नेता, जो उसके आध्यात्मिक और संगठनात्मक जीवन का मार्गदर्शन करते हैं। महाकुंभ पोर्टल के अनुसार नए संतों को गुरु-मंत्र देने का अधिकार केवल इन्हीं को है।"},
        "mr": {"name": "महामंडलेश्वर", "meaning": "आखाड्यातील ज्येष्ठ नेते, जे त्याच्या आध्यात्मिक आणि संघटनात्मक जीवनाला मार्गदर्शन करतात. महाकुंभ पोर्टलनुसार नव्या संतांना गुरु-मंत्र देण्याचा अधिकार फक्त त्यांनाच असतो."},
    },
    {
        "slug": "shri-mahant", "sources": ["kumbh_gurus", "fpj_13"],
        "en": {"name": "Shri Mahant", "meaning": "A senior office-bearer of an Akhada. The Maha Kumbh portal notes they accompany the Mahamandaleshwars in processions."},
        "hi": {"name": "श्री महंत", "meaning": "अखाड़े के वरिष्ठ पदाधिकारी। महाकुंभ पोर्टल के अनुसार वे शोभायात्राओं में महामंडलेश्वरों के साथ चलते हैं।"},
        "mr": {"name": "श्री महंत", "meaning": "आखाड्याचे ज्येष्ठ पदाधिकारी. महाकुंभ पोर्टलनुसार ते मिरवणुकांत महामंडलेश्वरांसोबत चालतात."},
    },
    {
        "slug": "mahant", "sources": ["etv_agni", "fpj_13"],
        "en": {"name": "Mahant", "meaning": "A head within an Akhada. In the Panch Agni Akhada, for example, the Mahant is appointed during the Maha Kumbh gathering."},
        "hi": {"name": "महंत", "meaning": "अखाड़े के भीतर का प्रमुख। उदाहरण के लिए, पंच अग्नि अखाड़े में महंत की नियुक्ति महाकुंभ के समागम में होती है।"},
        "mr": {"name": "महंत", "meaning": "आखाड्यातील प्रमुख. उदाहरणार्थ, पंच अग्नी आखाड्यात महंतांची नियुक्ती महाकुंभाच्या समागमात होते."},
    },
    {
        "slug": "thanapati", "sources": ["etv_agni", "fpj_13"],
        "en": {"name": "Thanapati", "meaning": "A manager who looks after an Akhada's affairs and organizes its religious programmes. Also called Sthaniya Mahant."},
        "hi": {"name": "थानापति", "meaning": "अखाड़े का प्रबंधक, जो उसके कामकाज और धार्मिक कार्यक्रमों की व्यवस्था देखता है। इन्हें स्थानीय महंत भी कहा जाता है।"},
        "mr": {"name": "थानापती", "meaning": "आखाड्याचे व्यवस्थापक, जे त्याचे कामकाज आणि धार्मिक कार्यक्रमांची व्यवस्था पाहतात. त्यांना स्थानिक महंत असेही म्हणतात."},
    },
]

_VAISHNAVA_NASHIK = {
    "en": "Reported in 2026: proposed sites for this Akhada in the Tapovan Sadhugram area were inspected, and the Nashik Municipal Corporation's Standing Committee approved basic works there. Final camp details aren't confirmed.",
    "hi": "2026 की रिपोर्टों के अनुसार तपोवन साधुग्राम क्षेत्र में इस अखाड़े के प्रस्तावित स्थलों का निरीक्षण हुआ और नाशिक महानगरपालिका की स्थायी समिति ने वहाँ बुनियादी कार्यों को मंज़ूरी दी। शिविर का अंतिम विवरण अभी पुष्ट नहीं है।",
    "mr": "2026 मधील वृत्तांनुसार तपोवन साधुग्राम परिसरात या आखाड्याच्या प्रस्तावित जागांची पाहणी झाली आणि नाशिक महापालिकेच्या स्थायी समितीने तेथील मूलभूत कामांना मंजुरी दिली. शिबिराचा अंतिम तपशील अजून निश्चित नाही.",
}
_SHAIVA_SOURCES = ["fpj_13", "ani_2025"]
_VAISHNAVA_SOURCES = ["pib_akharas", "fpj_13", "fpj_inspection", "navbharat_flag"]

AKHADAS = [
    {
        "slug": "juna", "tradition": "shaiva", "position": 1,
        "sources": ["pib_akharas", "kumbh_gurus", *_SHAIVA_SOURCES],
        "en": {
            "name": "Shri Panch Dashnam Juna Akhara", "common_name": "Juna Akhara",
            "summary": "The largest Akhada, known for its many initiated Naga sannyasis.",
            "organization": "Juna Akhara has initiated over 200 women into sannyas and renamed its women's organization Sannyasini Shri Panchadashnam Juna Akhara (reported in January 2025).",
            "kumbh_significance": "Its Naga sannyasis are among the most recognised participants of Kumbh processions.",
        },
        "hi": {
            "name": "श्री पंच दशनाम जूना अखाड़ा", "common_name": "जूना अखाड़ा",
            "summary": "सबसे बड़ा अखाड़ा, जो अपने अनेक दीक्षित नागा संन्यासियों के लिए जाना जाता है।",
            "organization": "जूना अखाड़े ने 200 से अधिक महिलाओं को संन्यास दीक्षा दी है और अपने महिला संगठन का नाम संन्यासिनी श्री पंचदशनाम जूना अखाड़ा रखा है (जनवरी 2025 की जानकारी)।",
            "kumbh_significance": "इसके नागा संन्यासी कुंभ की शोभायात्राओं के सबसे पहचाने जाने वाले सहभागियों में हैं।",
        },
        "mr": {
            "name": "श्री पंच दशनाम जुना आखाडा", "common_name": "जुना आखाडा",
            "summary": "सर्वात मोठा आखाडा, जो अनेक दीक्षित नागा संन्याशांसाठी ओळखला जातो.",
            "organization": "जुना आखाड्याने 200 हून अधिक महिलांना संन्यास दीक्षा दिली आहे आणि आपल्या महिला संघटनेचे नाव संन्यासिनी श्री पंचदशनाम जुना आखाडा ठेवले आहे (जानेवारी 2025 ची माहिती).",
            "kumbh_significance": "त्याचे नागा संन्यासी कुंभ मिरवणुकांतील सर्वाधिक ओळखले जाणारे सहभागी आहेत.",
        },
    },
    {
        "slug": "niranjani", "tradition": "shaiva", "position": 2,
        "sources": ["kumbh_gurus", *_SHAIVA_SOURCES],
        "en": {
            "name": "Shri Panchayati Akhada Niranjani", "common_name": "Niranjani Akhada",
            "summary": "One of the seven Shaiva Akhadas, listed by the Maha Kumbh portal among the largest after Juna, and known for its emphasis on yoga, meditation and spiritual knowledge.",
        },
        "hi": {
            "name": "श्री पंचायती अखाड़ा निरंजनी", "common_name": "निरंजनी अखाड़ा",
            "summary": "सात शैव अखाड़ों में से एक। महाकुंभ पोर्टल इसे जूना के बाद सबसे बड़े अखाड़ों में गिनता है। यह योग, ध्यान और आध्यात्मिक ज्ञान पर ज़ोर के लिए जाना जाता है।",
        },
        "mr": {
            "name": "श्री पंचायती आखाडा निरंजनी", "common_name": "निरंजनी आखाडा",
            "summary": "सात शैव आखाड्यांपैकी एक. महाकुंभ पोर्टल त्याला जुना नंतरच्या सर्वात मोठ्या आखाड्यांमध्ये गणते. योग, ध्यान आणि आध्यात्मिक ज्ञानावरील भरासाठी तो ओळखला जातो.",
        },
    },
    {
        "slug": "mahanirvani", "tradition": "shaiva", "position": 3,
        "sources": ["pib_akharas", "kumbh_gurus", *_SHAIVA_SOURCES],
        "en": {
            "name": "Shri Panchayati Akhada Mahanirvani", "common_name": "Mahanirvani Akhada",
            "summary": "One of the seven Shaiva Akhadas, described by the Government of India as one of the wealthiest and most influential.",
            "organization": "Described as the first Akhada to establish the position of Mahamandaleshwar for women. It also emphasizes environmental conservation.",
        },
        "hi": {
            "name": "श्री पंचायती अखाड़ा महानिर्वाणी", "common_name": "महानिर्वाणी अखाड़ा",
            "summary": "सात शैव अखाड़ों में से एक, जिसे भारत सरकार के प्रकाशन में सबसे समृद्ध और प्रभावशाली अखाड़ों में बताया गया है।",
            "organization": "इसे महिलाओं के लिए महामंडलेश्वर पद स्थापित करने वाला पहला अखाड़ा बताया गया है। यह पर्यावरण संरक्षण पर भी ज़ोर देता है।",
        },
        "mr": {
            "name": "श्री पंचायती आखाडा महानिर्वाणी", "common_name": "महानिर्वाणी आखाडा",
            "summary": "सात शैव आखाड्यांपैकी एक, ज्याचा भारत सरकारच्या प्रकाशनात सर्वात समृद्ध आणि प्रभावशाली आखाड्यांत उल्लेख आहे.",
            "organization": "महिलांसाठी महामंडलेश्वर पद स्थापन करणारा पहिला आखाडा म्हणून त्याचा उल्लेख आहे. तो पर्यावरण संवर्धनावरही भर देतो.",
        },
    },
    {
        "slug": "atal", "tradition": "shaiva", "position": 4, "sources": _SHAIVA_SOURCES,
        "en": {"name": "Shri Shambhu Panchayati Atal Akhara", "common_name": "Atal Akhada", "summary": "One of the seven Shaiva Akhadas of the sannyasi tradition."},
        "hi": {"name": "श्री शंभू पंचायती अटल अखाड़ा", "common_name": "अटल अखाड़ा", "summary": "संन्यासी परंपरा के सात शैव अखाड़ों में से एक।"},
        "mr": {"name": "श्री शंभू पंचायती अटल आखाडा", "common_name": "अटल आखाडा", "summary": "संन्यासी परंपरेतील सात शैव आखाड्यांपैकी एक."},
    },
    {
        "slug": "anand", "tradition": "shaiva", "position": 5, "sources": _SHAIVA_SOURCES,
        "en": {"name": "Shri Panchayati Anand Akhara", "common_name": "Anand Akhada", "summary": "One of the seven Shaiva Akhadas of the sannyasi tradition."},
        "hi": {"name": "श्री पंचायती आनंद अखाड़ा", "common_name": "आनंद अखाड़ा", "summary": "संन्यासी परंपरा के सात शैव अखाड़ों में से एक।"},
        "mr": {"name": "श्री पंचायती आनंद आखाडा", "common_name": "आनंद आखाडा", "summary": "संन्यासी परंपरेतील सात शैव आखाड्यांपैकी एक."},
    },
    {
        "slug": "avahan", "tradition": "shaiva", "position": 6,
        "sources": ["pib_akharas", *_SHAIVA_SOURCES],
        "en": {
            "name": "Shri Panch Dashnam Aavahan Akhara", "common_name": "Avahan Akhada",
            "summary": "A Shaiva Akhada described by the Government of India as part of the Kumbh Mela for over 1,200 years.",
            "kumbh_significance": "It keeps up the tradition of the Chhari Yatra, a procession carrying a holy staff that symbolizes divine authority.",
        },
        "hi": {
            "name": "श्री पंच दशनाम आवाहन अखाड़ा", "common_name": "आवाहन अखाड़ा",
            "summary": "एक शैव अखाड़ा, जिसे भारत सरकार के प्रकाशन में 1,200 से अधिक वर्षों से कुंभ मेले का हिस्सा बताया गया है।",
            "kumbh_significance": "यह छड़ी यात्रा की परंपरा निभाता है, जिसमें दैवी अधिकार की प्रतीक पवित्र छड़ी लेकर शोभायात्रा निकलती है।",
        },
        "mr": {
            "name": "श्री पंच दशनाम आवाहन आखाडा", "common_name": "आवाहन आखाडा",
            "summary": "एक शैव आखाडा, ज्याचा भारत सरकारच्या प्रकाशनात 1,200 हून अधिक वर्षे कुंभमेळ्याचा भाग असा उल्लेख आहे.",
            "kumbh_significance": "तो छडी यात्रेची परंपरा जपतो, ज्यात दैवी अधिकाराचे प्रतीक असलेली पवित्र छडी घेऊन मिरवणूक निघते.",
        },
    },
    {
        "slug": "agni", "tradition": "shaiva", "position": 7,
        "sources": ["etv_agni", *_SHAIVA_SOURCES],
        "en": {
            "name": "Shri Panch Agni Akhara", "common_name": "Agni Akhada",
            "summary": "One of the seven Shaiva Akhadas of the sannyasi tradition.",
            "organization": "Its Mahant is appointed during the Maha Kumbh gathering, and the Mahant appoints a manager, the Thanapati (reported in 2020).",
        },
        "hi": {
            "name": "श्री पंच अग्नि अखाड़ा", "common_name": "अग्नि अखाड़ा",
            "summary": "संन्यासी परंपरा के सात शैव अखाड़ों में से एक।",
            "organization": "इसके महंत की नियुक्ति महाकुंभ के समागम में होती है और महंत प्रबंधक, यानी थानापति, नियुक्त करते हैं (2020 की जानकारी)।",
        },
        "mr": {
            "name": "श्री पंच अग्नी आखाडा", "common_name": "अग्नी आखाडा",
            "summary": "संन्यासी परंपरेतील सात शैव आखाड्यांपैकी एक.",
            "organization": "त्याच्या महंतांची नियुक्ती महाकुंभाच्या समागमात होते आणि महंत व्यवस्थापक, म्हणजे थानापती, नेमतात (2020 ची माहिती).",
        },
    },
    {
        "slug": "nirmohi", "tradition": "vaishnava", "position": 8, "sources": _VAISHNAVA_SOURCES,
        "en": {"name": "Shri Panch Nirmohi Ani Akhada", "common_name": "Nirmohi Akhada", "summary": "One of the three Vaishnava Akhadas, devoted to Lord Vishnu.", "nashik_note": _VAISHNAVA_NASHIK["en"]},
        "hi": {"name": "श्री पंच निर्मोही अनी अखाड़ा", "common_name": "निर्मोही अखाड़ा", "summary": "भगवान विष्णु को समर्पित तीन वैष्णव अखाड़ों में से एक।", "nashik_note": _VAISHNAVA_NASHIK["hi"]},
        "mr": {"name": "श्री पंच निर्मोही अनी आखाडा", "common_name": "निर्मोही आखाडा", "summary": "भगवान विष्णूंना समर्पित तीन वैष्णव आखाड्यांपैकी एक.", "nashik_note": _VAISHNAVA_NASHIK["mr"]},
    },
    {
        "slug": "nirvani", "tradition": "vaishnava", "position": 9, "sources": _VAISHNAVA_SOURCES,
        "en": {"name": "Shri Panch Nirvani Ani Akhada", "common_name": "Nirvani Akhada", "summary": "One of the three Vaishnava Akhadas, devoted to Lord Vishnu.", "nashik_note": _VAISHNAVA_NASHIK["en"]},
        "hi": {"name": "श्री पंच निर्वाणी अनी अखाड़ा", "common_name": "निर्वाणी अखाड़ा", "summary": "भगवान विष्णु को समर्पित तीन वैष्णव अखाड़ों में से एक।", "nashik_note": _VAISHNAVA_NASHIK["hi"]},
        "mr": {"name": "श्री पंच निर्वाणी अनी आखाडा", "common_name": "निर्वाणी आखाडा", "summary": "भगवान विष्णूंना समर्पित तीन वैष्णव आखाड्यांपैकी एक.", "nashik_note": _VAISHNAVA_NASHIK["mr"]},
    },
    {
        "slug": "digambar", "tradition": "vaishnava", "position": 10, "sources": _VAISHNAVA_SOURCES,
        "en": {"name": "Shri Panch Digambar Ani Akhada", "common_name": "Digambar Akhada", "summary": "One of the three Vaishnava Akhadas, devoted to Lord Vishnu.", "nashik_note": _VAISHNAVA_NASHIK["en"]},
        "hi": {"name": "श्री पंच दिगंबर अनी अखाड़ा", "common_name": "दिगंबर अखाड़ा", "summary": "भगवान विष्णु को समर्पित तीन वैष्णव अखाड़ों में से एक।", "nashik_note": _VAISHNAVA_NASHIK["hi"]},
        "mr": {"name": "श्री पंच दिगंबर अनी आखाडा", "common_name": "दिगंबर आखाडा", "summary": "भगवान विष्णूंना समर्पित तीन वैष्णव आखाड्यांपैकी एक.", "nashik_note": _VAISHNAVA_NASHIK["mr"]},
    },
    {
        "slug": "bada-udasin", "tradition": "udasin", "position": 11, "sources": ["kumbh_gurus", "fpj_13"],
        "en": {"name": "Shri Panchayati Akhada Bada Udasin", "common_name": "Bada Udasin Akhada", "summary": "One of the two Udasin Akhadas, which trace their tradition to Chandra Dev (Sri Chand)."},
        "hi": {"name": "श्री पंचायती अखाड़ा बड़ा उदासीन", "common_name": "बड़ा उदासीन अखाड़ा", "summary": "दो उदासीन अखाड़ों में से एक, जो अपनी परंपरा चंद्र देव (श्री चंद) से जोड़ते हैं।"},
        "mr": {"name": "श्री पंचायती आखाडा बडा उदासीन", "common_name": "बडा उदासीन आखाडा", "summary": "दोन उदासीन आखाड्यांपैकी एक, जे आपली परंपरा चंद्र देव (श्री चंद) यांच्याशी जोडतात."},
    },
    {
        "slug": "naya-udasin", "tradition": "udasin", "position": 12, "sources": ["kumbh_gurus", "fpj_13"],
        "en": {"name": "Shri Panchayati Akhada Naya Udasin", "common_name": "Naya Udasin Akhada", "summary": "One of the two Udasin Akhadas, which trace their tradition to Chandra Dev (Sri Chand).", "history": "A 2019 report names Mahant Sudhir Das as its founder. Other accounts differ on its founding date."},
        "hi": {"name": "श्री पंचायती अखाड़ा नया उदासीन", "common_name": "नया उदासीन अखाड़ा", "summary": "दो उदासीन अखाड़ों में से एक, जो अपनी परंपरा चंद्र देव (श्री चंद) से जोड़ते हैं।", "history": "2019 की एक रिपोर्ट में महंत सुधीर दास को इसका संस्थापक बताया गया है। इसकी स्थापना की तिथि पर अलग-अलग मत हैं।"},
        "mr": {"name": "श्री पंचायती आखाडा नया उदासीन", "common_name": "नया उदासीन आखाडा", "summary": "दोन उदासीन आखाड्यांपैकी एक, जे आपली परंपरा चंद्र देव (श्री चंद) यांच्याशी जोडतात.", "history": "2019 च्या एका वृत्तात महंत सुधीर दास यांचा संस्थापक म्हणून उल्लेख आहे. स्थापनेच्या तारखेबाबत वेगवेगळे मत आहेत."},
    },
    {
        "slug": "nirmal", "tradition": "nirmal", "position": 13, "sources": ["nirmal_eos", "fpj_13"],
        "en": {
            "name": "Shri Panchayati Akhada Nirmal", "common_name": "Nirmal Akhada",
            "summary": "The Akhada of the Nirmal tradition, and the first central institution of that sect.",
            "history": "Formally inaugurated on 7 August 1862 at Patiala, with support from the rulers of Patiala, Nabha and Jind. Before it, Nirmal saints kept separate centres with no shared authority.",
            "nashik_note": "A reference entry lists Triyambak (Nashik) among its historical branches. This says nothing about its plans for 2027.",
        },
        "hi": {
            "name": "श्री पंचायती अखाड़ा निर्मल", "common_name": "निर्मल अखाड़ा",
            "summary": "निर्मल परंपरा का अखाड़ा और इस पंथ की पहली केंद्रीय संस्था।",
            "history": "7 अगस्त 1862 को पटियाला में इसका औपचारिक उद्घाटन हुआ, जिसमें पटियाला, नाभा और जींद के शासकों का सहयोग था। इससे पहले निर्मल संतों के अलग-अलग केंद्र थे और कोई साझा व्यवस्था नहीं थी।",
            "nashik_note": "एक संदर्भ ग्रंथ में त्र्यंबक (नाशिक) को इसकी ऐतिहासिक शाखाओं में गिना गया है। इससे 2027 की इसकी योजना के बारे में कुछ पता नहीं चलता।",
        },
        "mr": {
            "name": "श्री पंचायती आखाडा निर्मल", "common_name": "निर्मल आखाडा",
            "summary": "निर्मल परंपरेचा आखाडा आणि या पंथाची पहिली केंद्रीय संस्था.",
            "history": "7 ऑगस्ट 1862 रोजी पटियाला येथे त्याचे औपचारिक उद्घाटन झाले, ज्यात पटियाला, नाभा आणि जिंद येथील राज्यकर्त्यांचे सहकार्य होते. त्यापूर्वी निर्मल संतांची वेगवेगळी केंद्रे होती आणि समान व्यवस्था नव्हती.",
            "nashik_note": "एका संदर्भग्रंथात त्र्यंबक (नाशिक) चा त्याच्या ऐतिहासिक शाखांमध्ये उल्लेख आहे. यावरून 2027 च्या त्याच्या योजनेबद्दल काहीच कळत नाही.",
        },
    },
]

SAINTS = [
    {
        "slug": "adi-shankaracharya", "era": "historical", "position": 1,
        "sources": ["britannica_shankara", "britannica_dashnami", "kumbh_gurus", "pib_akharas"],
        "en": {
            "name": "Adi Shankaracharya",
            "biography": "Philosopher and teacher of Hindu tradition. Britannica notes that scholars now prefer the dates 700–750, rather than the once-customary 788–820. Government publications on the Kumbh place him variously in the 6th and 8th centuries.",
            "significance": "Ten orders of Shaiva ascetics and four monasteries are attributed to him, and official Kumbh publications trace the Akhada tradition to his effort to unite ascetics.",
        },
        "hi": {
            "name": "आदि शंकराचार्य",
            "biography": "हिंदू परंपरा के दार्शनिक और आचार्य। ब्रिटानिका के अनुसार विद्वान अब पहले प्रचलित 788–820 के बजाय 700–750 की तिथियों को अधिक मान्य मानते हैं। कुंभ से जुड़े सरकारी प्रकाशन उन्हें कहीं छठी और कहीं आठवीं शताब्दी में रखते हैं।",
            "significance": "शैव संन्यासियों की दस शाखाएँ और चार मठ उनसे जोड़े जाते हैं। कुंभ के आधिकारिक प्रकाशन अखाड़ा परंपरा को संन्यासियों को संगठित करने के उनके प्रयास से जोड़ते हैं।",
        },
        "mr": {
            "name": "आदि शंकराचार्य",
            "biography": "हिंदू परंपरेतील तत्त्वज्ञ आणि आचार्य. ब्रिटानिकानुसार विद्वान आता पूर्वी प्रचलित 788–820 ऐवजी 700–750 या तारखा अधिक ग्राह्य मानतात. कुंभाशी संबंधित सरकारी प्रकाशने त्यांना कधी सहाव्या तर कधी आठव्या शतकात ठेवतात.",
            "significance": "शैव संन्याशांच्या दहा शाखा आणि चार मठ त्यांच्याशी जोडले जातात. कुंभाची अधिकृत प्रकाशने आखाडा परंपरा संन्याशांना संघटित करण्याच्या त्यांच्या प्रयत्नाशी जोडतात.",
        },
    },
    {
        "slug": "sri-chand", "era": "historical", "position": 2,
        "sources": ["kumbh_gurus"],
        "en": {
            "name": "Sri Chand (Chandra Dev)",
            "biography": "Described by the Maha Kumbh portal as the son of the first Sikh Guru and the founder of the Udaseen Akharas.",
            "significance": "Udasin Akhadas trace their tradition to him.",
        },
        "hi": {
            "name": "श्री चंद (चंद्र देव)",
            "biography": "महाकुंभ पोर्टल के अनुसार वे प्रथम सिख गुरु के पुत्र और उदासीन अखाड़ों के संस्थापक थे।",
            "significance": "उदासीन अखाड़े अपनी परंपरा उनसे जोड़ते हैं।",
        },
        "mr": {
            "name": "श्री चंद (चंद्र देव)",
            "biography": "महाकुंभ पोर्टलनुसार ते पहिल्या शीख गुरूंचे पुत्र आणि उदासीन आखाड्यांचे संस्थापक होते.",
            "significance": "उदासीन आखाडे आपली परंपरा त्यांच्याशी जोडतात.",
        },
    },
    {
        "slug": "swami-avdheshanand-giri", "era": "contemporary", "position": 3,
        "akhada": "juna", "title": "acharya-mahamandaleshwar",
        "sources": ["hinduism_today"],
        "en": {
            "name": "Swami Avdheshanand Giri",
            "biography": "Described in 2009 by Hinduism Today as Acharya Mahamandaleshwar of the Juna Akhara. The magazine reports that he received sannyas diksha in 1985 from Swami Satyamitrananda and became Mahamandaleshwar in 1998, then Acharya.",
            "teachings": "He emphasizes meditation and selfless service (seva), and teaches that dharma must be lived, not only known.",
            "public_activities": "Hinduism Today describes his work as a speaker on the Ramayana in India and abroad, and social and educational projects, including one in Jhabua, Madhya Pradesh.",
        },
        "hi": {
            "name": "स्वामी अवधेशानंद गिरि",
            "biography": "हिंदुइज़्म टुडे ने 2009 में उन्हें जूना अखाड़े का आचार्य महामंडलेश्वर बताया। पत्रिका के अनुसार उन्होंने 1985 में स्वामी सत्यमित्रानंद से संन्यास दीक्षा ली और 1998 में महामंडलेश्वर, फिर आचार्य बने।",
            "teachings": "वे ध्यान और निःस्वार्थ सेवा पर ज़ोर देते हैं और सिखाते हैं कि धर्म केवल जानने की नहीं, जीने की बात है।",
            "public_activities": "हिंदुइज़्म टुडे के अनुसार वे भारत और विदेश में रामकथा कहते हैं और सामाजिक व शैक्षिक परियोजनाओं से जुड़े हैं, जिनमें मध्य प्रदेश के झाबुआ की एक परियोजना शामिल है।",
        },
        "mr": {
            "name": "स्वामी अवधेशानंद गिरी",
            "biography": "हिंदुइझम टुडेने 2009 मध्ये त्यांचा जुना आखाड्याचे आचार्य महामंडलेश्वर असा उल्लेख केला. मासिकानुसार त्यांनी 1985 मध्ये स्वामी सत्यमित्रानंद यांच्याकडून संन्यास दीक्षा घेतली आणि 1998 मध्ये ते महामंडलेश्वर, नंतर आचार्य झाले.",
            "teachings": "ते ध्यान आणि निःस्वार्थ सेवेवर भर देतात आणि धर्म केवळ जाणण्याचा नसून जगण्याचा विषय आहे, असे शिकवतात.",
            "public_activities": "हिंदुइझम टुडेनुसार ते भारतात आणि परदेशात रामकथा सांगतात आणि सामाजिक व शैक्षणिक प्रकल्पांशी जोडलेले आहेत, ज्यात मध्य प्रदेशातील झाबुआ येथील एका प्रकल्पाचा समावेश आहे.",
        },
    },
    {
        "slug": "swami-kailashanand-giri", "era": "contemporary", "position": 4,
        "akhada": "niranjani", "title": "acharya-mahamandaleshwar",
        "sources": ["republic_kailash", "ani_2025"],
        "en": {
            "name": "Swami Kailashanand Giri",
            "biography": "Installed as Acharya Mahamandaleshwar of the Niranjani Akhada at a ceremony reported in January 2021, attended by seers of the 13 Akhadas.",
            "public_activities": "He led the Niranjani Akhada's procession at the first Amrit Snan of the Maha Kumbh at Prayagraj on 14 January 2025.",
        },
        "hi": {
            "name": "स्वामी कैलाशानंद गिरि",
            "biography": "जनवरी 2021 की रिपोर्ट के अनुसार एक समारोह में उन्हें निरंजनी अखाड़े का आचार्य महामंडलेश्वर बनाया गया, जिसमें 13 अखाड़ों के संत उपस्थित थे।",
            "public_activities": "14 जनवरी 2025 को प्रयागराज महाकुंभ के पहले अमृत स्नान में उन्होंने निरंजनी अखाड़े की शोभायात्रा का नेतृत्व किया।",
        },
        "mr": {
            "name": "स्वामी कैलाशानंद गिरी",
            "biography": "जानेवारी 2021 च्या वृत्तानुसार एका सोहळ्यात त्यांची निरंजनी आखाड्याचे आचार्य महामंडलेश्वर म्हणून स्थापना झाली, ज्यास 13 आखाड्यांचे संत उपस्थित होते.",
            "public_activities": "14 जानेवारी 2025 रोजी प्रयागराज महाकुंभाच्या पहिल्या अमृत स्नानात त्यांनी निरंजनी आखाड्याच्या मिरवणुकीचे नेतृत्व केले.",
        },
    },
    {
        "slug": "mahant-gopal-giri", "era": "contemporary", "position": 5,
        "akhada": "avahan", "title": "mahant",
        "sources": ["pib_akharas"],
        "en": {
            "name": "Mahant Gopal Giri",
            "biography": "Named by the Government of India in January 2025 as leading the Shri Panch Dashnam Aavahan Akhara.",
            "public_activities": "The same publication credits the Akhada under his leadership with keeping up the Chhari Yatra tradition.",
        },
        "hi": {
            "name": "महंत गोपाल गिरि",
            "biography": "जनवरी 2025 के भारत सरकार के प्रकाशन में उन्हें श्री पंच दशनाम आवाहन अखाड़े का नेतृत्व करने वाला बताया गया है।",
            "public_activities": "उसी प्रकाशन के अनुसार उनके नेतृत्व में अखाड़ा छड़ी यात्रा की परंपरा निभा रहा है।",
        },
        "mr": {
            "name": "महंत गोपाल गिरी",
            "biography": "जानेवारी 2025 च्या भारत सरकारच्या प्रकाशनात ते श्री पंच दशनाम आवाहन आखाड्याचे नेतृत्व करतात, असा उल्लेख आहे.",
            "public_activities": "त्याच प्रकाशनानुसार त्यांच्या नेतृत्वाखाली आखाडा छडी यात्रेची परंपरा जपत आहे.",
        },
    },
]
