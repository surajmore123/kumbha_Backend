"""
Starting library, loaded by `manage.py seed_kumbh_content`. Checked 2026-10-30.
Traditions are described as traditions. Places where we found no official text
are marked awaiting verification rather than stated as fact.
"""

from datetime import date

CHECKED = date(2026, 10, 30)
_THIRD = "Read through a reference or search excerpt, not the original. Re-check."

SOURCES = {
    "nashik_gov": {
        "title": "Culture & Heritage, Nashik District", "url": "https://nashik.gov.in/en/tourism/culture-heritage/",
        "organization": "District Administration, Nashik", "source_type": "government",
    },
    "unesco": {
        "title": "Kumbh Mela, Representative List of the Intangible Cultural Heritage of Humanity",
        "url": "https://ich.unesco.org/en/RL/kumbh-mela-01258", "organization": "UNESCO", "source_type": "reference",
    },
    "kumbh_pauranic": {
        "title": "Pauranic Significance", "url": "https://www.kumbh.gov.in/en/pauranicsignificance",
        "organization": "Maha Kumbh Mela 2025, Government of Uttar Pradesh", "source_type": "government",
    },
    "kumbh_astro": {
        "title": "Astrological Significance", "url": "https://kumbh.gov.in/en/astrologicalsignificance",
        "organization": "Maha Kumbh Mela 2025, Government of Uttar Pradesh", "source_type": "government",
    },
    "trust": {
        "title": "History of Trimbakeshwar", "url": "https://trimbakeshwartrust.com/history",
        "organization": "Shri Trimbakeshwar Devasthan Trust", "source_type": "official_akhada",
    },
    "ntkma_about": {
        "title": "About the Nashik–Trimbakeshwar Authority",
        "url": "https://divcomnashik.maharashtra.gov.in/en/about-nashik-trimbakeshwar-authority/",
        "organization": "Divisional Commissioner, Nashik", "source_type": "government",
    },
    "pti": {
        "title": "Simhastha Kumbh Mela to begin in Nashik-Trimbakeshwar on Oct 31 next year",
        "url": "https://theprint.in/india/simhastha-kumbh-mela-to-begin-in-nashik-trimbakeshwar-on-oct-31-next-year/2643959",
        "organization": "PTI via ThePrint", "source_type": "news",
    },
    "fpj_parikrama": {
        "title": "Nashik: Saints, Mahants And Devotees Take Part In Nagar Parikrama Ahead Of Simhastha Kumbh",
        "url": "https://www.freepressjournal.in/pune/nashik-saints-mahants-and-devotees-take-part-in-nagar-parikrama-ahead-of-simhastha-kumbh",
        "organization": "Free Press Journal", "source_type": "news",
    },
    "pudhari_flag": {
        "title": "Why is flag hoisting performed at the Kumbh Mela?",
        "url": "https://pudhari.news/kumbh-mela/nashik-trimbakeshwar-kumbh-mela-2026-dhwajarohan-significance-muhurat-nl76",
        "organization": "Pudhari", "source_type": "news",
    },
    "jacobsen": {
        "title": "South Asian Religions on Display: Religious Processions in South Asia and in the Diaspora (pp. 32–34)",
        "url": "https://books.google.com/books?id=WT2odZ7_d7MC&pg=PA32", "organization": "Knut A. Jacobsen (ed.), Routledge",
        "source_type": "academic", "verification_notes": _THIRD,
    },
    "wiki_kalaram": {
        "title": "Kalaram Temple", "url": "https://en.wikipedia.org/wiki/Kalaram_Temple",
        "organization": "Wikipedia", "source_type": "reference", "verification_notes": _THIRD,
    },
    "wiki_panchavati": {
        "title": "Panchavati", "url": "https://en.wikipedia.org/wiki/Panchavati",
        "organization": "Wikipedia", "source_type": "reference", "verification_notes": _THIRD,
    },
}

SECTIONS = [
    ("understanding", "Understanding Kumbh", "कुंभ को समझें", "कुंभ समजून घ्या",
     "What it is, and why it comes to Nashik", "यह क्या है और नाशिक में क्यों होता है", "तो काय आहे आणि नाशिकमध्ये का होतो"),
    ("history", "History and Heritage", "इतिहास और विरासत", "इतिहास आणि वारसा",
     "The story of a river town and its temples", "एक नदी-नगर और उसके मंदिरों की कहानी", "नदीकाठच्या शहराची आणि मंदिरांची कथा"),
    ("rituals", "Rituals and Traditions", "अनुष्ठान और परंपराएँ", "विधी आणि परंपरा",
     "What happens, and what it means", "क्या होता है और उसका अर्थ क्या है", "काय घडते आणि त्याचा अर्थ काय"),
    ("guides", "Pilgrim Guides", "श्रद्धालु मार्गदर्शिका", "भाविक मार्गदर्शक",
     "Plain advice before you travel", "यात्रा से पहले सरल सलाह", "प्रवासापूर्वी सोपा सल्ला"),
    ("places", "Places of Discovery", "दर्शनीय स्थल", "दर्शनीय स्थळे",
     "The sacred geography of the Simhastha", "सिंहस्थ का पवित्र भूगोल", "सिंहस्थाचा पवित्र भूगोल"),
]

