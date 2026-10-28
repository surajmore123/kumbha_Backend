"""
Fixed assistant replies (no model call) in English, Hindi and Marathi,
and detection of the language to reply in.

These are used when the answer must not depend on the model: missing
data, failed processing, unsupported files. Keep them factual.
"""

import re
from dataclasses import dataclass

SUPPORTED_LANGUAGES = ("en", "hi", "mr")

_MESSAGES: dict[str, dict[str, str]] = {
    "unavailable": {
        "en": "Sorry, I am unable to respond right now. Please try again in a moment.",
        "hi": "क्षमा करें, मैं अभी उत्तर नहीं दे पा रहा हूँ। कृपया थोड़ी देर बाद फिर कोशिश करें।",
        "mr": "माफ करा, मी आत्ता उत्तर देऊ शकत नाही. कृपया थोड्या वेळाने पुन्हा प्रयत्न करा.",
    },
    "busy": {
        "en": "The AI service is busy right now. Please try again in a minute.",
        "hi": "एआई सेवा अभी व्यस्त है। कृपया एक मिनट बाद फिर कोशिश करें।",
        "mr": "एआय सेवा सध्या व्यस्त आहे. कृपया एका मिनिटाने पुन्हा प्रयत्न करा.",
    },
    "no_events": {
        "en": "I couldn't find any upcoming published and verified events in the available database.",
        "hi": "उपलब्ध डेटाबेस में मुझे कोई आगामी प्रकाशित और सत्यापित कार्यक्रम नहीं मिला।",
        "mr": "उपलब्ध डेटाबेसमध्ये मला कोणताही आगामी प्रकाशित आणि सत्यापित कार्यक्रम सापडला नाही.",
    },
    "no_temple": {
        "en": "I couldn't identify a matching temple in the available temple database. Please provide the temple name.",
        "hi": "उपलब्ध मंदिर डेटाबेस में मुझे कोई मेल खाता मंदिर नहीं मिला। कृपया मंदिर का नाम बताएं।",
        "mr": "उपलब्ध मंदिर डेटाबेसमध्ये मला जुळणारे मंदिर सापडले नाही. कृपया मंदिराचे नाव सांगा.",
    },
    "no_knowledge": {
        "en": "I couldn't find enough information in the available knowledge sources to answer that reliably.",
        "hi": "उपलब्ध जानकारी स्रोतों में इसका भरोसेमंद उत्तर देने के लिए पर्याप्त जानकारी नहीं मिली।",
        "mr": "उपलब्ध माहिती स्रोतांमध्ये याचे विश्वासार्ह उत्तर देण्यासाठी पुरेशी माहिती सापडली नाही.",
    },
    "no_crowd": {
        "en": "No crowd measurements are available for that area right now.",
        "hi": "उस क्षेत्र के लिए अभी भीड़ का कोई माप उपलब्ध नहीं है।",
        "mr": "त्या भागासाठी सध्या गर्दीची कोणतीही मोजणी उपलब्ध नाही.",
    },
    "crowd_fresh": {
        "en": "Crowd data last updated {time} ({minutes} min ago).",
        "hi": "भीड़ का डेटा आखिरी बार {time} पर अपडेट हुआ ({minutes} मिनट पहले)।",
        "mr": "गर्दीची माहिती शेवटची {time} वाजता अद्ययावत झाली ({minutes} मिनिटांपूर्वी).",
    },
    "crowd_stale": {
        "en": "Note: the latest crowd data is from {time} and may not reflect current conditions.",
        "hi": "ध्यान दें: भीड़ का नवीनतम डेटा {time} का है और यह वर्तमान स्थिति नहीं दर्शा सकता।",
        "mr": "टीप: गर्दीची नवीनतम माहिती {time} ची आहे आणि ती सध्याची स्थिती दर्शवत नसेल.",
    },
    "image_failed": {
        "en": "I couldn't analyse this image right now, so I can't say what it shows. Please try again.",
        "hi": "मैं अभी इस चित्र का विश्लेषण नहीं कर सका, इसलिए नहीं बता सकता कि इसमें क्या है। कृपया फिर कोशिश करें।",
        "mr": "मी सध्या या चित्राचे विश्लेषण करू शकलो नाही, त्यामुळे त्यात काय आहे ते सांगू शकत नाही. कृपया पुन्हा प्रयत्न करा.",
    },
    "audio_failed": {
        "en": "I couldn't process this voice message right now. Please try again or type your question.",
        "hi": "मैं अभी इस वॉइस संदेश को प्रोसेस नहीं कर सका। कृपया फिर कोशिश करें या अपना प्रश्न लिखें।",
        "mr": "मी सध्या हा व्हॉइस संदेश प्रक्रिया करू शकलो नाही. कृपया पुन्हा प्रयत्न करा किंवा तुमचा प्रश्न लिहा.",
    },
    "no_speech": {
        "en": "I couldn't hear any speech in this recording. Please try recording again closer to the microphone.",
        "hi": "इस रिकॉर्डिंग में मुझे कोई आवाज़ सुनाई नहीं दी। कृपया माइक्रोफ़ोन के पास से फिर रिकॉर्ड करें।",
        "mr": "या रेकॉर्डिंगमध्ये मला कोणताही आवाज ऐकू आला नाही. कृपया मायक्रोफोनजवळून पुन्हा रेकॉर्ड करा.",
    },
    "document_failed": {
        "en": "I couldn't analyse this document right now. Please try again.",
        "hi": "मैं अभी इस दस्तावेज़ का विश्लेषण नहीं कर सका। कृपया फिर कोशिश करें।",
        "mr": "मी सध्या या दस्तऐवजाचे विश्लेषण करू शकलो नाही. कृपया पुन्हा प्रयत्न करा.",
    },
    "document_scanned_no_ocr": {
        "en": "This PDF appears to be scanned (pages are images, not text). I couldn't read it because text recognition (OCR) is not available for it on the server.",
        "hi": "यह PDF स्कैन किया हुआ लगता है (पृष्ठ चित्र हैं, टेक्स्ट नहीं)। सर्वर पर इसके लिए टेक्स्ट पहचान (OCR) उपलब्ध नहीं है, इसलिए मैं इसे पढ़ नहीं सका।",
        "mr": "ही PDF स्कॅन केलेली दिसते (पाने चित्रे आहेत, मजकूर नाही). सर्व्हरवर यासाठी मजकूर ओळख (OCR) उपलब्ध नसल्याने मी ती वाचू शकलो नाही.",
    },
    "document_empty": {
        "en": "I couldn't find any readable text in this document.",
        "hi": "इस दस्तावेज़ में मुझे पढ़ने योग्य कोई टेक्स्ट नहीं मिला।",
        "mr": "या दस्तऐवजात मला वाचण्यायोग्य मजकूर सापडला नाही.",
    },
    # ---- upload validation ----
    "empty_file": {
        "en": "The uploaded file is empty.",
        "hi": "अपलोड की गई फ़ाइल खाली है।",
        "mr": "अपलोड केलेली फाइल रिकामी आहे.",
    },
    "unsupported_file": {
        "en": "This file type is not supported. Please send a JPEG, PNG or WebP image; a WAV, MP3, M4A, AAC, OGG, FLAC or WebM recording; or a PDF, DOCX, TXT, CSV or XLSX document.",
        "hi": "यह फ़ाइल प्रकार समर्थित नहीं है। कृपया JPEG, PNG या WebP चित्र; WAV, MP3, M4A, AAC, OGG, FLAC या WebM रिकॉर्डिंग; या PDF, DOCX, TXT, CSV या XLSX दस्तावेज़ भेजें।",
        "mr": "हा फाइल प्रकार समर्थित नाही. कृपया JPEG, PNG किंवा WebP चित्र; WAV, MP3, M4A, AAC, OGG, FLAC किंवा WebM रेकॉर्डिंग; किंवा PDF, DOCX, TXT, CSV किंवा XLSX दस्तऐवज पाठवा.",
    },
    "type_mismatch": {
        "en": "The file's contents don't match its name or type, so it was not processed.",
        "hi": "फ़ाइल की सामग्री उसके नाम या प्रकार से मेल नहीं खाती, इसलिए इसे प्रोसेस नहीं किया गया।",
        "mr": "फाइलमधील मजकूर तिच्या नावाशी किंवा प्रकाराशी जुळत नाही, त्यामुळे ती प्रक्रिया केली नाही.",
    },
    "file_too_large": {
        "en": "The file is too large. The limit for this file type is {limit} MB.",
        "hi": "फ़ाइल बहुत बड़ी है। इस प्रकार की फ़ाइल की सीमा {limit} MB है।",
        "mr": "फाइल खूप मोठी आहे. या प्रकारच्या फाइलची मर्यादा {limit} MB आहे.",
    },
    "corrupt_image": {
        "en": "This image could not be opened. It may be damaged or incomplete.",
        "hi": "यह चित्र खोला नहीं जा सका। यह खराब या अधूरा हो सकता है।",
        "mr": "हे चित्र उघडता आले नाही. ते खराब किंवा अपूर्ण असू शकते.",
    },
    "unsupported_image": {
        "en": "This image format is not supported. Please send a JPEG, PNG or WebP image.",
        "hi": "यह चित्र प्रारूप समर्थित नहीं है। कृपया JPEG, PNG या WebP चित्र भेजें।",
        "mr": "हा चित्र प्रकार समर्थित नाही. कृपया JPEG, PNG किंवा WebP चित्र पाठवा.",
    },
    "image_too_large": {
        "en": "This image's dimensions are too large to process.",
        "hi": "इस चित्र का आकार प्रोसेस करने के लिए बहुत बड़ा है।",
        "mr": "या चित्राचा आकार प्रक्रिया करण्यासाठी खूप मोठा आहे.",
    },
    "corrupt_audio": {
        "en": "This recording could not be decoded. It may be damaged or use an unsupported codec.",
        "hi": "यह रिकॉर्डिंग डिकोड नहीं हो सकी। यह खराब हो सकती है या असमर्थित कोडेक में हो सकती है।",
        "mr": "हे रेकॉर्डिंग डिकोड करता आले नाही. ते खराब असू शकते किंवा असमर्थित कोडेकमध्ये असू शकते.",
    },
    "empty_audio": {
        "en": "This recording is empty.",
        "hi": "यह रिकॉर्डिंग खाली है।",
        "mr": "हे रेकॉर्डिंग रिकामे आहे.",
    },
    "audio_too_long": {
        "en": "This recording is too long. Please keep voice messages under {limit} seconds.",
        "hi": "यह रिकॉर्डिंग बहुत लंबी है। कृपया वॉइस संदेश {limit} सेकंड से कम रखें।",
        "mr": "हे रेकॉर्डिंग खूप लांब आहे. कृपया व्हॉइस संदेश {limit} सेकंदांपेक्षा कमी ठेवा.",
    },
    "audio_conversion_unavailable": {
        "en": "This audio format needs conversion, which is not available on the server right now. Please send WAV or MP3.",
        "hi": "इस ऑडियो प्रारूप को बदलना पड़ता है, जो अभी सर्वर पर उपलब्ध नहीं है। कृपया WAV या MP3 भेजें।",
        "mr": "या ऑडिओ प्रकाराचे रूपांतर करावे लागते, जे सध्या सर्व्हरवर उपलब्ध नाही. कृपया WAV किंवा MP3 पाठवा.",
    },
    "encrypted_document": {
        "en": "This document is password-protected or encrypted, so I can't read it.",
        "hi": "यह दस्तावेज़ पासवर्ड से सुरक्षित या एन्क्रिप्टेड है, इसलिए मैं इसे पढ़ नहीं सकता।",
        "mr": "हा दस्तऐवज पासवर्डने संरक्षित किंवा एन्क्रिप्टेड आहे, त्यामुळे मी तो वाचू शकत नाही.",
    },
    "corrupt_document": {
        "en": "This document could not be opened. It may be damaged or in an unsupported format.",
        "hi": "यह दस्तावेज़ खोला नहीं जा सका। यह खराब या असमर्थित प्रारूप में हो सकता है।",
        "mr": "हा दस्तऐवज उघडता आला नाही. तो खराब किंवा असमर्थित प्रकारात असू शकतो.",
    },
    "macro_document": {
        "en": "Documents containing macros are not accepted.",
        "hi": "मैक्रो वाले दस्तावेज़ स्वीकार नहीं किए जाते।",
        "mr": "मॅक्रो असलेले दस्तऐवज स्वीकारले जात नाहीत.",
    },
    "media_unavailable": {
        "en": "File analysis is temporarily unavailable. Please try again later or type your question.",
        "hi": "फ़ाइल विश्लेषण अस्थायी रूप से उपलब्ध नहीं है। कृपया बाद में कोशिश करें या अपना प्रश्न लिखें।",
        "mr": "फाइल विश्लेषण तात्पुरते उपलब्ध नाही. कृपया नंतर प्रयत्न करा किंवा तुमचा प्रश्न लिहा.",
    },
}

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "bn": "Bengali",
    "or": "Odia",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "ur": "Urdu",
}

