"""Learn articles and Nashik activities, loaded by `manage.py seed_akhadas`."""

from datetime import date

ARTICLES = [
    {
        "slug": "what-is-an-akhada", "category": "basics", "position": 1,
        "sources": ["pib_akharas", "kumbh_gurus", "fpj_13", "ani_2025"], "akhadas": ["juna"],
        "en": {
            "title": "What is an Akhada?",
            "intro": "An Akhada is an order of ascetics that shares a tradition, a discipline and a leadership.",
            "body": "Official Kumbh publications trace the word to 'akhand', meaning indivisible. The Akhada brings together followers with similar customs and beliefs.\n\nThe system joined two aims: spiritual learning through scripture and physical defence through martial training. Akhadas remain places of worship, learning and discipline.\n\nThirteen Akhadas are generally recognised today: seven Shaiva, three Vaishnava, and three more usually grouped together, made up of two Udasin Akhadas and the Nirmal Akhada.",
        },
        "hi": {
            "title": "अखाड़ा क्या है?",
            "intro": "अखाड़ा संन्यासियों का ऐसा संगठन है जिसकी परंपरा, अनुशासन और नेतृत्व साझा होते हैं।",
            "body": "कुंभ के आधिकारिक प्रकाशन इस शब्द को 'अखंड' से जोड़ते हैं, जिसका अर्थ है अविभाज्य। अखाड़ा समान रीति और मान्यता वाले अनुयायियों को एक साथ लाता है।\n\nइस व्यवस्था के दो उद्देश्य थे: शास्त्रों से आध्यात्मिक शिक्षा और शस्त्र अभ्यास से शारीरिक रक्षा। अखाड़े आज भी उपासना, अध्ययन और अनुशासन के केंद्र हैं।\n\nआज सामान्यतः तेरह अखाड़े मान्य हैं: सात शैव, तीन वैष्णव और तीन अन्य, जिनमें दो उदासीन अखाड़े और निर्मल अखाड़ा आते हैं।",
        },
        "mr": {
            "title": "आखाडा म्हणजे काय?",
            "intro": "आखाडा हा संन्याशांचा असा संघ आहे ज्याची परंपरा, शिस्त आणि नेतृत्व समान असते.",
            "body": "कुंभाची अधिकृत प्रकाशने हा शब्द 'अखंड' शी जोडतात, ज्याचा अर्थ अविभाज्य असा आहे. आखाडा समान रीती आणि श्रद्धा असलेल्या अनुयायांना एकत्र आणतो.\n\nया व्यवस्थेची दोन उद्दिष्टे होती: शास्त्रांतून आध्यात्मिक शिक्षण आणि शस्त्राभ्यासातून शारीरिक संरक्षण. आखाडे आजही उपासना, अध्ययन आणि शिस्तीची केंद्रे आहेत.\n\nआज साधारणपणे तेरा आखाडे मान्य आहेत: सात शैव, तीन वैष्णव आणि आणखी तीन, ज्यात दोन उदासीन आखाडे आणि निर्मल आखाडा येतात.",
        },
    },
    {
        "slug": "who-are-sadhus", "category": "basics", "position": 2,
        "sources": ["britannica_dashnami", "kumbh_gurus", "pib_akharas"],
        "en": {
            "title": "Who are Sadhus?",
            "intro": "Sadhus are Hindu ascetics who have left ordinary household life for a spiritual path.",
            "body": "Many belong to a recognised order. Shaiva ascetics of the Dashnami tradition, for instance, belong to one of ten orders attributed to Adi Shankaracharya, and each order is attached to one of four monasteries.\n\nTraditions differ in worship, dress and discipline. Women renunciates also take part, and in 2025 the Government of India reported growing numbers being initiated into Akhadas.\n\nNot everyone in saffron belongs to an Akhada. This app lists only people with a public, documented role.",
        },
        "hi": {
            "title": "साधु कौन होते हैं?",
            "intro": "साधु वे हिंदू तपस्वी हैं जिन्होंने सामान्य गृहस्थ जीवन छोड़कर आध्यात्मिक मार्ग अपनाया है।",
            "body": "बहुत से साधु किसी मान्य परंपरा से जुड़े होते हैं। उदाहरण के लिए, दशनामी परंपरा के शैव संन्यासी आदि शंकराचार्य से जोड़ी जाने वाली दस शाखाओं में से किसी एक के होते हैं और हर शाखा चार मठों में से किसी एक से जुड़ी होती है।\n\nपरंपराओं में उपासना, वेश और अनुशासन अलग-अलग होते हैं। महिला संन्यासी भी इसमें शामिल हैं और 2025 में भारत सरकार ने अखाड़ों में उनकी दीक्षा बढ़ने की जानकारी दी।\n\nभगवा पहनने वाला हर व्यक्ति अखाड़े का सदस्य नहीं होता। इस ऐप में केवल सार्वजनिक और प्रलेखित भूमिका वाले लोग शामिल हैं।",
        },
        "mr": {
            "title": "साधू कोण असतात?",
            "intro": "साधू हे असे हिंदू तपस्वी आहेत ज्यांनी सामान्य गृहस्थ जीवन सोडून आध्यात्मिक मार्ग स्वीकारला आहे.",
            "body": "अनेक साधू एखाद्या मान्य परंपरेशी जोडलेले असतात. उदाहरणार्थ, दशनामी परंपरेतील शैव संन्यासी आदि शंकराचार्यांशी जोडल्या जाणाऱ्या दहा शाखांपैकी एकाचे असतात आणि प्रत्येक शाखा चार मठांपैकी एकाशी जोडलेली असते.\n\nपरंपरांमध्ये उपासना, वेश आणि शिस्त वेगवेगळी असते. महिला संन्यासिनीही यात सहभागी आहेत आणि 2025 मध्ये भारत सरकारने आखाड्यांत त्यांची दीक्षा वाढत असल्याची माहिती दिली.\n\nभगवे वस्त्र घालणारी प्रत्येक व्यक्ती आखाड्याची सदस्य नसते. या अॅपमध्ये फक्त सार्वजनिक आणि नोंदलेली भूमिका असलेल्या व्यक्तींचा समावेश आहे.",
        },
    },
    {
        "slug": "who-are-naga-sadhus", "category": "traditions", "position": 3,
        "sources": ["britannica_naga", "pib_akharas", "kumbh_gurus"], "akhadas": ["juna"],
        "en": {
            "title": "Who are Naga Sadhus?",
            "intro": "Naga sadhus are ascetics of the Shaiva Akhadas, known for rigorous discipline and for leading Kumbh processions.",
            "body": "'Naga' refers to their traditional nakedness, a sign of complete renunciation. Britannica describes them as the most militant of the Dashnami ascetics, who in past centuries sometimes fought in battles.\n\nThe Government of India describes them as combining ascetic practice with training in martial arts. They carry traditional weapons such as spears and swords in processions, and the Juna Akhara has the largest number.\n\nFor most pilgrims, the Kumbh is the one chance to see them. Please be respectful: see our article on interacting with Sadhus.",
        },
        "hi": {
            "title": "नागा साधु कौन होते हैं?",
            "intro": "नागा साधु शैव अखाड़ों के तपस्वी हैं, जो कठोर अनुशासन और कुंभ की शोभायात्राओं में अग्रणी भूमिका के लिए जाने जाते हैं।",
            "body": "'नागा' शब्द उनकी पारंपरिक दिगंबर अवस्था को दर्शाता है, जो पूर्ण त्याग का प्रतीक है। ब्रिटानिका उन्हें दशनामी संन्यासियों में सबसे अधिक योद्धा स्वभाव का बताता है, जो बीती शताब्दियों में कभी-कभी युद्धों में शामिल हुए।\n\nभारत सरकार के अनुसार वे तपस्या के साथ शस्त्र अभ्यास भी करते हैं। शोभायात्राओं में वे भाले और तलवार जैसे पारंपरिक शस्त्र लेकर चलते हैं और जूना अखाड़े में उनकी संख्या सबसे अधिक है।\n\nअधिकतर श्रद्धालुओं के लिए कुंभ ही उन्हें देखने का अवसर होता है। कृपया सम्मान रखें: साधुओं से व्यवहार पर हमारा लेख देखें।",
        },
        "mr": {
            "title": "नागा साधू कोण असतात?",
            "intro": "नागा साधू हे शैव आखाड्यांचे तपस्वी आहेत, जे कठोर शिस्त आणि कुंभ मिरवणुकांतील अग्रभागी भूमिकेसाठी ओळखले जातात.",
            "body": "'नागा' हा शब्द त्यांच्या पारंपरिक दिगंबर अवस्थेचा निर्देश करतो, जी संपूर्ण त्यागाचे प्रतीक आहे. ब्रिटानिका त्यांचा दशनामी संन्याशांतील सर्वाधिक लढवय्ये असा उल्लेख करते, जे पूर्वीच्या शतकांत कधी कधी युद्धांत सहभागी झाले.\n\nभारत सरकारनुसार ते तपश्चर्येसोबत शस्त्राभ्यासही करतात. मिरवणुकांत ते भाले आणि तलवारी अशी पारंपरिक शस्त्रे घेऊन चालतात आणि जुना आखाड्यात त्यांची संख्या सर्वाधिक आहे.\n\nबहुतेक भाविकांसाठी कुंभ हीच त्यांना पाहण्याची संधी असते. कृपया आदर राखा: साधूंशी वागण्याबाबतचा आमचा लेख पहा.",
        },
    },
    {
        "slug": "why-akhadas-join-kumbh", "category": "kumbh", "position": 4,
        "sources": ["pib_akharas", "kumbh_gurus"],
        "en": {
            "title": "Why do Akhadas take part in the Kumbh?",
            "intro": "For the Akhadas, the Kumbh is a gathering of the whole tradition as well as a sacred bath.",
            "body": "Official publications describe the Akhadas as the heart of the Kumbh. They camp together, hold worship and teaching, and lead the main processions.\n\nThe Kumbh is also when much of an Akhada's organizational life takes place. New members are initiated, and titles are conferred.\n\nThe Akhil Bharatiya Akhara Parishad, the Akhadas' representative body, works with the Mela committee on the dates, times and order of processions and baths.",
        },
        "hi": {
            "title": "अखाड़े कुंभ में क्यों आते हैं?",
            "intro": "अखाड़ों के लिए कुंभ पवित्र स्नान के साथ-साथ पूरी परंपरा का समागम भी है।",
            "body": "आधिकारिक प्रकाशन अखाड़ों को कुंभ का हृदय बताते हैं। वे साथ शिविर लगाते हैं, उपासना और प्रवचन करते हैं और मुख्य शोभायात्राओं का नेतृत्व करते हैं।\n\nअखाड़ों का बहुत-सा संगठनात्मक कार्य भी कुंभ में होता है। नए सदस्यों की दीक्षा होती है और पदवियाँ दी जाती हैं।\n\nअखाड़ों की प्रतिनिधि संस्था अखिल भारतीय अखाड़ा परिषद मेला समिति के साथ मिलकर शोभायात्राओं और स्नान की तिथि, समय और क्रम तय करती है।",
        },
        "mr": {
            "title": "आखाडे कुंभात का येतात?",
            "intro": "आखाड्यांसाठी कुंभ हा पवित्र स्नानासोबतच संपूर्ण परंपरेचा समागमही आहे.",
            "body": "अधिकृत प्रकाशने आखाड्यांना कुंभाचे हृदय म्हणतात. ते एकत्र शिबिरे उभारतात, उपासना आणि प्रवचने करतात आणि मुख्य मिरवणुकांचे नेतृत्व करतात.\n\nआखाड्यांचे बरेच संघटनात्मक कामही कुंभातच होते. नव्या सदस्यांना दीक्षा दिली जाते आणि पदव्या प्रदान केल्या जातात.\n\nआखाड्यांची प्रतिनिधी संस्था अखिल भारतीय आखाडा परिषद मेळा समितीसोबत मिरवणुका आणि स्नानाच्या तारखा, वेळा व क्रम ठरवते.",
        },
    },
    {
        "slug": "mahamandaleshwar-and-mahant", "category": "organization", "position": 5,
        "sources": ["kumbh_gurus", "pib_akharas", "hinduism_today", "etv_agni"],
        "akhadas": ["mahanirvani"], "saints": ["swami-avdheshanand-giri", "swami-kailashanand-giri"],
        "en": {
            "title": "What are Mahamandaleshwar and Mahant?",
            "intro": "These are titles of leadership within an Akhada. Their exact use differs from one Akhada to another.",
            "body": "A Mahamandaleshwar is a senior leader who guides the spiritual and organizational life of the Akhada. The Maha Kumbh portal says they alone may give the Guru-mantra to new saints.\n\nAn Acharya Mahamandaleshwar is the senior spiritual head, chosen by the assembled saints. The Mahanirvani Akhada is described as the first to create the position of Mahamandaleshwar for women.\n\nA Mahant is a head within the Akhada, and a Shri Mahant is a senior office-bearer. A Thanapati looks after day-to-day management and religious programmes.",
        },
        "hi": {
            "title": "महामंडलेश्वर और महंत क्या होते हैं?",
            "intro": "ये अखाड़े के भीतर नेतृत्व की पदवियाँ हैं। इनका ठीक उपयोग हर अखाड़े में अलग हो सकता है।",
            "body": "महामंडलेश्वर वरिष्ठ नेता होते हैं जो अखाड़े के आध्यात्मिक और संगठनात्मक जीवन का मार्गदर्शन करते हैं। महाकुंभ पोर्टल के अनुसार नए संतों को गुरु-मंत्र देने का अधिकार केवल इन्हीं को है।\n\nआचार्य महामंडलेश्वर वरिष्ठ आध्यात्मिक प्रमुख होते हैं, जिन्हें संत मिलकर चुनते हैं। महानिर्वाणी अखाड़े को महिलाओं के लिए महामंडलेश्वर पद बनाने वाला पहला अखाड़ा बताया गया है।\n\nमहंत अखाड़े के भीतर प्रमुख होते हैं और श्री महंत वरिष्ठ पदाधिकारी। थानापति रोज़ के प्रबंधन और धार्मिक कार्यक्रमों को देखते हैं।",
        },
        "mr": {
            "title": "महामंडलेश्वर आणि महंत म्हणजे काय?",
            "intro": "या आखाड्यातील नेतृत्वाच्या पदव्या आहेत. त्यांचा नेमका वापर प्रत्येक आखाड्यात वेगळा असू शकतो.",
            "body": "महामंडलेश्वर हे ज्येष्ठ नेते असतात, जे आखाड्याच्या आध्यात्मिक आणि संघटनात्मक जीवनाला मार्गदर्शन करतात. महाकुंभ पोर्टलनुसार नव्या संतांना गुरु-मंत्र देण्याचा अधिकार फक्त त्यांनाच असतो.\n\nआचार्य महामंडलेश्वर हे ज्येष्ठ आध्यात्मिक प्रमुख असतात, ज्यांची निवड संत एकत्रितपणे करतात. महानिर्वाणी आखाड्याचा महिलांसाठी महामंडलेश्वर पद निर्माण करणारा पहिला आखाडा असा उल्लेख आहे.\n\nमहंत हे आखाड्यातील प्रमुख असतात आणि श्री महंत ज्येष्ठ पदाधिकारी. थानापती दैनंदिन व्यवस्थापन आणि धार्मिक कार्यक्रम पाहतात.",
        },
    },
    {
        "slug": "spiritual-traditions", "category": "traditions", "position": 6,
        "sources": ["kumbh_gurus", "fpj_13", "nirmal_eos", "britannica_dashnami"],
        "en": {
            "title": "What are the different traditions?",
            "intro": "The 13 Akhadas belong to a few broad traditions, grouped mainly by whom they worship.",
            "body": "Shaiva Akhadas worship Lord Shiva. Their ascetics, the sannyasis, follow the Dashnami tradition, and there are seven of these Akhadas.\n\nVaishnava Akhadas, also called Bairagi, worship Lord Vishnu in his various forms. There are three: Nirmohi, Nirvani and Digambar.\n\nUdasin Akhadas trace their tradition to Chandra Dev (Sri Chand). The Nirmal Akhada comes from a tradition of saints linked to Guru Gobind Singh, and some counts group it with the Udasin Akhadas.",
        },
        "hi": {
            "title": "अलग-अलग परंपराएँ कौन सी हैं?",
            "intro": "तेरह अखाड़े कुछ व्यापक परंपराओं से जुड़े हैं, जो मुख्यतः उपास्य देव के आधार पर बँटी हैं।",
            "body": "शैव अखाड़े भगवान शिव की उपासना करते हैं। इनके संन्यासी दशनामी परंपरा का पालन करते हैं और ऐसे सात अखाड़े हैं।\n\nवैष्णव अखाड़े, जिन्हें बैरागी भी कहते हैं, भगवान विष्णु के विभिन्न रूपों की उपासना करते हैं। ये तीन हैं: निर्मोही, निर्वाणी और दिगंबर।\n\nउदासीन अखाड़े अपनी परंपरा चंद्र देव (श्री चंद) से जोड़ते हैं। निर्मल अखाड़ा गुरु गोबिंद सिंह से जुड़ी संत परंपरा से है और कुछ गणनाओं में इसे उदासीन अखाड़ों के साथ गिना जाता है।",
        },
        "mr": {
            "title": "वेगवेगळ्या परंपरा कोणत्या आहेत?",
            "intro": "तेरा आखाडे काही व्यापक परंपरांशी जोडलेले आहेत, ज्या मुख्यतः उपास्य दैवतानुसार विभागलेल्या आहेत.",
            "body": "शैव आखाडे भगवान शिवांची उपासना करतात. त्यांचे संन्यासी दशनामी परंपरा पाळतात आणि असे सात आखाडे आहेत.\n\nवैष्णव आखाडे, ज्यांना बैरागीही म्हणतात, भगवान विष्णूंच्या विविध रूपांची उपासना करतात. ते तीन आहेत: निर्मोही, निर्वाणी आणि दिगंबर.\n\nउदासीन आखाडे आपली परंपरा चंद्र देव (श्री चंद) यांच्याशी जोडतात. निर्मल आखाडा गुरु गोबिंद सिंह यांच्याशी जोडलेल्या संत परंपरेतील आहे आणि काही गणनांत तो उदासीन आखाड्यांसोबत मोजला जातो.",
        },
    },
    {
        "slug": "why-processions-matter", "category": "kumbh", "position": 7,
        "sources": ["kumbh_gurus", "pib_akharas"], "akhadas": ["avahan"],
        "en": {
            "title": "Why are processions important?",
            "intro": "Processions are how an Akhada arrives at the Kumbh and goes to its sacred bath, in public and in order.",
            "body": "The Peshwai and the Amrit Snan procession display an Akhada's standing and tradition. Leaders travel in a set order: the Maha Kumbh portal notes that Mahamandaleshwars are accompanied by the Shri Mahant, and that Naga sages ride horses.\n\nEach Akhada has its own customs. The Avahan Akhada, for example, keeps up the Chhari Yatra, carrying a holy staff symbolizing divine authority.\n\nRoutes and timings are set by the authorities with the Akhadas, and they can change. Follow official announcements on the day.",
        },
        "hi": {
            "title": "शोभायात्राएँ क्यों महत्वपूर्ण हैं?",
            "intro": "शोभायात्रा के रूप में अखाड़ा कुंभ में प्रवेश करता है और पवित्र स्नान के लिए सार्वजनिक रूप से, तय क्रम में जाता है।",
            "body": "पेशवाई और अमृत स्नान की शोभायात्रा अखाड़े की प्रतिष्ठा और परंपरा को दर्शाती है। नेतृत्व तय क्रम में चलता है: महाकुंभ पोर्टल के अनुसार महामंडलेश्वरों के साथ श्री महंत चलते हैं और नागा संत घोड़ों पर सवार होते हैं।\n\nहर अखाड़े की अपनी रीति होती है। उदाहरण के लिए, आवाहन अखाड़ा छड़ी यात्रा निभाता है, जिसमें दैवी अधिकार की प्रतीक पवित्र छड़ी ले जाई जाती है।\n\nमार्ग और समय प्रशासन अखाड़ों के साथ मिलकर तय करता है और ये बदल सकते हैं। उस दिन की आधिकारिक घोषणाओं का पालन करें।",
        },
        "mr": {
            "title": "मिरवणुका का महत्त्वाच्या आहेत?",
            "intro": "मिरवणुकीच्या रूपात आखाडा कुंभात प्रवेश करतो आणि पवित्र स्नानासाठी सार्वजनिकरित्या, ठरलेल्या क्रमाने जातो.",
            "body": "पेशवाई आणि अमृत स्नानाची मिरवणूक आखाड्याची प्रतिष्ठा आणि परंपरा दाखवते. नेतृत्व ठरलेल्या क्रमाने चालते: महाकुंभ पोर्टलनुसार महामंडलेश्वरांसोबत श्री महंत चालतात आणि नागा संत घोड्यांवर असतात.\n\nप्रत्येक आखाड्याची स्वतःची रीत असते. उदाहरणार्थ, आवाहन आखाडा छडी यात्रा जपतो, ज्यात दैवी अधिकाराचे प्रतीक असलेली पवित्र छडी नेली जाते.\n\nमार्ग आणि वेळा प्रशासन आखाड्यांसोबत ठरवते आणि त्या बदलू शकतात. त्या दिवशीच्या अधिकृत घोषणांचे पालन करा.",
        },
    },
    {
        "slug": "significance-of-amrit-snan", "category": "kumbh", "position": 8,
        "sources": ["pti_dates", "jacobsen", "lochtefeld", "kumbh_gurus"],
        "en": {
            "title": "What is the significance of Amrit Snan?",
            "intro": "Amrit Snan is the sacred bath of the Akhadas on the principal bathing days of the Kumbh.",
            "body": "It was long known as Shahi Snan, the royal bath. At the June 2025 planning meeting in Nashik, the name Amrut Snan was proposed and accepted for this Simhastha.\n\nIn Nashik–Trimbakeshwar, Vaishnava and Shaiva Akhadas bathe separately. Scholars record that, after a clash over bathing order in 1789, the Maratha Peshwa moved the Vaishnava bath to Ramkund in Nashik. Shaiva Akhadas have continued to bathe at Trimbakeshwar.\n\nThis differs from Prayagraj, where the Akhadas bathe at one place, the Triveni Sangam, in turn. Check the Nashik Kumbh section for current dates.",
        },
        "hi": {
            "title": "अमृत स्नान का क्या महत्व है?",
            "intro": "अमृत स्नान कुंभ के प्रमुख स्नान दिवसों पर अखाड़ों का पवित्र स्नान है।",
            "body": "इसे लंबे समय तक शाही स्नान कहा जाता रहा। जून 2025 में नाशिक की योजना बैठक में इस सिंहस्थ के लिए अमृत स्नान नाम का प्रस्ताव रखा गया और स्वीकार हुआ।\n\nनाशिक–त्र्यंबकेश्वर में वैष्णव और शैव अखाड़े अलग-अलग स्नान करते हैं। विद्वानों के अनुसार 1789 में स्नान के क्रम को लेकर हुए संघर्ष के बाद मराठा पेशवा ने वैष्णव स्नान को नाशिक के रामकुंड में स्थानांतरित किया। शैव अखाड़े त्र्यंबकेश्वर में स्नान करते आ रहे हैं।\n\nप्रयागराज में ऐसा नहीं है, वहाँ अखाड़े एक ही स्थान, त्रिवेणी संगम पर बारी-बारी से स्नान करते हैं। वर्तमान तिथियों के लिए नाशिक कुंभ अनुभाग देखें।",
        },
        "mr": {
            "title": "अमृत स्नानाचे महत्त्व काय?",
            "intro": "अमृत स्नान म्हणजे कुंभाच्या प्रमुख स्नान दिवशी आखाड्यांचे पवित्र स्नान.",
            "body": "याला दीर्घकाळ शाही स्नान म्हटले जात होते. जून 2025 मध्ये नाशिकच्या नियोजन बैठकीत या सिंहस्थासाठी अमृत स्नान हे नाव सुचवले गेले आणि स्वीकारले गेले.\n\nनाशिक–त्र्यंबकेश्वर येथे वैष्णव आणि शैव आखाडे वेगवेगळे स्नान करतात. विद्वानांच्या नोंदीनुसार 1789 मध्ये स्नानाच्या क्रमावरून झालेल्या संघर्षानंतर मराठा पेशव्यांनी वैष्णव स्नान नाशिकच्या रामकुंडावर हलवले. शैव आखाडे त्र्यंबकेश्वर येथे स्नान करत आले आहेत.\n\nप्रयागराजमध्ये असे नाही, तेथे आखाडे एकाच ठिकाणी, त्रिवेणी संगमावर क्रमाने स्नान करतात. सध्याच्या तारखांसाठी नाशिक कुंभ विभाग पहा.",
        },
    },
    {
        "slug": "how-akhadas-are-organized", "category": "organization", "position": 9,
        "sources": ["kumbh_gurus", "fpj_13", "etv_agni", "etv_parishad"],
        "en": {
            "title": "How are Akhadas organized?",
            "intro": "Each Akhada runs itself through its own office-bearers, and a shared body represents them together.",
            "body": "The Maha Kumbh portal says a five-member committee manages each Akhada's order and operations, its members seen as representatives of Brahma, Vishnu, Shiva, Ganesha and Shakti.\n\nOther office-bearers can include the Shri Mahant, Mahants, the Thanapati, secretaries and keepers of accounts. Titles and duties vary between Akhadas.\n\nThe Akhil Bharatiya Akhara Parishad promotes harmony between Akhadas and settles disputes. As of June 2026 the Parishad itself was reported to be divided into rival groups, so this app doesn't name a single head.",
        },
        "hi": {
            "title": "अखाड़ों का संगठन कैसा होता है?",
            "intro": "हर अखाड़ा अपने पदाधिकारियों से चलता है और एक साझा संस्था सबका प्रतिनिधित्व करती है।",
            "body": "महाकुंभ पोर्टल के अनुसार पाँच सदस्यों की समिति हर अखाड़े की व्यवस्था और संचालन देखती है। इसके सदस्यों को ब्रह्मा, विष्णु, शिव, गणेश और शक्ति का प्रतिनिधि माना जाता है।\n\nअन्य पदाधिकारियों में श्री महंत, महंत, थानापति, सचिव और लेखा देखने वाले हो सकते हैं। पदवियाँ और दायित्व अखाड़ों में अलग-अलग होते हैं।\n\nअखिल भारतीय अखाड़ा परिषद अखाड़ों में सद्भाव बढ़ाती है और विवाद सुलझाती है। जून 2026 की रिपोर्ट के अनुसार परिषद स्वयं प्रतिद्वंद्वी गुटों में बँटी थी, इसलिए यह ऐप किसी एक प्रमुख का नाम नहीं देता।",
        },
        "mr": {
            "title": "आखाड्यांची रचना कशी असते?",
            "intro": "प्रत्येक आखाडा स्वतःच्या पदाधिकाऱ्यांमार्फत चालतो आणि एक समान संस्था सर्वांचे प्रतिनिधित्व करते.",
            "body": "महाकुंभ पोर्टलनुसार पाच सदस्यांची समिती प्रत्येक आखाड्याची व्यवस्था आणि कामकाज पाहते. तिचे सदस्य ब्रह्मा, विष्णू, शिव, गणेश आणि शक्ती यांचे प्रतिनिधी मानले जातात.\n\nइतर पदाधिकाऱ्यांत श्री महंत, महंत, थानापती, सचिव आणि हिशेब पाहणारे असू शकतात. पदव्या आणि जबाबदाऱ्या आखाड्यांनुसार बदलतात.\n\nअखिल भारतीय आखाडा परिषद आखाड्यांत सलोखा वाढवते आणि वाद मिटवते. जून 2026 च्या वृत्तानुसार परिषदच प्रतिस्पर्धी गटांत विभागलेली होती, म्हणून हे अॅप कोणत्याही एका प्रमुखाचे नाव देत नाही.",
        },
    },
    {
        "slug": "respectful-interaction", "category": "etiquette", "position": 10, "is_editorial": True,
        "sources": ["dh_reels", "kumbh_gurus"],
        "en": {
            "title": "How can I interact respectfully with Sadhus?",
            "intro": "Our own guidance, based on common courtesy at sacred gatherings. Rules at the Kumbh are set by the authorities and can change.",
            "body": "Greet with folded hands, and ask before you photograph or film anyone, especially during worship or meditation. At the 2025 Maha Kumbh, the Akhara Parishad's demand led to limits on making videos, so check the current rules.\n\nDon't enter an Akhada's camp or sacred area unless invited or clearly open to visitors. Keep clear of processions, and follow police and volunteers.\n\nMoney or offerings are your own choice. No one needs to pay for a blessing, and nothing in this app recommends giving to any person.",
        },
        "hi": {
            "title": "साधुओं से सम्मानपूर्वक कैसे मिलें?",
            "intro": "यह हमारा अपना मार्गदर्शन है, जो पवित्र समागमों के सामान्य शिष्टाचार पर आधारित है। कुंभ के नियम प्रशासन तय करता है और वे बदल सकते हैं।",
            "body": "हाथ जोड़कर अभिवादन करें और किसी की फ़ोटो या वीडियो लेने से पहले पूछें, ख़ासकर पूजा या ध्यान के समय। 2025 के महाकुंभ में अखाड़ा परिषद की माँग पर वीडियो बनाने पर रोक लगी थी, इसलिए वर्तमान नियम जाँच लें।\n\nबिना आमंत्रण या स्पष्ट अनुमति के अखाड़े के शिविर या पवित्र क्षेत्र में न जाएँ। शोभायात्राओं से दूरी रखें और पुलिस व स्वयंसेवकों का पालन करें।\n\nदान या भेंट आपकी अपनी इच्छा है। आशीर्वाद के लिए किसी को कुछ देना ज़रूरी नहीं, और यह ऐप किसी व्यक्ति को देने की सलाह नहीं देता।",
        },
        "mr": {
            "title": "साधूंशी आदराने कसे वागावे?",
            "intro": "हे आमचे स्वतःचे मार्गदर्शन आहे, जे पवित्र समागमांतील सामान्य शिष्टाचारावर आधारित आहे. कुंभातील नियम प्रशासन ठरवते आणि ते बदलू शकतात.",
            "body": "हात जोडून नमस्कार करा आणि कोणाचा फोटो किंवा व्हिडिओ घेण्यापूर्वी विचारा, विशेषतः पूजा किंवा ध्यानाच्या वेळी. 2025 च्या महाकुंभात आखाडा परिषदेच्या मागणीवरून व्हिडिओ बनवण्यावर बंधने आली होती, म्हणून सध्याचे नियम तपासा.\n\nआमंत्रणाशिवाय किंवा स्पष्ट परवानगीशिवाय आखाड्याच्या शिबिरात किंवा पवित्र परिसरात जाऊ नका. मिरवणुकांपासून अंतर ठेवा आणि पोलीस व स्वयंसेवकांच्या सूचना पाळा.\n\nदान किंवा भेट ही तुमची स्वतःची इच्छा आहे. आशीर्वादासाठी कोणाला काही देणे आवश्यक नाही आणि हे अॅप कोणत्याही व्यक्तीला देण्याचा सल्ला देत नाही.",
        },
    },
]