ARTICLES = [
    {
        "slug": "what-is-kumbh-mela", "section": "understanding", "featured": True, "cover": "kumbh-panorama",
        "sources": ["unesco", "nashik_gov", "kumbh_pauranic"],
        "en": ("What is the Kumbh Mela?", "One of the largest peaceful gatherings on earth, and a meeting of faith, river and sky.",
"""The Kumbh Mela is a Hindu pilgrimage in which millions gather to bathe in a sacred river. UNESCO, which added it to its list of intangible cultural heritage in 2017, calls it one of the world's largest peaceful gatherings of pilgrims.

It moves between four places: Haridwar, Prayagraj, Ujjain and Nashik–Trimbakeshwar. Each hosts the full Kumbh about once every twelve years.

## The story behind it

The tradition begins with the churning of the ocean, the Samudra Manthan. Gods and demons fought over a pot of amrit, the nectar of immortality, and drops fell at four places as it was carried away. Those four places host the Kumbh today.

> The chase is said to have lasted twelve divine days, and each divine day equals one human year.

## Why people come

Devotees believe that bathing at this time cleanses the soul. Ascetics, saints and ordinary families gather side by side, and UNESCO notes that the teacher-student bond in ashrams and Akhadas is the main way this tradition is passed on."""),
        "hi": ("कुंभ मेला क्या है?", "धरती के सबसे बड़े शांतिपूर्ण समागमों में से एक, जहाँ आस्था, नदी और आकाश मिलते हैं।",
"""कुंभ मेला एक हिंदू तीर्थयात्रा है जिसमें लाखों लोग पवित्र नदी में स्नान के लिए एकत्र होते हैं। यूनेस्को ने 2017 में इसे अमूर्त सांस्कृतिक विरासत की सूची में शामिल किया और इसे श्रद्धालुओं के विश्व के सबसे बड़े शांतिपूर्ण समागमों में से एक बताया।

यह चार स्थानों पर होता है: हरिद्वार, प्रयागराज, उज्जैन और नाशिक–त्र्यंबकेश्वर। हर स्थान पर पूर्ण कुंभ लगभग बारह वर्ष में एक बार होता है।

## इसके पीछे की कथा

यह परंपरा समुद्र मंथन से शुरू होती है। अमृत के कलश के लिए देवों और असुरों में संघर्ष हुआ और कलश ले जाते समय चार स्थानों पर अमृत की बूँदें गिरीं। आज इन्हीं चार स्थानों पर कुंभ होता है।

> कहा जाता है कि यह संघर्ष बारह दिव्य दिनों तक चला और एक दिव्य दिन एक मानव वर्ष के बराबर होता है।

## लोग क्यों आते हैं

श्रद्धालु मानते हैं कि इस समय स्नान से आत्मा शुद्ध होती है। साधु, संत और सामान्य परिवार साथ-साथ आते हैं। यूनेस्को के अनुसार आश्रमों और अखाड़ों का गुरु-शिष्य संबंध ही इस परंपरा को आगे बढ़ाने का मुख्य माध्यम है।"""),
        "mr": ("कुंभमेळा म्हणजे काय?", "पृथ्वीवरील सर्वात मोठ्या शांततापूर्ण समागमांपैकी एक, जिथे श्रद्धा, नदी आणि आकाश एकत्र येतात.",
"""कुंभमेळा ही एक हिंदू तीर्थयात्रा आहे ज्यात लाखो लोक पवित्र नदीत स्नानासाठी एकत्र येतात. युनेस्कोने 2017 मध्ये त्याचा अमूर्त सांस्कृतिक वारशाच्या यादीत समावेश केला आणि तो भाविकांच्या जगातील सर्वात मोठ्या शांततापूर्ण समागमांपैकी एक असल्याचे म्हटले.

तो चार ठिकाणी होतो: हरिद्वार, प्रयागराज, उज्जैन आणि नाशिक–त्र्यंबकेश्वर. प्रत्येक ठिकाणी पूर्ण कुंभ साधारण बारा वर्षांतून एकदा होतो.

## यामागची कथा

ही परंपरा समुद्रमंथनापासून सुरू होते. अमृताच्या कलशासाठी देव आणि असुरांमध्ये संघर्ष झाला आणि कलश नेताना चार ठिकाणी अमृताचे थेंब पडले. आज याच चार ठिकाणी कुंभ होतो.

> हा संघर्ष बारा दिव्य दिवस चालला असे मानले जाते आणि एक दिव्य दिवस म्हणजे एक मानवी वर्ष.

## लोक का येतात

या काळात स्नान केल्याने आत्मा शुद्ध होतो, अशी भाविकांची श्रद्धा आहे. साधू, संत आणि सामान्य कुटुंबे एकत्र येतात. युनेस्कोच्या मते आश्रम आणि आखाड्यांतील गुरु-शिष्य नाते हेच ही परंपरा पुढे नेण्याचे मुख्य माध्यम आहे."""),
    },
    {
        "slug": "what-is-simhastha", "section": "understanding", "cover": "ramkund-sankranti",
        "sources": ["nashik_gov", "kumbh_astro", "pti"], "temples": ["Trimbakeshwar"],
        "en": ("What is Simhastha, and why Nashik?", "The name comes from the sky; the place comes from the river.",
"""Simhastha means "in Leo". The Kumbh at Nashik and Trimbakeshwar takes this name because it is held when Jupiter enters Simha, the sign of Leo.

## The Godavari

The Kumbh here belongs to the Godavari. The river rises on the Brahmagiri hills at Trimbakeshwar and is honoured as Dakshin Ganga, the Ganga of the south. Tradition says that the sage Gautam's penance led Shiva to release the Ganga from his matted hair, and that she descended here as the Godavari.

## Two places, one Kumbh

The Simhastha is unusual in being held in two towns about 30 km apart. Nashik and Trimbakeshwar both host it, and the Akhadas are divided between them.

!info The Simhastha of 2027 opens with flag hoisting on 31 October 2026 and runs until 24 July 2028. The main bathing days fall in August and September 2027."""),
        "hi": ("सिंहस्थ क्या है और नाशिक ही क्यों?", "नाम आकाश से आता है, स्थान नदी से।",
"""सिंहस्थ का अर्थ है "सिंह राशि में"। नाशिक और त्र्यंबकेश्वर के कुंभ को यह नाम इसलिए मिला क्योंकि यह तब होता है जब बृहस्पति सिंह राशि में प्रवेश करते हैं।

## गोदावरी

यहाँ का कुंभ गोदावरी का है। यह नदी त्र्यंबकेश्वर के ब्रह्मगिरि पर्वत से निकलती है और इसे दक्षिण गंगा कहा जाता है। परंपरा के अनुसार गौतम ऋषि की तपस्या से शिव ने अपनी जटाओं से गंगा को मुक्त किया और वे यहाँ गोदावरी के रूप में उतरीं।

## दो स्थान, एक कुंभ

सिंहस्थ की विशेषता है कि यह लगभग 30 किमी दूर दो नगरों में होता है। नाशिक और त्र्यंबकेश्वर दोनों इसके आयोजक हैं और अखाड़े दोनों में बँटे होते हैं।

!info 2027 का सिंहस्थ 31 अक्टूबर 2026 को ध्वजारोहण से शुरू होकर 24 जुलाई 2028 तक चलेगा। मुख्य स्नान दिवस अगस्त और सितंबर 2027 में हैं।"""),
        "mr": ("सिंहस्थ म्हणजे काय आणि नाशिकच का?", "नाव आकाशातून येते, स्थान नदीतून.",
"""सिंहस्थ म्हणजे "सिंह राशीत". नाशिक आणि त्र्यंबकेश्वरच्या कुंभाला हे नाव मिळाले कारण तो गुरू सिंह राशीत प्रवेश करतो तेव्हा होतो.

## गोदावरी

येथील कुंभ गोदावरीचा आहे. ही नदी त्र्यंबकेश्वरच्या ब्रह्मगिरी पर्वतावर उगम पावते आणि तिला दक्षिण गंगा म्हणतात. परंपरेनुसार गौतम ऋषींच्या तपश्चर्येमुळे शिवांनी आपल्या जटांतून गंगेला मुक्त केले आणि ती येथे गोदावरी म्हणून अवतरली.

## दोन ठिकाणे, एक कुंभ

सिंहस्थाचे वैशिष्ट्य म्हणजे तो साधारण 30 किमी अंतरावरील दोन गावांत होतो. नाशिक आणि त्र्यंबकेश्वर दोन्ही त्याचे यजमान आहेत आणि आखाडे दोन्हीकडे विभागले जातात.

!info 2027 चा सिंहस्थ 31 ऑक्टोबर 2026 रोजी ध्वजारोहणाने सुरू होऊन 24 जुलै 2028 पर्यंत चालेल. मुख्य स्नान दिवस ऑगस्ट आणि सप्टेंबर 2027 मध्ये आहेत."""),
    },
    {
        "slug": "four-kumbh-cities", "section": "understanding", "cover": "sadhu-after-snan",
        "sources": ["nashik_gov", "kumbh_astro", "unesco"],
        "en": ("Four cities, one tradition", "How the Kumbh differs between Haridwar, Prayagraj, Ujjain and Nashik.",
"""Each Kumbh has its own river and its own moment in the sky. The Maha Kumbh portal sets them out this way.

- Haridwar, on the Ganga: Jupiter in Aquarius, and the Sun in Aries.
- Prayagraj, at the Sangam: the Sun in Capricorn, with Jupiter in Aries or Taurus.
- Ujjain, on the Shipra: Jupiter in Leo with the Sun in Aries, or Jupiter in Libra at Kartik Amavasya.
- Nashik, on the Godavari: Jupiter in Leo.

## What sets Nashik apart

At Prayagraj the Akhadas bathe at one place. In Nashik district, an arrangement made by the Peshwas means Vaishnava Akhadas bathe at Nashik, while Shaiva and Udasin Akhadas bathe at Trimbakeshwar."""),
        "hi": ("चार नगर, एक परंपरा", "हरिद्वार, प्रयागराज, उज्जैन और नाशिक का कुंभ कैसे अलग है।",
"""हर कुंभ की अपनी नदी और आकाश का अपना योग होता है। महाकुंभ पोर्टल इन्हें इस प्रकार बताता है।

- हरिद्वार, गंगा तट: बृहस्पति कुंभ राशि में और सूर्य मेष में।
- प्रयागराज, संगम: सूर्य मकर में और बृहस्पति मेष या वृषभ में।
- उज्जैन, शिप्रा तट: बृहस्पति सिंह में और सूर्य मेष में, या कार्तिक अमावस्या पर बृहस्पति तुला में।
- नाशिक, गोदावरी तट: बृहस्पति सिंह राशि में।

## नाशिक की विशेषता

प्रयागराज में अखाड़े एक ही स्थान पर स्नान करते हैं। नाशिक ज़िले में पेशवाओं की व्यवस्था के कारण वैष्णव अखाड़े नाशिक में और शैव व उदासीन अखाड़े त्र्यंबकेश्वर में स्नान करते हैं।"""),
        "mr": ("चार शहरे, एक परंपरा", "हरिद्वार, प्रयागराज, उज्जैन आणि नाशिकचा कुंभ कसा वेगळा आहे.",
"""प्रत्येक कुंभाची स्वतःची नदी आणि आकाशातील स्वतःचा योग असतो. महाकुंभ पोर्टल ते असे सांगते.

- हरिद्वार, गंगा किनारा: गुरू कुंभ राशीत आणि सूर्य मेषेत.
- प्रयागराज, संगम: सूर्य मकरेत आणि गुरू मेष किंवा वृषभेत.
- उज्जैन, शिप्रा किनारा: गुरू सिंहेत आणि सूर्य मेषेत, किंवा कार्तिक अमावास्येला गुरू तुळेत.
- नाशिक, गोदावरी किनारा: गुरू सिंह राशीत.

## नाशिकचे वेगळेपण

प्रयागराजमध्ये आखाडे एकाच ठिकाणी स्नान करतात. नाशिक जिल्ह्यात पेशव्यांच्या व्यवस्थेमुळे वैष्णव आखाडे नाशिकमध्ये आणि शैव व उदासीन आखाडे त्र्यंबकेश्वर येथे स्नान करतात."""),
    },
    {
        "slug": "history-of-nashik-kumbh", "section": "history", "cover": "kushavarta-crowd",
        "sources": ["nashik_gov", "jacobsen", "pti"], "akhadas": ["juna", "nirmohi"],
        "en": ("A Kumbh in two towns", "How a dispute over bathing order shaped the Simhastha we know.",
"""The Simhastha is held on the Godavari at both Nashik and Trimbakeshwar, and that division has a history.

## The Peshwa's arrangement

Scholars record a clash between Shaiva sannyasis and Vaishnava bairagis in 1789 over who should bathe first. The Maratha Peshwa then moved the Vaishnava bath to Ramkund in Nashik, leaving Trimbak to the Shaiva ascetics. The Nashik district administration describes the same outcome: Vaishnava Akhadas bathe at Nashik, Shaiva and Udasin Akhadas at Trimbakeshwar.

!info The Akhadas & Sadhus section explains who these orders are, and profiles each of them.

## In living memory

The last Simhastha here was held in 2015–16. Planning for the next is led by the Nashik–Trimbakeshwar Kumbh Mela Authority, a body set up by the Government of Maharashtra."""),
        "hi": ("दो नगरों का एक कुंभ", "स्नान के क्रम के विवाद ने सिंहस्थ का आज का रूप कैसे बनाया।",
"""सिंहस्थ गोदावरी तट पर नाशिक और त्र्यंबकेश्वर दोनों में होता है और इस विभाजन का अपना इतिहास है।

## पेशवा की व्यवस्था

विद्वानों के अनुसार 1789 में शैव संन्यासियों और वैष्णव बैरागियों में पहले स्नान को लेकर संघर्ष हुआ। इसके बाद मराठा पेशवा ने वैष्णव स्नान को नाशिक के रामकुंड में स्थानांतरित किया और त्र्यंबक शैव संन्यासियों के लिए रहा। नाशिक ज़िला प्रशासन भी यही बताता है: वैष्णव अखाड़े नाशिक में, शैव और उदासीन अखाड़े त्र्यंबकेश्वर में स्नान करते हैं।

!info अखाड़े और साधु अनुभाग में इन संगठनों का परिचय और प्रत्येक की जानकारी है।

## निकट अतीत

पिछला सिंहस्थ यहाँ 2015–16 में हुआ था। अगले की योजना नाशिक–त्र्यंबकेश्वर कुंभ मेला प्राधिकरण बना रहा है, जिसे महाराष्ट्र सरकार ने गठित किया है।"""),
        "mr": ("दोन गावांचा एक कुंभ", "स्नानाच्या क्रमावरील वादाने आजचा सिंहस्थ कसा घडवला.",
"""सिंहस्थ गोदावरीकाठी नाशिक आणि त्र्यंबकेश्वर दोन्ही ठिकाणी होतो आणि या विभागणीला इतिहास आहे.

## पेशव्यांची व्यवस्था

विद्वानांच्या नोंदीनुसार 1789 मध्ये शैव संन्यासी आणि वैष्णव बैरागी यांच्यात आधी स्नान कोणी करायचे यावरून संघर्ष झाला. त्यानंतर मराठा पेशव्यांनी वैष्णव स्नान नाशिकच्या रामकुंडावर हलवले आणि त्र्यंबक शैव संन्याशांसाठी राहिले. नाशिक जिल्हा प्रशासनही हेच सांगते: वैष्णव आखाडे नाशिकमध्ये, शैव आणि उदासीन आखाडे त्र्यंबकेश्वर येथे स्नान करतात.

!info आखाडे आणि साधू विभागात या संघटनांची ओळख आणि प्रत्येकाची माहिती आहे.

## अलीकडील काळ

मागील सिंहस्थ येथे 2015–16 मध्ये झाला. पुढच्याचे नियोजन नाशिक–त्र्यंबकेश्वर कुंभमेळा प्राधिकरण करत आहे, जे महाराष्ट्र शासनाने स्थापन केले आहे."""),
    },
    {
        "slug": "history-of-trimbakeshwar", "section": "history", "cover": "trimbakeshwar-mist",
        "sources": ["trust", "nashik_gov"], "temples": ["Trimbakeshwar"],
        "images": {"shikhara": ("trimbak-shikhara", "The temple's shikhara against the hills", "पहाड़ियों के सामने मंदिर का शिखर", "डोंगरांच्या पार्श्वभूमीवर मंदिराचे शिखर")},
        "en": ("Trimbakeshwar, where the Godavari begins", "A Jyotirlinga at the foot of Brahmagiri.",
"""Trimbakeshwar is one of the twelve Jyotirlingas, the most sacred shrines of Shiva. The town lies at the foot of Brahmagiri, the hill from which the Godavari flows.

## The present temple

According to the temple trust, the third Peshwa, Balaji Bajirao, built the present temple on the site of an older one, and it was opened with ceremony on Mahashivaratri, 16 February 1756.

[[image:shikhara]]

## Saints of Trimbak

The town also holds the samadhi of Sant Nivruttinath, and tradition says the sage Gautam made his home here. The Nath tradition remembers Nivruttinath as one of its founders."""),
        "hi": ("त्र्यंबकेश्वर, जहाँ गोदावरी का उद्गम है", "ब्रह्मगिरि की तलहटी में एक ज्योतिर्लिंग।",
"""त्र्यंबकेश्वर बारह ज्योतिर्लिंगों में से एक है, जो शिव के सबसे पवित्र धाम हैं। यह नगर ब्रह्मगिरि की तलहटी में बसा है, जहाँ से गोदावरी निकलती है।

## वर्तमान मंदिर

मंदिर न्यास के अनुसार तीसरे पेशवा बालाजी बाजीराव ने पुराने मंदिर के स्थान पर वर्तमान मंदिर बनवाया और 16 फ़रवरी 1756 को महाशिवरात्रि पर इसका भव्य उद्घाटन हुआ।

[[image:shikhara]]

## त्र्यंबक के संत

नगर में संत निवृत्तिनाथ की समाधि भी है और परंपरा के अनुसार गौतम ऋषि यहीं रहते थे। नाथ परंपरा निवृत्तिनाथ को अपने संस्थापकों में गिनती है।"""),
        "mr": ("त्र्यंबकेश्वर, जिथे गोदावरीचा उगम होतो", "ब्रह्मगिरीच्या पायथ्याशी एक ज्योतिर्लिंग.",
"""त्र्यंबकेश्वर हे बारा ज्योतिर्लिंगांपैकी एक आहे, जी शिवांची सर्वात पवित्र स्थाने आहेत. हे गाव ब्रह्मगिरीच्या पायथ्याशी वसले आहे, जिथून गोदावरी वाहते.

## सध्याचे मंदिर

मंदिर न्यासानुसार तिसरे पेशवे बाळाजी बाजीराव यांनी जुन्या मंदिराच्या जागी सध्याचे मंदिर बांधले आणि 16 फेब्रुवारी 1756 रोजी महाशिवरात्रीला त्याचे भव्य उद्घाटन झाले.

[[image:shikhara]]

## त्र्यंबकचे संत

गावात संत निवृत्तिनाथांची समाधी आहे आणि परंपरेनुसार गौतम ऋषी येथेच राहत. नाथ परंपरा निवृत्तिनाथांना आपल्या संस्थापकांपैकी एक मानते."""),
    },
    {
        "slug": "panchavati-and-ramkund", "section": "history", "cover": "kalaram",
        "sources": ["wiki_panchavati", "wiki_kalaram", "nashik_gov"], "temples": ["Kala Rama"],
        "en": ("Panchavati: the forest of five banyans", "Where the Ramayana meets the Godavari.",
"""Panchavati is the old heart of Nashik, on the banks of the Godavari. The name joins pancha, five, and vati, banyan: a grove of five sacred banyan trees.

Tradition holds that Rama, Sita and Lakshmana lived here during their exile, and it is from this story that much of Nashik's sacred geography takes its names.

## A living quarter

Today Panchavati holds Ramkund, the Kalaram temple and many smaller shrines within walking distance. It is also where the Vaishnava Akhadas bathe during the Simhastha.

> The area around Panchavati is considered sacred, and features several temples and holy sites."""),
        "hi": ("पंचवटी: पाँच वटवृक्षों का वन", "जहाँ रामायण गोदावरी से मिलती है।",
"""पंचवटी गोदावरी तट पर बसा नाशिक का पुराना केंद्र है। यह नाम पंच यानी पाँच और वट यानी बरगद से बना है: पाँच पवित्र वटवृक्षों का समूह।

परंपरा के अनुसार राम, सीता और लक्ष्मण ने वनवास का समय यहाँ बिताया। नाशिक के कई पवित्र स्थलों के नाम इसी कथा से आते हैं।

## एक जीवंत क्षेत्र

आज पंचवटी में रामकुंड, कालाराम मंदिर और कई छोटे मंदिर पैदल दूरी पर हैं। सिंहस्थ में वैष्णव अखाड़े यहीं स्नान करते हैं।

> पंचवटी का क्षेत्र पवित्र माना जाता है और यहाँ कई मंदिर व तीर्थ हैं।"""),
        "mr": ("पंचवटी: पाच वटवृक्षांचे वन", "जिथे रामायण गोदावरीला भेटते.",
"""पंचवटी हे गोदावरीकाठचे नाशिकचे जुने केंद्र आहे. हे नाव पंच म्हणजे पाच आणि वट म्हणजे वड यांपासून बनले आहे: पाच पवित्र वटवृक्षांचा समूह.

परंपरेनुसार राम, सीता आणि लक्ष्मण यांनी वनवासाचा काळ येथे घालवला. नाशिकमधील अनेक पवित्र स्थळांची नावे याच कथेतून आली आहेत.

## एक जिवंत परिसर

आज पंचवटीत रामकुंड, काळाराम मंदिर आणि अनेक लहान मंदिरे चालत जाण्याच्या अंतरावर आहेत. सिंहस्थात वैष्णव आखाडे येथेच स्नान करतात.

> पंचवटीचा परिसर पवित्र मानला जातो आणि येथे अनेक मंदिरे व तीर्थे आहेत."""),
    },
    {
        "slug": "amrit-snan-explained", "section": "rituals", "cover": "nirmal-shahi",
        "sources": ["pti", "nashik_gov"], "akhadas": ["juna", "nirmohi", "nirmal"],
        "en": ("Amrit Snan: the sacred bath", "The moment the whole Simhastha turns towards.",
"""Amrit Snan is the bath of the Akhadas on the main days of the Kumbh. Saints go to the river in procession, in an order settled with the authorities, and pilgrims bathe after them.

Long called Shahi Snan, the royal bath, it was renamed Amrit Snan for this Simhastha at the planning meeting of June 2025.

## Dates for 2027

- First Amrit Snan: 2 August 2027
- Second Amrit Snan: 31 August 2027
- Third Amrit Snan: 11 September 2027 at Nashik and 12 September at Trimbakeshwar

!warn These dates were reported from the June 2025 meeting. Confirm them with official announcements before you book travel."""),
        "hi": ("अमृत स्नान: पवित्र स्नान", "वह क्षण जिसकी ओर पूरा सिंहस्थ बढ़ता है।",
"""अमृत स्नान कुंभ के मुख्य दिनों पर अखाड़ों का स्नान है। संत प्रशासन से तय क्रम में शोभायात्रा के साथ नदी तक जाते हैं और उनके बाद श्रद्धालु स्नान करते हैं।

इसे लंबे समय तक शाही स्नान कहा जाता था। जून 2025 की योजना बैठक में इस सिंहस्थ के लिए इसका नाम अमृत स्नान रखा गया।

## 2027 की तिथियाँ

- पहला अमृत स्नान: 2 अगस्त 2027
- दूसरा अमृत स्नान: 31 अगस्त 2027
- तीसरा अमृत स्नान: 11 सितंबर 2027 नाशिक में और 12 सितंबर त्र्यंबकेश्वर में

!warn ये तिथियाँ जून 2025 की बैठक की रिपोर्टों से हैं। यात्रा बुक करने से पहले आधिकारिक घोषणाओं से पुष्टि करें।"""),
        "mr": ("अमृत स्नान: पवित्र स्नान", "तो क्षण ज्याकडे संपूर्ण सिंहस्थ वळतो.",
"""अमृत स्नान म्हणजे कुंभाच्या मुख्य दिवशी आखाड्यांचे स्नान. संत प्रशासनाशी ठरलेल्या क्रमाने मिरवणुकीने नदीवर जातात आणि त्यांच्यानंतर भाविक स्नान करतात.

याला दीर्घकाळ शाही स्नान म्हटले जात होते. जून 2025 च्या नियोजन बैठकीत या सिंहस्थासाठी त्याचे नाव अमृत स्नान ठेवण्यात आले.

## 2027 च्या तारखा

- पहिले अमृत स्नान: 2 ऑगस्ट 2027
- दुसरे अमृत स्नान: 31 ऑगस्ट 2027
- तिसरे अमृत स्नान: 11 सप्टेंबर 2027 नाशिकमध्ये आणि 12 सप्टेंबर त्र्यंबकेश्वर येथे

!warn या तारखा जून 2025 च्या बैठकीच्या वृत्तांतून आहेत. प्रवास आरक्षित करण्यापूर्वी अधिकृत घोषणांवरून खात्री करा."""),
    },
    {
        "slug": "dhwajarohan", "section": "rituals", "cover": "ramkund-sankranti",
        "sources": ["pudhari_flag", "pti"],
        "en": ("Dhwajarohan: raising the flag", "The Simhastha begins not with a bath, but with a flag.",
"""Dhwajarohan is the hoisting of the flag that opens the Simhastha, at Ramkund in Nashik and at Trimbakeshwar. In 2026 it falls on 31 October, and the flag comes down on 24 July 2028.

## What the flag means

A report in Pudhari explains the symbols: the lion for valour, saffron for sacrifice, and the sun and moon as a sign that the Kumbh endures as long as they do.

Akhadas also raise their own flags when they camp, to mark their presence and the start of their rituals."""),
        "hi": ("ध्वजारोहण: ध्वज फहराना", "सिंहस्थ स्नान से नहीं, ध्वज से शुरू होता है।",
"""ध्वजारोहण वह अनुष्ठान है जिससे सिंहस्थ का आरंभ होता है। यह नाशिक के रामकुंड और त्र्यंबकेश्वर में होता है। 2026 में यह 31 अक्टूबर को है और ध्वज 24 जुलाई 2028 को उतरेगा।

## ध्वज का अर्थ

पुढारी की एक रिपोर्ट इसके प्रतीक बताती है: सिंह पराक्रम का, भगवा त्याग का, और सूर्य-चंद्र इस बात का कि कुंभ उनके रहने तक चलता रहेगा।

अखाड़े भी शिविर लगाने पर अपने ध्वज फहराते हैं, जिससे उनकी उपस्थिति और अनुष्ठानों का आरंभ होता है।"""),
        "mr": ("ध्वजारोहण: ध्वज उभारणे", "सिंहस्थ स्नानाने नव्हे, ध्वजाने सुरू होतो.",
"""ध्वजारोहण हा तो विधी आहे ज्याने सिंहस्थाची सुरुवात होते. तो नाशिकच्या रामकुंडावर आणि त्र्यंबकेश्वर येथे होतो. 2026 मध्ये तो 31 ऑक्टोबरला आहे आणि ध्वज 24 जुलै 2028 रोजी उतरेल.

## ध्वजाचा अर्थ

पुढारीच्या एका वृत्तात त्याची प्रतीके सांगितली आहेत: सिंह पराक्रमाचे, भगवा त्यागाचे, आणि सूर्य-चंद्र हे की ते असेपर्यंत कुंभ चालत राहील.

आखाडेही शिबिर उभारताना आपले ध्वज उभारतात, ज्यातून त्यांची उपस्थिती आणि विधींची सुरुवात दर्शवली जाते."""),
    },
    {
        "slug": "nagar-pradakshina", "section": "rituals", "cover": "tableau",
        "sources": ["pti", "fpj_parikrama"],
        "en": ("Nagar Pradakshina: walking the town", "A sacred circuit through the streets of Nashik.",
"""Pradakshina means walking around something sacred. In a Nagar Pradakshina, the whole town becomes the circuit.

Before the 2026 flag hoisting, a procession left Modi Ground in Tapovan and passed through Panchavati, the old city and the market streets to Ramkund. A palanquin carried the religious flag, the sacred Kumbh and an idol of Goddess Godavari, and an aarti followed at the river.

!info A Nagar Pradakshina is reported for 29 July 2027. Check official announcements for the route."""),
        "hi": ("नगर प्रदक्षिणा: नगर की परिक्रमा", "नाशिक की गलियों से होकर एक पवित्र परिक्रमा।",
"""प्रदक्षिणा का अर्थ है किसी पवित्र वस्तु की परिक्रमा करना। नगर प्रदक्षिणा में पूरा नगर ही परिक्रमा पथ बन जाता है।

2026 के ध्वजारोहण से पहले तपोवन के मोदी मैदान से शोभायात्रा निकली और पंचवटी, पुराने शहर और बाज़ार की गलियों से होकर रामकुंड पहुँची। पालकी में धर्मध्वज, पवित्र कुंभ और देवी गोदावरी की मूर्ति थी और नदी पर आरती हुई।

!info 29 जुलाई 2027 को नगर प्रदक्षिणा की जानकारी है। मार्ग के लिए आधिकारिक घोषणाएँ देखें।"""),
        "mr": ("नगर प्रदक्षिणा: नगराची परिक्रमा", "नाशिकच्या रस्त्यांतून एक पवित्र परिक्रमा.",
"""प्रदक्षिणा म्हणजे पवित्र वस्तूभोवती फेरी. नगर प्रदक्षिणेत संपूर्ण नगरच परिक्रमेचा मार्ग बनते.

2026 च्या ध्वजारोहणापूर्वी तपोवनातील मोदी मैदानातून मिरवणूक निघाली आणि पंचवटी, जुने शहर व बाजारपेठेतून रामकुंडावर पोहोचली. पालखीत धर्मध्वज, पवित्र कुंभ आणि देवी गोदावरीची मूर्ती होती आणि नदीवर आरती झाली.

!info 29 जुलै 2027 रोजी नगर प्रदक्षिणेची माहिती आहे. मार्गासाठी अधिकृत घोषणा पहा."""),
    },
    {
        "slug": "first-time-at-kumbh", "section": "guides", "kind": "guide", "editorial": True, "cover": "sadhus-nashik",
        "sources": ["ntkma_about", "pti"],
        "en": ("Your first Kumbh", "What to expect, and how to enjoy it calmly.",
"""A Kumbh is unlike any other crowd. Expect long walks, closed roads on main bathing days, and very early starts. The Kumbh Authority and police decide what is open on any day, so plans need room to change.

## Before you travel

- Choose your dates around the bathing days, not only on them.
- Book travel and stay early, using official or trusted services.
- Save the emergency number 112.

## On the day

- Agree a meeting point with your group before you enter a crowd.
- Keep an ID and a contact number on everyone, especially children and elders.
- Follow barricades, police and volunteers. Routes change for safety.

!info This is our own guidance. The Plan tab can build your day-by-day itinerary."""),
        "hi": ("आपका पहला कुंभ", "क्या अपेक्षा करें और शांति से इसका आनंद कैसे लें।",
"""कुंभ की भीड़ किसी और भीड़ जैसी नहीं होती। लंबी पैदल यात्रा, मुख्य स्नान दिवसों पर बंद सड़कें और बहुत सुबह की शुरुआत के लिए तैयार रहें। किस दिन क्या खुला है, यह कुंभ प्राधिकरण और पुलिस तय करते हैं, इसलिए योजना में बदलाव की गुंजाइश रखें।

## यात्रा से पहले

- तिथियाँ केवल स्नान के दिन नहीं, उनके आसपास चुनें।
- यात्रा और ठहराव जल्दी, आधिकारिक या भरोसेमंद सेवाओं से बुक करें।
- आपातकालीन नंबर 112 सहेज लें।

## उस दिन

- भीड़ में जाने से पहले समूह के साथ मिलने का स्थान तय करें।
- सबके पास पहचान पत्र और संपर्क नंबर रखें, ख़ासकर बच्चों और बुज़ुर्गों के पास।
- बैरिकेड, पुलिस और स्वयंसेवकों का पालन करें। सुरक्षा के लिए मार्ग बदलते हैं।

!info यह हमारा अपना मार्गदर्शन है। योजना टैब आपके लिए दिन-प्रतिदिन की यात्रा योजना बना सकता है।"""),
        "mr": ("तुमचा पहिला कुंभ", "काय अपेक्षित आहे आणि शांतपणे आनंद कसा घ्यावा.",
"""कुंभातील गर्दी इतर कोणत्याही गर्दीसारखी नसते. लांब चालणे, मुख्य स्नान दिवशी बंद रस्ते आणि पहाटेची सुरुवात यासाठी तयार रहा. कोणत्या दिवशी काय सुरू आहे हे कुंभ प्राधिकरण आणि पोलीस ठरवतात, म्हणून नियोजनात बदलाला जागा ठेवा.

## प्रवासापूर्वी

- तारखा फक्त स्नानाच्या दिवशी नव्हे, त्यांच्या आसपास निवडा.
- प्रवास आणि निवास लवकर, अधिकृत किंवा विश्वासार्ह सेवांमधून आरक्षित करा.
- आपत्कालीन क्रमांक 112 जतन करा.

## त्या दिवशी

- गर्दीत जाण्यापूर्वी गटासोबत भेटण्याचे ठिकाण ठरवा.
- सर्वांकडे ओळखपत्र आणि संपर्क क्रमांक ठेवा, विशेषतः मुले आणि ज्येष्ठांकडे.
- बॅरिकेड, पोलीस आणि स्वयंसेवकांच्या सूचना पाळा. सुरक्षेसाठी मार्ग बदलतात.

!info हे आमचे स्वतःचे मार्गदर्शन आहे. नियोजन टॅब तुमचा दिवसनिहाय कार्यक्रम तयार करू शकतो."""),
    },
    {
        "slug": "what-to-carry", "section": "guides", "kind": "guide", "editorial": True, "cover": "sadhu-trimbak",
        "sources": ["ntkma_about"],
        "en": ("What to carry", "A light bag makes a long day easier.",
"""Carry little, and carry it close. You may walk far from any vehicle.

- A government ID for each person, and a paper copy of contact numbers.
- Any regular medicines, with the prescription.
- Water, a dry snack and a small towel.
- Comfortable footwear you can slip off, and a plastic bag for it.
- A change of clothes for after the bath, kept dry.
- A power bank, because networks and charging may be hard to find.

!warn Leave valuables and large bags behind. Check the current rules on what's allowed near the ghats."""),
        "hi": ("क्या साथ रखें", "हल्का बैग लंबे दिन को आसान बनाता है।",
"""कम सामान रखें और उसे अपने पास रखें। हो सकता है वाहन से दूर तक पैदल चलना पड़े।

- हर व्यक्ति का सरकारी पहचान पत्र और संपर्क नंबरों की काग़ज़ी प्रति।
- नियमित दवाएँ, पर्चे के साथ।
- पानी, सूखा नाश्ता और छोटा तौलिया।
- आरामदायक चप्पल-जूते जिन्हें आसानी से उतारा जा सके और उनके लिए एक थैली।
- स्नान के बाद के लिए सूखे कपड़े।
- पावर बैंक, क्योंकि नेटवर्क और चार्जिंग मुश्किल हो सकते हैं।

!warn क़ीमती सामान और बड़े बैग न लाएँ। घाटों के पास क्या ले जा सकते हैं, इसके वर्तमान नियम जाँच लें।"""),
        "mr": ("सोबत काय ठेवावे", "हलकी बॅग लांब दिवस सोपा करते.",
"""कमी सामान ठेवा आणि ते जवळ ठेवा. वाहनापासून लांब चालावे लागू शकते.

- प्रत्येकाचे सरकारी ओळखपत्र आणि संपर्क क्रमांकांची कागदी प्रत.
- नियमित औषधे, प्रिस्क्रिप्शनसह.
- पाणी, सुका खाऊ आणि लहान टॉवेल.
- सहज काढता येणारी आरामदायक पादत्राणे आणि त्यासाठी पिशवी.
- स्नानानंतरचे कोरडे कपडे.
- पॉवर बँक, कारण नेटवर्क आणि चार्जिंग अवघड असू शकते.

!warn मौल्यवान वस्तू आणि मोठ्या बॅगा आणू नका. घाटांजवळ काय नेता येते याचे सध्याचे नियम तपासा."""),
    },
    {
        "slug": "travelling-with-family-and-elders", "section": "guides", "kind": "guide", "editorial": True, "cover": "tapovan-rama",
        "sources": ["ntkma_about"],
        "en": ("With children and elders", "Slower days, and a little more planning.",
"""Crowds, heat and long walks fall hardest on the very young and the elderly. Plan fewer things in a day, and rest often.

## With children

- Put a card with your name and phone number in each child's pocket.
- Take a photo of them each morning, so you can show what they're wearing.
- Choose a meeting point they can recognise.

## With seniors

- Avoid the main bathing days if walking is difficult.
- Carry medicines and a list of conditions in a pocket, not a bag.
- Ask volunteers about accessible routes before you set out.

!warn If someone in your group feels unwell in a crowd, move to the side and ask the nearest volunteer or police officer. In any emergency, call 112."""),
        "hi": ("बच्चों और बुज़ुर्गों के साथ", "धीमे दिन और थोड़ी अधिक तैयारी।",
"""भीड़, गर्मी और लंबी पैदल यात्रा का असर बच्चों और बुज़ुर्गों पर सबसे अधिक होता है। दिन में कम काम रखें और बार-बार आराम करें।

## बच्चों के साथ

- हर बच्चे की जेब में आपके नाम और फ़ोन नंबर का कार्ड रखें।
- रोज़ सुबह उनकी फ़ोटो लें, ताकि दिखा सकें कि उन्होंने क्या पहना है।
- ऐसा मिलने का स्थान चुनें जिसे वे पहचान सकें।

## बुज़ुर्गों के साथ

- चलने में कठिनाई हो तो मुख्य स्नान दिवसों से बचें।
- दवाएँ और बीमारियों की सूची बैग में नहीं, जेब में रखें।
- निकलने से पहले स्वयंसेवकों से सुगम मार्गों के बारे में पूछें।

!warn समूह में किसी की तबीयत भीड़ में बिगड़े तो किनारे जाएँ और निकटतम स्वयंसेवक या पुलिस से मदद लें। किसी भी आपात स्थिति में 112 पर कॉल करें।"""),
        "mr": ("मुले आणि ज्येष्ठांसोबत", "सावकाश दिवस आणि थोडे अधिक नियोजन.",
"""गर्दी, उष्णता आणि लांब चालण्याचा सर्वाधिक त्रास लहान मुलांना आणि ज्येष्ठांना होतो. दिवसात कमी गोष्टी ठेवा आणि वारंवार विश्रांती घ्या.

## मुलांसोबत

- प्रत्येक मुलाच्या खिशात तुमचे नाव आणि फोन क्रमांक असलेले कार्ड ठेवा.
- रोज सकाळी त्यांचा फोटो घ्या, म्हणजे त्यांनी काय घातले आहे ते दाखवता येईल.
- त्यांना ओळखता येईल असे भेटण्याचे ठिकाण निवडा.

## ज्येष्ठांसोबत

- चालणे अवघड असल्यास मुख्य स्नान दिवस टाळा.
- औषधे आणि आजारांची यादी बॅगेत नव्हे, खिशात ठेवा.
- निघण्यापूर्वी स्वयंसेवकांना सुलभ मार्गांबद्दल विचारा.

!warn गटातील कोणाला गर्दीत अस्वस्थ वाटल्यास बाजूला जा आणि जवळच्या स्वयंसेवक किंवा पोलिसांची मदत घ्या. कोणत्याही आणीबाणीत 112 वर कॉल करा."""),
    },
    {
        "slug": "at-ramkund", "section": "places", "kind": "place", "cover": "ramkund-sankranti",
        "sources": ["nashik_gov", "wiki_kalaram", "jacobsen"], "temples": ["Kala Rama"],
        "en": ("Ramkund", "The sacred bathing tank of Nashik, on the Godavari.",
"""Ramkund is the principal bathing place in Nashik, on the Godavari in Panchavati. During the Simhastha it is where the Vaishnava Akhadas bathe.

Tradition links it with Rama, and devotees believe that bathing in the Godavari frees them from past sins. On festival days the steps fill with families at the water's edge.

!warn Water levels and access change, and works are under way for the Kumbh. Follow signs and instructions at the ghat."""),
        "hi": ("रामकुंड", "गोदावरी पर नाशिक का पवित्र स्नान कुंड।",
"""रामकुंड पंचवटी में गोदावरी पर नाशिक का प्रमुख स्नान स्थल है। सिंहस्थ में वैष्णव अखाड़े यहीं स्नान करते हैं।

परंपरा इसे राम से जोड़ती है और श्रद्धालु मानते हैं कि गोदावरी में स्नान से पूर्व पाप दूर होते हैं। पर्वों पर सीढ़ियाँ जल के किनारे परिवारों से भर जाती हैं।

!warn जल स्तर और पहुँच बदलती रहती है और कुंभ के कार्य चल रहे हैं। घाट के संकेतों और निर्देशों का पालन करें।"""),
        "mr": ("रामकुंड", "गोदावरीवरील नाशिकचे पवित्र स्नान कुंड.",
"""रामकुंड हे पंचवटीत गोदावरीवरील नाशिकचे प्रमुख स्नानस्थळ आहे. सिंहस्थात वैष्णव आखाडे येथेच स्नान करतात.

परंपरा त्याला रामांशी जोडते आणि गोदावरीत स्नान केल्याने पूर्वीची पापे दूर होतात, अशी भाविकांची श्रद्धा आहे. सणांच्या दिवशी पायऱ्या पाण्याजवळ कुटुंबांनी भरून जातात.

!warn पाण्याची पातळी आणि प्रवेश बदलत असतात आणि कुंभाची कामे सुरू आहेत. घाटावरील फलक आणि सूचनांचे पालन करा."""),
    },
    {
        "slug": "kushavarta-tirtha", "section": "places", "kind": "place", "cover": "kushavarta-crowd",
        "sources": ["pti", "nashik_gov"], "temples": ["Trimbakeshwar"],
        "en": ("Kushavarta Tirtha", "The sacred tank of Trimbakeshwar.",
"""Kushavarta is the sacred tank at Trimbakeshwar, and devotees bathe here in the waters of the Godavari. During the Simhastha, Shaiva and Udasin Akhadas bathe at Trimbakeshwar, and crowd management here is a major part of planning."""),
        "hi": ("कुशावर्त तीर्थ", "त्र्यंबकेश्वर का पवित्र कुंड।",
"""कुशावर्त त्र्यंबकेश्वर का पवित्र कुंड है, जहाँ श्रद्धालु गोदावरी के जल में स्नान करते हैं। सिंहस्थ में शैव और उदासीन अखाड़े त्र्यंबकेश्वर में स्नान करते हैं और यहाँ भीड़ प्रबंधन योजना का बड़ा हिस्सा है।"""),
        "mr": ("कुशावर्त तीर्थ", "त्र्यंबकेश्वरचे पवित्र कुंड.",
"""कुशावर्त हे त्र्यंबकेश्वरचे पवित्र कुंड आहे, जिथे भाविक गोदावरीच्या पाण्यात स्नान करतात. सिंहस्थात शैव आणि उदासीन आखाडे त्र्यंबकेश्वर येथे स्नान करतात आणि येथील गर्दी व्यवस्थापन हा नियोजनाचा मोठा भाग आहे."""),
    },
    {
        "slug": "kalaram-temple", "section": "places", "kind": "place", "cover": "kalaram",
        "sources": ["wiki_kalaram"], "temples": ["Kala Rama"],
        "en": ("Kalaram Temple", "Black stone and a turning point in social history.",
"""The Kalaram temple stands in Panchavati, and takes its name from its dark image of Rama. Sources credit Sardar Rangarao Odhekar with building it in the late 18th century, though they differ on the exact year.

The sanctum holds images of Rama, Sita and Lakshmana. In March 1930, B. R. Ambedkar led a satyagraha here for the entry of Dalits to the temple, one of the landmark protests of its time."""),
        "hi": ("कालाराम मंदिर", "काला पत्थर और सामाजिक इतिहास का एक मोड़।",
"""कालाराम मंदिर पंचवटी में है और इसका नाम राम की श्याम प्रतिमा से पड़ा। स्रोतों के अनुसार इसे सरदार रंगराव ओढेकर ने 18वीं शताब्दी के अंत में बनवाया, हालाँकि सही वर्ष पर मत अलग हैं।

गर्भगृह में राम, सीता और लक्ष्मण की प्रतिमाएँ हैं। मार्च 1930 में बी. आर. आंबेडकर ने दलितों के मंदिर प्रवेश के लिए यहाँ सत्याग्रह किया, जो अपने समय का एक ऐतिहासिक आंदोलन था।"""),
        "mr": ("काळाराम मंदिर", "काळा पाषाण आणि सामाजिक इतिहासातील एक वळण.",
"""काळाराम मंदिर पंचवटीत आहे आणि त्याचे नाव रामांच्या श्यामल मूर्तीवरून पडले. स्रोतांनुसार सरदार रंगराव ओढेकर यांनी ते 18 व्या शतकाच्या अखेरीस बांधले, मात्र नेमक्या वर्षाबाबत मतभेद आहेत.

गाभाऱ्यात राम, सीता आणि लक्ष्मण यांच्या मूर्ती आहेत. मार्च 1930 मध्ये बाबासाहेब आंबेडकर यांनी दलितांच्या मंदिरप्रवेशासाठी येथे सत्याग्रह केला, जे त्या काळातील ऐतिहासिक आंदोलन होते."""),
    },
    {
        "slug": "trimbakeshwar-jyotirlinga", "section": "places", "kind": "place", "cover": "trimbak-shikhara",
        "sources": ["trust", "nashik_gov"], "temples": ["Trimbakeshwar"],
        "en": ("Trimbakeshwar Jyotirlinga", "One of the twelve, about 30 km from Nashik.",
"""One of the twelve Jyotirlingas, the temple stands in Trimbak at the foot of Brahmagiri, close to the source of the Godavari. The temple trust dates its grand opening to Mahashivaratri in 1756."""),
        "hi": ("त्र्यंबकेश्वर ज्योतिर्लिंग", "बारह में से एक, नाशिक से लगभग 30 किमी।",
"""बारह ज्योतिर्लिंगों में से एक यह मंदिर त्र्यंबक में ब्रह्मगिरि की तलहटी में, गोदावरी के उद्गम के पास है। मंदिर न्यास इसका भव्य उद्घाटन 1756 की महाशिवरात्रि को बताता है।"""),
        "mr": ("त्र्यंबकेश्वर ज्योतिर्लिंग", "बारापैकी एक, नाशिकपासून सुमारे 30 किमी.",
"""बारा ज्योतिर्लिंगांपैकी एक असलेले हे मंदिर त्र्यंबक येथे ब्रह्मगिरीच्या पायथ्याशी, गोदावरीच्या उगमाजवळ आहे. मंदिर न्यास त्याचे भव्य उद्घाटन 1756 च्या महाशिवरात्रीला झाल्याचे सांगतो."""),
    },
    {
        "slug": "sita-gufa", "section": "places", "kind": "place", "cover": "sita-gufa", "unverified": True,
        "sources": ["wiki_kalaram"],
        "en": ("Sita Gufa", "A cave in Panchavati, remembered in the Ramayana tradition.",
"""Sita Gufa, or Sita's cave, is a shrine in Panchavati, near the Kalaram temple. Local tradition connects it with Sita's time in the forest during the exile.

!info We haven't yet found an official description of this site, so treat this as tradition, not history."""),
        "hi": ("सीता गुफा", "पंचवटी की एक गुफा, जो रामायण परंपरा में स्मरणीय है।",
"""सीता गुफा पंचवटी में कालाराम मंदिर के पास एक तीर्थ है। स्थानीय परंपरा इसे वनवास में सीता के समय से जोड़ती है।

!info हमें अभी इस स्थल का आधिकारिक विवरण नहीं मिला है, इसलिए इसे इतिहास नहीं, परंपरा मानें।"""),
        "mr": ("सीता गुंफा", "पंचवटीतील एक गुंफा, जी रामायण परंपरेत स्मरणात आहे.",
"""सीता गुंफा हे पंचवटीत काळाराम मंदिराजवळील एक तीर्थ आहे. स्थानिक परंपरा तिला वनवासातील सीतेच्या काळाशी जोडते.

!info आम्हाला अजून या स्थळाचे अधिकृत वर्णन मिळालेले नाही, म्हणून हे इतिहास नव्हे, परंपरा समजा."""),
    },
    {
        "slug": "tapovan", "section": "places", "kind": "place", "cover": "tapovan-rama", "unverified": True,
        "sources": ["fpj_parikrama", "wiki_panchavati"],
        "en": ("Tapovan", "The riverside quarter that becomes a city of saints.",
"""Tapovan lies along the Godavari near Panchavati, and tradition links it with the exile of Rama, Sita and Lakshmana. It is also the area planned for the Sadhugram, where Akhadas camp during the Simhastha.

!info We haven't yet found an official description of this site, so treat the traditions here as tradition, not history. Land for the Sadhugram was still being settled in late 2026."""),
        "hi": ("तपोवन", "नदी किनारे का वह क्षेत्र जो संतों का नगर बन जाता है।",
"""तपोवन पंचवटी के पास गोदावरी के किनारे है और परंपरा इसे राम, सीता और लक्ष्मण के वनवास से जोड़ती है। सिंहस्थ में अखाड़ों के शिविर के लिए साधुग्राम भी इसी क्षेत्र में प्रस्तावित है।

!info हमें अभी इस स्थल का आधिकारिक विवरण नहीं मिला है, इसलिए यहाँ की बातों को इतिहास नहीं, परंपरा मानें। 2026 के अंत तक साधुग्राम की ज़मीन का विषय तय हो रहा था।"""),
        "mr": ("तपोवन", "नदीकाठचा तो परिसर जो संतांचे नगर बनतो.",
"""तपोवन पंचवटीजवळ गोदावरीकाठी आहे आणि परंपरा त्याला राम, सीता आणि लक्ष्मण यांच्या वनवासाशी जोडते. सिंहस्थात आखाड्यांच्या शिबिरांसाठी साधुग्रामही याच परिसरात प्रस्तावित आहे.

!info आम्हाला अजून या स्थळाचे अधिकृत वर्णन मिळालेले नाही, म्हणून येथील गोष्टी इतिहास नव्हे, परंपरा समजा. 2026 च्या अखेरीस साधुग्रामच्या जमिनीचा विषय ठरत होता."""),
    },
]