# Script ranges for languages written in their own script. Devanagari is
# shared by Hindi and Marathi and is told apart with word hints below.
_SCRIPTS = (
    ("gu", re.compile(r"[઀-૿]")),
    ("pa", re.compile(r"[਀-੿]")),
    ("bn", re.compile(r"[ঀ-৿]")),
    ("or", re.compile(r"[଀-୿]")),
    ("ta", re.compile(r"[஀-௿]")),
    ("te", re.compile(r"[ఀ-౿]")),
    ("kn", re.compile(r"[ಀ-೿]")),
    ("ml", re.compile(r"[ഀ-ൿ]")),
    ("ur", re.compile(r"[؀-ۿ]")),
)
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_DEVANAGARI_WORD = re.compile(r"[ऀ-ॿ]+")
_LATIN_WORD = re.compile(r"[a-z']+")

_MARATHI_HINTS = {
    "आहे", "आहेत", "काय", "कुठे", "कसे", "कसा", "कशी", "मला", "आणि", "नाही",
    "आम्ही", "तुम्ही", "कोणते", "कोणता", "केव्हा", "किती", "मंदिराचे", "गर्दी",
    "सांगा", "जायचे", "होणार", "आहोत", "माहिती", "कधी", "मध्ये", "होईल",
    "पाहिजे", "करा", "येथे", "तिथे", "च्या", "चे", "ची", "पुढचे", "पुढील",
    "जवळ", "उद्या",
}
_HINDI_HINTS = {
    "है", "हैं", "क्या", "कहाँ", "कहां", "कैसे", "मुझे", "और", "नहीं", "हम",
    "आप", "कौन", "कब", "कितना", "कितनी", "भीड़", "बताइए", "बताओ", "जाना",
    "होगा", "रहा", "में", "चाहिए", "यहाँ", "वहाँ", "अगला", "अगली", "पास",
    "कल", "मेरा", "मेरी", "था", "थी",
}
# Hindi and Marathi typed in Latin letters ("Amrit snan kab hai?").
_ROMAN_HINDI = {
    "kab", "kya", "hai", "hain", "kahan", "kahaan", "kaise", "kaun", "mujhe",
    "batao", "bataiye", "kitna", "kitni", "chahiye", "nahi", "nahin", "mein",
    "agla", "agli", "bheed", "bhid", "hoga", "kaha", "jana", "raha",
}
_ROMAN_MARATHI = {
    "kadhi", "kay", "aahe", "ahe", "aahet", "ahet", "kuthe", "kasa", "kashi",
    "kase", "mala", "sanga", "pahije", "kiti", "gardi", "madhe", "madhye",
    "aani", "ani", "nahi", "hoil", "pudhcha", "pudhche", "javal", "udya",
}
_ROMAN_STRONG = {
    "hi": {"kab", "kya", "kahan", "kaise", "batao", "bataiye", "chahiye", "kahaan"},
    "mr": {"kadhi", "aahe", "ahe", "kuthe", "sanga", "pahije", "ahet", "aahet", "madhe", "madhye"},
}
_ENGLISH_WORDS = {
    "the", "is", "are", "what", "when", "where", "how", "which", "who", "why",
    "can", "do", "does", "i", "you", "my", "me", "to", "of", "for", "please",
    "tell", "about", "near", "next", "show", "hello", "hi", "thanks", "thank",
    "there", "this", "that", "and", "with", "will", "should", "want", "need",
    "help", "it", "be", "an", "a", "in", "on", "at", "from",
}