_ANNOUNCED_EN = "Reported from the June 2025 planning meeting chaired by the Chief Minister. Confirm with official announcements."
_ANNOUNCED_HI = "जून 2025 में मुख्यमंत्री की अध्यक्षता वाली योजना बैठक की जानकारी। आधिकारिक घोषणाओं से पुष्टि करें।"
_ANNOUNCED_MR = "जून 2025 मधील मुख्यमंत्र्यांच्या अध्यक्षतेखालील नियोजन बैठकीची माहिती. अधिकृत घोषणांवरून खात्री करा."
_NASHIK = {"en": "Nashik", "hi": "नाशिक", "mr": "नाशिक"}
_BOTH = {"en": "Nashik and Trimbakeshwar", "hi": "नाशिक और त्र्यंबकेश्वर", "mr": "नाशिक आणि त्र्यंबकेश्वर"}


def _snan(slug, number, day, place=_BOTH):
    return {
        "slug": slug, "kind": "bathing", "confirmation": "announced", "start_date": day,
        "sources": ["pti_dates", "sarkarnama_dates"],
        "en": {"title": f"{number[0]} Amrit Snan", "description": _ANNOUNCED_EN, "location": place["en"]},
        "hi": {"title": f"{number[1]} अमृत स्नान", "description": _ANNOUNCED_HI, "location": place["hi"]},
        "mr": {"title": f"{number[2]} अमृत स्नान", "description": _ANNOUNCED_MR, "location": place["mr"]},
    }