GLOSSARY = [
    ("simhastha", ["what-is-simhastha"], [], ("Simhastha", "The Kumbh held when Jupiter is in Leo, at Nashik–Trimbakeshwar.", "From Simha, Leo. The name marks the moment in the sky that sets this Kumbh."), ("सिंहस्थ", "बृहस्पति के सिंह राशि में होने पर नाशिक–त्र्यंबकेश्वर में होने वाला कुंभ।", "सिंह राशि से बना शब्द। यह नाम आकाश के उस योग को बताता है जो इस कुंभ का समय तय करता है।"), ("सिंहस्थ", "गुरू सिंह राशीत असताना नाशिक–त्र्यंबकेश्वर येथे होणारा कुंभ.", "सिंह राशीवरून आलेला शब्द. हे नाव आकाशातील त्या योगाला सूचित करते जो या कुंभाची वेळ ठरवतो.")),
    ("amrit-snan", ["amrit-snan-explained"], ["juna"], ("Amrit Snan", "The sacred bath of the Akhadas on the main days of the Kumbh.", "Formerly called Shahi Snan. Saints go to the river first, in an agreed order."), ("अमृत स्नान", "कुंभ के मुख्य दिनों पर अखाड़ों का पवित्र स्नान।", "पहले इसे शाही स्नान कहते थे। संत तय क्रम में सबसे पहले नदी पर जाते हैं।"), ("अमृत स्नान", "कुंभाच्या मुख्य दिवशी आखाड्यांचे पवित्र स्नान.", "पूर्वी याला शाही स्नान म्हणत. संत ठरलेल्या क्रमाने सर्वप्रथम नदीवर जातात.")),
    ("akhada", ["amrit-snan-explained"], ["juna"], ("Akhada", "An order of ascetics with a shared tradition and leadership.", "There are 13 generally recognised Akhadas. See Akhadas & Sadhus for each."), ("अखाड़ा", "साझा परंपरा और नेतृत्व वाला संन्यासियों का संगठन।", "सामान्यतः 13 अखाड़े मान्य हैं। हर एक की जानकारी अखाड़े और साधु अनुभाग में है।"), ("आखाडा", "समान परंपरा आणि नेतृत्व असलेला संन्याशांचा संघ.", "साधारणपणे 13 आखाडे मान्य आहेत. प्रत्येकाची माहिती आखाडे आणि साधू विभागात आहे.")),
    ("naga-sadhu", [], ["juna"], ("Naga Sadhu", "An ascetic of the Shaiva Akhadas, known for strict discipline.", "They walk at the head of processions, and many belong to the Juna Akhara."), ("नागा साधु", "शैव अखाड़ों का तपस्वी, जो कठोर अनुशासन के लिए जाना जाता है।", "वे शोभायात्राओं में आगे चलते हैं और बहुत से जूना अखाड़े से जुड़े हैं।"), ("नागा साधू", "शैव आखाड्यांचा तपस्वी, जो कठोर शिस्तीसाठी ओळखला जातो.", "ते मिरवणुकांत पुढे चालतात आणि अनेक जण जुना आखाड्याचे असतात.")),
    ("mahamandaleshwar", [], [], ("Mahamandaleshwar", "A senior spiritual leader within an Akhada.", "Guides the Akhada's spiritual and organizational life."), ("महामंडलेश्वर", "अखाड़े के वरिष्ठ आध्यात्मिक नेता।", "अखाड़े के आध्यात्मिक और संगठनात्मक जीवन का मार्गदर्शन करते हैं।"), ("महामंडलेश्वर", "आखाड्यातील ज्येष्ठ आध्यात्मिक नेते.", "आखाड्याच्या आध्यात्मिक आणि संघटनात्मक जीवनाला मार्गदर्शन करतात.")),
    ("mahant", [], [], ("Mahant", "A head within an Akhada or monastery.", "Duties differ between Akhadas."), ("महंत", "अखाड़े या मठ के भीतर का प्रमुख।", "दायित्व अखाड़ों में अलग-अलग होते हैं।"), ("महंत", "आखाडा किंवा मठातील प्रमुख.", "जबाबदाऱ्या आखाड्यांनुसार बदलतात.")),
    ("ghat", ["at-ramkund"], [], ("Ghat", "Steps leading down to a river.", "Used for bathing and worship."), ("घाट", "नदी तक उतरने वाली सीढ़ियाँ।", "स्नान और पूजा के लिए उपयोग होती हैं।"), ("घाट", "नदीकडे उतरणाऱ्या पायऱ्या.", "स्नान आणि पूजेसाठी वापरल्या जातात.")),
    ("kund", ["at-ramkund", "kushavarta-tirtha"], [], ("Kund", "A sacred tank or pool.", "Ramkund and Kushavarta are the two best known here."), ("कुंड", "पवित्र जलाशय।", "यहाँ रामकुंड और कुशावर्त सबसे प्रसिद्ध हैं।"), ("कुंड", "पवित्र जलाशय.", "येथे रामकुंड आणि कुशावर्त सर्वात प्रसिद्ध आहेत.")),
    ("tirtha", ["kushavarta-tirtha"], [], ("Tirtha", "A sacred place of pilgrimage, often by water.", "The word suggests a crossing place."), ("तीर्थ", "पवित्र तीर्थस्थान, अक्सर जल के किनारे।", "इस शब्द में पार उतरने के स्थान का भाव है।"), ("तीर्थ", "पवित्र यात्रास्थळ, अनेकदा पाण्याजवळ.", "या शब्दात पार उतरण्याच्या ठिकाणाचा भाव आहे.")),
    ("pradakshina", ["nagar-pradakshina"], [], ("Pradakshina", "Walking around something sacred, keeping it to your right.", "In a Nagar Pradakshina, the circuit is the town."), ("प्रदक्षिणा", "किसी पवित्र वस्तु को दाईं ओर रखते हुए उसकी परिक्रमा।", "नगर प्रदक्षिणा में पूरा नगर परिक्रमा पथ होता है।"), ("प्रदक्षिणा", "पवित्र वस्तूला उजवीकडे ठेवून तिच्याभोवती फेरी.", "नगर प्रदक्षिणेत संपूर्ण नगर हाच मार्ग असतो.")),
    ("dhwajarohan", ["dhwajarohan"], [], ("Dhwajarohan", "The hoisting of the flag that opens the Simhastha.", "Held at Ramkund and Trimbakeshwar."), ("ध्वजारोहण", "ध्वज फहराना, जिससे सिंहस्थ का आरंभ होता है।", "रामकुंड और त्र्यंबकेश्वर में होता है।"), ("ध्वजारोहण", "ध्वज उभारणे, ज्याने सिंहस्थाची सुरुवात होते.", "रामकुंड आणि त्र्यंबकेश्वर येथे होते.")),
]