# "Explain this in Hindi", "मराठीत सांगा", "हिंदी में बताइए" …
_EXPLICIT_LATIN = re.compile(
    r"\b(?:in|into|to)\s+(english|hindi|marathi|gujarati|punjabi|bengali|"
    r"bangla|odia|oriya|tamil|telugu|kannada|malayalam|urdu)\b",
    re.I,
)
_EXPLICIT_NAMES = {
    "english": "en", "hindi": "hi", "marathi": "mr", "gujarati": "gu",
    "punjabi": "pa", "bengali": "bn", "bangla": "bn", "odia": "or",
    "oriya": "or", "tamil": "ta", "telugu": "te", "kannada": "kn",
    "malayalam": "ml", "urdu": "ur",
}
_EXPLICIT_NATIVE = (
    ("hi", re.compile(r"हिं?न?दी\s*(?:में|मे|त|मध्ये)|हिंदीत")),
    ("mr", re.compile(r"मराठी\s*(?:में|मे|त|मध्ये)|मराठीत")),
    ("en", re.compile(r"(?:अंग्रेज़ी|अंग्रेजी|इंग्लिश|इंग्रजी)\s*(?:में|मे|त|मध्ये)|इंग्रजीत")),
)


@dataclass(frozen=True)
class LanguageInfo:
    """
    The language to answer in.

    `code` is an ISO 639-1 code. `romanized` means Hindi or Marathi typed in
    Latin letters, which is answered the same way. `explicit` means the user
    asked for that language; `source` says how it was decided
    ("explicit", "text", "app" or "default").
    """

    code: str
    romanized: bool = False
    explicit: bool = False
    source: str = "text"

    @property
    def name(self) -> str:
        return LANGUAGE_NAMES.get(self.code, "the user's language")