ACTIVITIES = [
    {
        "slug": "kumbh-flag-hoisting-2026", "kind": "ceremony", "confirmation": "announced",
        "start_date": date(2026, 10, 31), "sources": ["pti_dates", "navbharat_flag"],
        "en": {"title": "Kumbh flag hoisting (Dhwajarohan)", "description": "Marks the start of the Simhastha period. A report of 28 October 2026 gives the time as a proposed 12:02 pm at Ramkund, with details awaiting final approval.", "location": "Ramkund, Nashik, and Trimbakeshwar"},
        "hi": {"title": "कुंभ ध्वजारोहण", "description": "इससे सिंहस्थ काल का आरंभ होता है। 28 अक्टूबर 2026 की रिपोर्ट में रामकुंड पर दोपहर 12:02 का प्रस्तावित समय बताया गया है और विवरण अंतिम मंज़ूरी के अधीन है।", "location": "रामकुंड, नाशिक और त्र्यंबकेश्वर"},
        "mr": {"title": "कुंभ ध्वजारोहण", "description": "यामुळे सिंहस्थ काळाची सुरुवात होते. 28 ऑक्टोबर 2026 च्या वृत्तात रामकुंडावर दुपारी 12:02 ही प्रस्तावित वेळ दिली आहे आणि तपशील अंतिम मंजुरीच्या अधीन आहे.", "location": "रामकुंड, नाशिक आणि त्र्यंबकेश्वर"},
    },
    {
        "slug": "tapovan-vaishnava-camps", "kind": "camp", "confirmation": "awaiting",
        "akhadas": ["nirmohi", "nirvani", "digambar"],
        "sources": ["fpj_inspection", "navbharat_flag", "sarkarnama_land"],
        "en": {"title": "Vaishnava Akhada sites at Tapovan Sadhugram", "description": "Proposed sites were inspected in June 2026, and the Nashik Municipal Corporation's Standing Committee approved works such as roads, water and electricity. News reports say land for the wider Sadhugram was still unresolved in October 2026, so camp locations aren't final.", "location": "Tapovan Sadhugram area, Nashik (proposed)"},
        "hi": {"title": "तपोवन साधुग्राम में वैष्णव अखाड़ों के स्थल", "description": "जून 2026 में प्रस्तावित स्थलों का निरीक्षण हुआ और नाशिक महानगरपालिका की स्थायी समिति ने सड़क, पानी और बिजली जैसे कार्यों को मंज़ूरी दी। समाचारों के अनुसार अक्टूबर 2026 तक व्यापक साधुग्राम की ज़मीन का प्रश्न अनसुलझा था, इसलिए शिविर स्थल अंतिम नहीं हैं।", "location": "तपोवन साधुग्राम क्षेत्र, नाशिक (प्रस्तावित)"},
        "mr": {"title": "तपोवन साधुग्राममधील वैष्णव आखाड्यांच्या जागा", "description": "जून 2026 मध्ये प्रस्तावित जागांची पाहणी झाली आणि नाशिक महापालिकेच्या स्थायी समितीने रस्ते, पाणी आणि वीज अशा कामांना मंजुरी दिली. वृत्तांनुसार ऑक्टोबर 2026 पर्यंत व्यापक साधुग्रामच्या जमिनीचा प्रश्न सुटलेला नव्हता, त्यामुळे शिबिरांच्या जागा अंतिम नाहीत.", "location": "तपोवन साधुग्राम परिसर, नाशिक (प्रस्तावित)"},
    },
    {
        "slug": "akhada-flag-hoisting-2027", "kind": "ceremony", "confirmation": "announced",
        "start_date": date(2027, 7, 24), "sources": ["sarkarnama_dates"],
        "en": {"title": "Akhada flag hoisting", "description": "Reported in June 2025 by one news outlet; we found no later confirmation.", "location": "Sadhugram, Nashik"},
        "hi": {"title": "अखाड़ा ध्वजारोहण", "description": "जून 2025 में एक समाचार माध्यम की जानकारी; इसके बाद की पुष्टि हमें नहीं मिली।", "location": "साधुग्राम, नाशिक"},
        "mr": {"title": "आखाडा ध्वजारोहण", "description": "जून 2025 मध्ये एका वृत्तमाध्यमाची माहिती; त्यानंतरची पुष्टी आम्हाला मिळाली नाही.", "location": "साधुग्राम, नाशिक"},
    },
    {
        "slug": "nagar-pradakshina-2027", "kind": "procession", "confirmation": "announced",
        "start_date": date(2027, 7, 29), "sources": ["pti_dates", "sarkarnama_dates"],
        "en": {"title": "Nagar Pradakshina", "description": _ANNOUNCED_EN, "location": "Nashik"},
        "hi": {"title": "नगर प्रदक्षिणा", "description": _ANNOUNCED_HI, "location": "नाशिक"},
        "mr": {"title": "नगर प्रदक्षिणा", "description": _ANNOUNCED_MR, "location": "नाशिक"},
    },
    _snan("amrit-snan-1-2027", ("First", "पहला", "पहिले"), date(2027, 8, 2)),
    _snan("amrit-snan-2-2027", ("Second", "दूसरा", "दुसरे"), date(2027, 8, 31)),
    _snan("amrit-snan-3-nashik-2027", ("Third", "तीसरा", "तिसरे"), date(2027, 9, 11), _NASHIK),
    _snan(
        "amrit-snan-3-trimbak-2027", ("Third", "तीसरा", "तिसरे"), date(2027, 9, 12),
        {"en": "Trimbakeshwar", "hi": "त्र्यंबकेश्वर", "mr": "त्र्यंबकेश्वर"},
    ),
    {
        "slug": "nashik-trimbak-separate-baths", "kind": "history", "confirmation": "historical",
        "sources": ["jacobsen", "lochtefeld", "pti_dates"],
        "en": {"title": "Why Vaishnava and Shaiva Akhadas bathe separately", "description": "Scholars record a clash over bathing order in 1789, after which the Maratha Peshwa moved the Vaishnava bath to Ramkund in Nashik. A Peshwa inscription claims very heavy loss of life. The Akhadas still bathe separately today."},
        "hi": {"title": "वैष्णव और शैव अखाड़े अलग-अलग स्नान क्यों करते हैं", "description": "विद्वानों के अनुसार 1789 में स्नान के क्रम पर संघर्ष हुआ, जिसके बाद मराठा पेशवा ने वैष्णव स्नान को नाशिक के रामकुंड में स्थानांतरित किया। पेशवा के एक अभिलेख में भारी जनहानि का दावा है। अखाड़े आज भी अलग-अलग स्नान करते हैं।"},
        "mr": {"title": "वैष्णव आणि शैव आखाडे वेगवेगळे स्नान का करतात", "description": "विद्वानांच्या नोंदीनुसार 1789 मध्ये स्नानाच्या क्रमावरून संघर्ष झाला, त्यानंतर मराठा पेशव्यांनी वैष्णव स्नान नाशिकच्या रामकुंडावर हलवले. पेशव्यांच्या एका लेखात मोठ्या जीवितहानीचा दावा आहे. आखाडे आजही वेगवेगळे स्नान करतात."},
    },
]