def normalize_language(value: str | None) -> str:
    value = (value or "").strip().lower()[:2]
    return value if value in SUPPORTED_LANGUAGES else ""


def _explicit_request(text: str) -> str | None:
    match = _EXPLICIT_LATIN.search(text)
    if match:
        return _EXPLICIT_NAMES[match.group(1).lower()]
    for code, pattern in _EXPLICIT_NATIVE:
        if pattern.search(text):
            return code
    return None


def _devanagari_language(text: str, fallback: str) -> str:
    words = _DEVANAGARI_WORD.findall(text)
    marathi = sum(w in _MARATHI_HINTS for w in words) + 2 * text.count("ळ")
    hindi = sum(w in _HINDI_HINTS for w in words)
    if marathi > hindi:
        return "mr"
    if hindi > marathi:
        return "hi"
    return fallback if fallback in ("hi", "mr") else "hi"


def _latin_language(text: str) -> tuple[str | None, bool]:
    """('hi' | 'mr', True) for romanized Hindi/Marathi, ('en', False) for
    English, (None, False) when there is no signal (a bare name, "ok")."""
    words = _LATIN_WORD.findall(text.lower())
    scores = {
        "hi": sum(w in _ROMAN_HINDI for w in words),
        "mr": sum(w in _ROMAN_MARATHI for w in words),
    }
    strong = {
        code: any(w in _ROMAN_STRONG[code] for w in words) for code in ("hi", "mr")
    }
    best = max(("hi", "mr"), key=lambda c: (strong[c], scores[c]))
    english = sum(w in _ENGLISH_WORDS for w in words)
    if strong[best] or (scores[best] >= 2 and scores[best] >= english):
        return best, True
    if english:
        return "en", False
    return None, False


def analyze_language(text: str | None, fallback: str | None = None) -> LanguageInfo:
    """
    Decide the reply language from the user's own words.

    1. An explicit request ("answer in Marathi") wins.
    2. Otherwise the language of the question: its script, then word hints
       for Hindi vs Marathi and for romanized Hindi/Marathi vs English.
    3. Only when the text carries no language signal (empty, a photo with
       no caption, a bare place name) is `fallback` — the app language —
       used.
    """
    text = (text or "").strip()
    app_language = normalize_language(fallback)

    requested = _explicit_request(text)
    if requested:
        return LanguageInfo(requested, explicit=True, source="explicit")

    for code, pattern in _SCRIPTS:
        if pattern.search(text):
            return LanguageInfo(code)
    if _DEVANAGARI.search(text):
        return LanguageInfo(_devanagari_language(text, app_language))

    latin, romanized = _latin_language(text)
    if latin:
        return LanguageInfo(latin, romanized=romanized)
    if app_language:
        return LanguageInfo(app_language, source="app")
    return LanguageInfo("en", source="default")


def detect_language(text: str | None, fallback: str | None = None) -> str:
    """Reply language code for `text`; see `analyze_language`."""
    return analyze_language(text, fallback).code


def message(key: str, language: str = "en", **kwargs) -> str:
    entry = _MESSAGES[key]
    text = entry.get(language) or entry["en"]
    return text.format(**kwargs) if kwargs else text
