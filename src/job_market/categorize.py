"""Job-function categorization: normalization, weighted rules and tie-breaks.

Decisions D-026 and D-028. The definitions behind every rule are in
``docs/labelling_guide.md``; rule IDs such as T1 refer to its tie-break table.

How one title is categorized:

1. ``category_text`` builds a matching text from ``title_clean``: lower case,
   technical tokens protected (C++ -> cpp, .NET -> dotnet, Node.js -> nodejs,
   e-commerce -> ecommerce), punctuation removed, and simple plurals reduced
   ("videos" -> "video", "setters" -> "setter"). ``title_clean`` itself is
   never changed.
2. Every category has weighted patterns: 3 = specific phrase that almost
   always means the category ("power bi", "appointment setter"), 2 = clear
   word ("bookkeeper", "flutter"), 1 = generic word ("developer", "design").
   A category's score is the sum of the weights of its distinct matching
   patterns.
3. Tie-break rules settle the common overlaps (guide section 4).
4. Two separate tasks of different functions with no priority ("logo and
   website") give Other / Unclear, with both kept as secondary matches.

Titles with no rule match are left to the fallback classifier
(``steps/categorize.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .taxonomy import OTHER

# ---------------------------------------------------------------- matching text

_TECH_TOKENS = [
    (r"c\+\+", " cpp "),
    (r"c#", " csharp "),
    (r"f#", " fsharp "),
    (r"\.net\b", " dotnet "),
    (r"\basp\.net\b", " aspnet "),
    (r"\bnode\.?js\b", " nodejs "),
    (r"\bnext\.?js\b", " nextjs "),
    (r"\bnuxt\.?js\b", " nuxtjs "),
    (r"\bvue\.?js\b", " vuejs "),
    (r"\breact\.?js\b", " react "),
    (r"\bthree\.?js\b", " threejs "),
    (r"\bd3\.?js\b", " d3js "),
    (r"\be[-\s]?commerce\b", " ecommerce "),
    (r"\be[-\s]?book", " ebook"),
    (r"\be[-\s]?mail", " email"),
    (r"\bu\.?s\.?a?\b(?=[\s,.)-]|$)", " usa "),
    (r"\bui\s*/\s*ux\b", " ui ux "),
    (r"\bux\s*/\s*ui\b", " ui ux "),
    (r"\bvoice[-\s]?over", " voiceover"),
    (r"\bco[-\s]?founder", " cofounder"),
    (r"\bfull[-\s]?stack\b", " fullstack "),
    (r"\bfront[-\s]?end\b", " frontend "),
    (r"\bback[-\s]?end\b", " backend "),
    (r"\bwordpress\b", " wordpress "),
    (r"\bt[-\s]?shirt", " tshirt"),
    (r"\bpower\s?point\b", " powerpoint "),
    (r"\bpower\s?bi\b", " powerbi "),
    (r"\bchat\s?gpt\b", " chatgpt "),
    (r"\bgen\s?ai\b", " genai "),
    (r"\bweb\s?3\b", " web3 "),
    (r"\b2d\b", " 2d "),
    (r"\b3d\b", " 3d "),
]
_TECH_RES = [(re.compile(p, re.IGNORECASE), r) for p, r in _TECH_TOKENS]
_NON_WORD = re.compile(r"[^\w]+")
# Words ending in "s" that are not plurals, or whose singular would mislead.
_KEEP_S = frozenset(
    "ios aws saas css js sas sass gis dns cms sms os gps plus status canvas yes pos ups "
    "bus kubernetes windows pandas business process express address wordpress "
    "news series species physics mathematics economics ethics "
    "its his has was gas dynamics kids lens bonus campus focus nexus virus corpus".split()
)


def _singular(word: str) -> str:
    if len(word) <= 2 or word in _KEEP_S or word.endswith(("ss", "us", "is", "js")):
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s"):
        return word[:-1]
    return word


def category_text(title_clean: object) -> str:
    """The text the rules match: protected tech tokens, no punctuation, singular words."""
    if not isinstance(title_clean, str):
        return ""
    text = title_clean.casefold()
    for pattern, replacement in _TECH_RES:
        text = pattern.sub(replacement, text)
    words = _NON_WORD.sub(" ", text).replace("_", " ").split()
    return " ".join(_singular(w) for w in words)


# ---------------------------------------------------------------- rules

# Each entry: (category, weight, pattern). Patterns are regular expressions
# matched as whole words on ``category_text``; write them in singular form.
_RULES: list[tuple[str, int, str]] = []


def _add(category: str, weight: int, *patterns: str) -> None:
    for pattern in patterns:
        _RULES.append((category, weight, pattern))


# 1 Web development
_add("web_development", 3, "wordpress", "webflow", "wix", "squarespace", "shopify theme", "shopify developer",
     "shopify website", "shopify store setup", "shopify plus", "shopify store design", "liquid", "shopify expert", "landing page", "web developer", "web development",
     "website developer", "website development", "web design", "website design", "website designer", "web designer",
     "fullstack", "frontend", "elementor", "divi", "woocommerce", "web app", "webapp", "bubble io", "bubble",
     "framer", "laravel", "php", "nextjs", "nuxtjs", "vuejs", "angular", "react", "django", "html", "css",
     "javascript", "typescript", "website", "web page", "webpage", "site", "kajabi", "godaddy", "hubspot cms",
     "go high level website", "mern", "mern stack", "mean stack", "mevn", "lamp stack", "funnel builder", "clickfunnel", "sales funnel")
_add("web_development", 2, "shopify", "nodejs", "backend", "web", "seo friendly website", "domain", "hosting", "ghl",
     "gohighlevel", "go high level", "membership site", "plugin")
# 2 Mobile development
_add("mobile_development", 3, "mobile app", "ios", "android", "flutter", "react native", "swift", "swiftui", "kotlin",
     "iphone app", "ipad app", "app store", "play store", "google play", "xamarin", "ionic", "mobile application",
     "mobile development", "mobile developer", "apk", "testflight", "iphone application")
_add("mobile_development", 2, "app developer", "app development", "iphone", "native app")
_add("mobile_development", 1, "app")
# 3 Software & IT
_add("software_it", 3, "python script", "automation", "automate", "scraper", "scraping", "scrape", "crawler",
     "zapier", "make com", "integromat", "n8n", "api integration", "api", "chrome extension", "browser extension",
     "devops", "aws", "azure", "google cloud", "gcp", "docker", "kubernetes", "linux", "server", "vps",
     "cybersecurity", "penetration test", "pentest", "it support", "network", "firewall", "database", "postgresql",
     "mysql", "mongodb", "blockchain", "smart contract", "solidity", "web3", "erc 20", "token", "nft", "crypto bot",
     "unity", "unreal", "game developer", "game development", "roblox", "godot", "telegram bot", "discord bot",
     "trading bot", "bot developer", "desktop app", "salesforce", "zoho", "odoo", "netsuite", "sap", "erp", "crm setup",
     "microsoft 365", "office 365", "sharepoint", "power automate", "power apps", "airtable", "google apps script",
     "apps script", "vba", "macro", "excel vba", "rpa", "selenium", "puppeteer", "playwright", "software developer",
     "software development", "software engineer", "programmer", "golang", "rust", "java", "cpp", "csharp", "dotnet",
     "aspnet", "ruby on rails", "rails", "embedded software", "firmware", "qa tester", "qa engineer", "software testing",
     "test automation", "github", "git", "microservice", "saas")
# T1/T4 decide when the app is mobile or web; an app with no platform is software (decision D-029).
_add("software_it", 3, r"(?:create|build|develop|make|fix|code)\w* (?:\w+ ){0,4}(?:app|application)", "apify")
_add("software_it", 2, "python", "developer", "script", "bot", "integration", "software", "coding", "code",
     "programming", "engineer", "it", "cloud", "security", "hack", "migration", "deploy", "bug", "fix error")
# 4 AI & ML
_add("ai_ml", 3, "machine learning", "deep learning", "llm", "large language model", "gpt", "chatgpt", "openai",
     "chatbot", "chat bot", "ai chatbot", "ai agent", "ai developer", "ai engineer", "ai model", "ai expert",
     "ai specialist", "ai automation", "ai integration", "ai app", "ai tool", "ai assistant", "ai solution",
     "ai consultant", "nlp", "natural language processing", "computer vision", "object detection", "image recognition",
     "langchain", "llama", "fine tune", "finetune", "rag", "vector database", "prompt engineer", "prompt engineering",
     "genai", "generative ai", "artificial intelligence", "ml engineer", "ml model", "neural network", "pytorch",
     "tensorflow", "hugging face", "huggingface", "stable diffusion", "whisper", "voice agent", "voice ai",
     "conversational ai", "data scientist machine learning", "yolo", "opencv", "mediapipe", "vapi", "retell")
_add("ai_ml", 2, "ai", "ml", "gemini", "claude", "copilot", "agent")
# 5 Data & analytics
_add("data_analytics", 3, "data analyst", "data analysis", "data analytic", "data scientist", "data science",
     "powerbi", "tableau", "looker", "looker studio", "data studio", "dashboard", "data visualization",
     "data visualisation", "excel expert", "excel formula", "excel spreadsheet", "excel model", "google sheet expert",
     "spreadsheet expert", "statistical analysis", "statistic", "spss", "stata", "r programming", "rstudio",
     "regression analysis", "survey analysis", "kpi report", "bigquery", "snowflake", "data engineer", "etl",
     "data pipeline", "data warehouse", "dbt", "sql query", "data modeling", "data modelling", "analytics report",
     "quantitative research", "econometric")
_add("data_analytics", 2, "excel", "spreadsheet", "google sheet", "sql", "data", "analysis", "analyst", "report",
     "reporting", "analytics", "forecast")
# 6 Design & creative
_add("design_creative", 3, "graphic design", "graphic designer", "logo", "logo design", "branding", "brand identity",
     "brand book", "brand guideline", "ui ux", "ui design", "ux design", "ui designer", "ux designer", "figma", "mockup",
     "mock up", "wireframe", "prototype design", "illustration", "illustrator", "illustrate", "canva", "photoshop",
     "banner", "flyer", "poster", "brochure", "packaging", "label design", "book cover", "cover design", "infographic",
     "thumbnail", "youtube thumbnail", "tshirt", "merch design", "sticker", "icon design", "vector", "character design",
     "concept art", "3d model", "3d modeling", "3d modeling", "3d render", "3d artist", "3d design", "rendering",
     "blender", "cinema 4d", "c4d", "presentation design", "pitch deck design", "slide design", "powerpoint design",
     "powerpoint", "pitch deck", "social media post design", "social media graphic", "carousel design", "ad creative",
     "creative design", "nft art", "digital art", "art", "artist", "drawing", "comic", "manga", "children book illustration",
     "tattoo", "font", "typography", "business card", "letterhead", "magazine layout", "layout design", "indesign",
     "product design mockup", "visual design", "visual artist", "web banner", "email template design", "gif",
     "facebook cover", "cover photo", "channel art", "youtube banner", "linkedin banner", "menu design",
     "product designer")
_add("design_creative", 2, "designer", "graphic", "creative", "visual", "image", "design")
# 7 Video & animation
_add("video_animation", 3, "video editor", "video editing", "video edit", "edit video", "youtube video",
     "youtube editor", "tiktok video", "reel", "short form", "shorts", "animation", "animator", "animated",
     "motion graphic", "motion design", "after effect", "premiere", "davinci", "final cut", "explainer video",
     "whiteboard animation", "2d animation", "3d animation", "videographer", "videography", "video production",
     "video creator", "ugc video", "ugc creator", "video ad", "video content", "faceless youtube", "cinematic",
     "vfx", "color grading", "colour grading", "unboxing video", "promo video", "music video", "wedding video",
     "video shoot", "film", "filmmaker")
_add("video_animation", 2, "video", "youtube", "tiktok", "clip", "footage", "vlog", "ugc", "trim")
_add("video_animation", 1, "editor", "editing")
# 8 Photography
_add("photography", 3, "photographer", "photography", "photo shoot", "photoshoot", "headshot", "photo editing",
     "photo editor", "photo retouch", "retouch", "retoucher", "retouching", "background removal", "remove background",
     "product photo", "product photography", "real estate photo", "drone photo", "lightroom", "photo restoration",
     "photo edit", "edit photo", "image editing", "image editor", "edit image")
_add("photography", 2, "photo", "picture")
# 9 Writing & content
_add("writing_content", 3, "writer", "copywriter", "copywriting", "content writer", "content writing", "blog post",
     "blog writer", "blog article", "article writer", "article writing", "ghostwriter", "ghostwriting", "ghost writer",
     "proofread", "proofreader", "proofreading", "editor for book", "book editor", "copy editor", "copyedit",
     "line editing", "developmental edit", "script writer", "scriptwriter", "script writing", "screenplay",
     "screenwriter", "ebook", "book writing", "write a book", "technical writer", "technical writing", "resume",
     "cv writing", "cover letter", "grant writer", "grant writing", "speech writer", "newsletter writer",
     "product description", "sale page copy", "website copy", "ad copy", "email copy", "seo article", "seo content",
     "seo writer", "seo blog", "story writer", "storyteller", "novel", "poem", "poetry", "lyric", "essay", "thesis",
     "dissertation", "document editing", "manuscript", "research paper", "white paper", "whitepaper", "case study writer", "ux writer", "content creator writer")
_add("writing_content", 2, "writing", "write", "article", "blog", "content", "copy", "story", "script", "book",
     "author", "editing service")
# 10 Translation & transcription
_add("translation_transcription", 3, "translator", "translation", "translate", "transcription", "transcribe",
     "transcriber", "transcript", "subtitle", "subtitling", "caption", "captioning", "localization", "localisation",
     "interpreter", "interpreting", "post editor", "machine translation post")
_add("translation_transcription", 2, "native speaker", "bilingual", "english to", "to english", "spanish to",
     "french to", "german to")
# 11 Digital marketing
_add("digital_marketing", 3, "seo", "search engine optimization", "social media manager", "social media management",
     "social media marketing", "social media marketer", "smm", "smma", "google ad", "facebook ad", "meta ad",
     "instagram ad", "tiktok ad", "linkedin ad", "amazon ppc", "amazon ad", "ppc", "media buyer", "media buying",
     "paid ad", "paid social", "ad campaign", "ad manager", "ads manager", "email marketing", "email marketer",
     "klaviyo", "mailchimp", "email campaign", "email flow", "influencer", "ugc campaign", "ugc strategy",
     "digital marketing", "digital marketer", "growth marketer", "growth marketing", "growth hacker", "marketing manager",
     "marketing specialist", "marketing strategist", "marketing strategy", "marketing campaign", "marketing expert",
     "marketing consultant", "content strategy", "content strategist", "content marketing", "community manager",
     "aso", "app store optimization", "conversion rate optimization", "cro", "ga4", "google analytic", "google tag",
     "tag manager", "facebook pixel", "pixel", "tracking setup", "affiliate marketing", "pr", "public relation",
     "press release", "brand ambassador", "pinterest manager", "pinterest marketing", "youtube growth",
     "youtube channel manager", "instagram growth", "backlink", "link building", "local seo", "seo audit", "google business profile",
     "gmb", "reputation management", "review management", "marketing")
_add("digital_marketing", 2, "social media", "instagram", "facebook", "linkedin", "pinterest", "twitter", "marketer",
     "promotion", "promote", "campaign", "advertising", "advertisement", "traffic", "growth", "content creator", "brand",
     "ad", "media outreach", "publicity")
# 12 Sales & lead generation
_add("sales_lead_generation", 3, "lead generation", "lead gen", "lead list", "appointment setter", "appointment setting",
     "cold caller", "cold calling", "cold call", "cold email", "cold outreach", "telemarketer", "telemarketing",
     "sale representative", "sale rep", "sale agent", "sale manager", "sale executive", "sale closer", "closer",
     "high ticket", "business development", "bdr", "sdr", "b2b sale", "inside sale", "outbound", "prospecting",
     "linkedin outreach", "email outreach", "find client", "find customer", "get client", "commission only",
     "commission based", "setter", "dialer", "lead qualification", "sale specialist", "sale")
_add("sales_lead_generation", 2, "lead", "outreach", "b2b", "client acquisition", "customer acquisition")
# 13 Admin & virtual assistance
_add("admin_virtual_assistance", 3, "virtual assistant", "va", "executive assistant", "personal assistant",
     "administrative assistant", "admin assistant", "admin support", "data entry", "copy paste", "typing", "typist",
     "web research", "internet research", "online research", "data collection", "list building", "email management",
     "calendar management", "inbox management", "crm update", "crm management", "pdf to excel", "pdf to word",
     "document formatting", "file organization", "virtual assistance", "back office", "data mining")
_add("admin_virtual_assistance", 2, "assistant", "admin", "administrative", "research", "researcher", "entry",
     "organize", "scheduling", "secretary", "receptionist", "clerk", "operation assistant")
# 14 Customer service
_add("customer_service", 3, "customer service", "customer support", "chat support", "email support", "phone support",
     "support agent", "support specialist", "support representative", "call center", "call centre", "helpdesk",
     "help desk", "customer success", "customer care", "live chat", "chat agent", "inbound call", "zendesk",
     "freshdesk", "gorgias", "moderator", "chat moderator", "community moderator", "technical support")
_add("customer_service", 2, "support", "customer")
# "chatter" counts only with a stated task (T28/T29); a bare "chatter" is Other (T30).
_add("customer_service", 3, r"chatter\w* (?:\w+ ){0,5}(?:support|customer|question|inquir\w*)")
_add("sales_lead_generation", 3, r"chatter\w* (?:\w+ ){0,5}(?:upsell\w*|sell\w*|sale|ppv|convert\w*|conversion)")
# 15 Accounting & finance
_add("accounting_finance", 3, "bookkeeper", "bookkeeping", "book keeping", "accountant", "accounting", "quickbooks",
     "xero", "sage", "tax return", "tax preparation", "tax", "payroll", "cpa", "financial statement", "financial model",
     "financial modeling", "financial modelling", "financial analyst", "financial analysis", "valuation", "cfo",
     "fractional cfo", "bank reconciliation", "reconciliation", "account payable", "account receivable", "invoicing",
     "invoice", "medical biller", "medical billing", "billing specialist", "financial audit", "auditor", "budgeting",
     "cash flow", "profit and loss", "p l", "vat", "gst", "sale tax", "irs", "1099", "w2", "excel financial",
     "cleaning up the book", "clean up the book", "catch up book", "investment analyst", "equity research",
     "financial planning", "fp a")
_add("accounting_finance", 2, "audit", "finance", "financial", "book", "billing", "budget", "expense")
# 16 Legal
_add("legal", 3, "lawyer", "attorney", "legal", "paralegal", "contract review", "contract drafting", "draft contract",
     "terms and condition", "term of service", "terms of service", "privacy policy", "trademark", "patent",
     "copyright", "company registration", "company formation", "incorporation", "register company", "llc formation",
     "visa", "immigration", "gdpr", "compliance", "notary", "lawsuit", "litigation", "dmca", "bankruptcy",
     "nda", "legal advice", "legal consultant", "sec filing", "13d", "regulatory filing", "compliance filing")
_add("legal", 2, "contract", "law", "regulation", "license", "licence")
# 17 Engineering & architecture
_add("engineering_architecture", 3, "autocad", "auto cad", "cad", "solidwork", "solidworks", "revit", "sketchup",
     "fusion 360", "catia", "creo", "inventor", "mechanical engineer", "mechanical engineering", "electrical engineer",
     "electrical engineering", "civil engineer", "civil engineering", "structural engineer", "structural engineering",
     "pcb", "pcb design", "circuit", "schematic", "arduino", "raspberry pi", "esp32", "embedded system", "iot device",
     "architect", "architecture", "architectural", "floor plan", "interior design", "interior designer", "landscape design",
     "technical drawing", "shop drawing", "product engineering", "hvac", "mep", "bim", "3d printing", "3d print",
     "injection mold", "sheet metal", "fea", "cfd", "matlab", "simulink", "plc", "robotics", "drone design",
     "product development engineer", "industrial design", "openscad", "permit drawing", "construction drawing", "kitchen design")
_add("engineering_architecture", 2, "engineering", "mechanical", "electrical", "electronic", "hardware",
     "prototype", "construction", "renovation")
# 18 Audio & music
_add("audio_music", 3, "voiceover", "voice actor", "voice actress", "voice talent", "voice artist", "narrator",
     "narration", "audiobook", "podcast editor", "podcast editing", "podcast producer", "podcast production",
     "audio editor", "audio editing", "audio engineer", "mixing", "mastering", "mix and master", "music producer",
     "music production", "composer", "compose music", "songwriter", "singer", "vocalist", "beat", "jingle",
     "sound design", "sound designer", "sound effect", "audio production", "dubbing", "dub")
_add("audio_music", 2, "voice", "podcast", "audio", "music", "song", "sound")
# 19 E-commerce operations
_add("ecommerce_operations", 3, "amazon listing", "product listing", "listing optimization", "amazon seller",
     "amazon store", "amazon fba", "fba", "amazon account manager", "amazon va", "amazon expert", "etsy",
     "ebay", "walmart", "product upload", "upload product", "product research", "dropshipping", "dropship",
     "shopify store manager", "store manager", "ecommerce manager", "ecommerce specialist", "ecommerce va",
     "ecommerce virtual assistant", "inventory", "order fulfillment", "order processing", "tiktok shop",
     "amazon brand registry", "a plus content", "a content", "sourcing product", "product sourcing", "printful",
     "print on demand", "pod")
_add("ecommerce_operations", 2, "amazon", "ecommerce", "store", "listing")
_add("ecommerce_operations", 1, "product")
# 20 Business, project management & consulting
_add("business_project_management", 3, "project manager", "project management", "product manager",
     "product management", "product owner", "scrum master", "program manager", "operations manager",
     "operation manager", "business consultant", "business consulting", "management consultant", "consultant",
     "consulting", "business plan", "business strategy", "strategy consultant", "business analyst",
     "market research", "competitor research", "competitive analysis", "feasibility study", "sourcing agent",
     "procurement", "supply chain", "logistic", "business coach", "coaching", "coach", "mentor", "startup advisor",
     "advisor", "chief of staff", "cofounder", "fractional coo", "coo", "ceo", "process improvement", "sop",
     "jira", "asana", "clickup", "monday com", "notion setup", "event planner",
     "event management", "travel coordinator", "travel planner", "pitch deck consultant", "investor relation",
     "fundraising", "grant research", "real estate analyst", "underwriting", "acquisition manager")
_add("business_project_management", 2, "manager", "management", "strategy", "business", "startup", "planning",
     "coordinator", "investor", "operations", "operation")
_add("business_project_management", 1, "partner")
# 21 Education & tutoring
_add("education_tutoring", 3, "tutor", "tutoring", "teacher", "teaching", "teach", "lesson", "course creation",
     "course creator", "online course", "create a course", "curriculum", "instructional design", "instructional designer",
     "e learning", "elearning", "lms", "training program", "trainer", "instructor", "exam prep", "homework help",
     "language teacher", "english teacher", "math tutor", "music lesson", "piano teacher", "guitar teacher",
     "coding instructor", "workshop facilitator", "educational content", "education consultant", "academic coach")
_add("education_tutoring", 2, "course", "training", "education", "educational", "learning", "student", "class",
     "academic", "school")
# 22 HR & recruiting
_add("hr_recruiting", 3, "recruiter", "recruiting", "recruitment", "headhunter", "headhunting", "talent acquisition",
     "talent sourcer", "candidate sourcing", "source candidate", "hr consultant", "hr manager", "hr specialist",
     "human resource", "employee handbook", "hr policy", "onboarding process", "hr generalist", "hr assistant",
     "staffing", "job description writer", "interview candidate")
_add("hr_recruiting", 2, "hr", "talent", "hiring process", "employee")

_PLAIN = re.compile(r"[a-z0-9 ]+")


def _normalize_pattern(pattern: str) -> str:
    """Plain word patterns go through the same normalization as titles, so a
    pattern written as "sales rep" or "google ads" still matches."""
    return category_text(pattern) if _PLAIN.fullmatch(pattern) else pattern


# Plain word patterns are looked up as word n-grams (fast); the few patterns
# with regular-expression syntax are searched with a regex.
_PHRASES: dict[str, list[tuple[int, str, int]]] = {}
_REGEX_RULES: list[tuple[int, str, int, re.Pattern[str]]] = []
for _index, (_category, _weight, _pattern) in enumerate(_RULES):
    if _PLAIN.fullmatch(_pattern):
        _entries = _PHRASES.setdefault(category_text(_pattern), [])
        if all(c != _category for _, c, _ in _entries):   # a repeated pattern counts once
            _entries.append((_index, _category, _weight))
    else:
        _REGEX_RULES.append((_index, _category, _weight, re.compile(rf"\b{_pattern}\b")))
_MAX_WORDS = max(len(p.split()) for p in _PHRASES)

# Industry tags (decision D-026): client sector, multi-label, never a category.
INDUSTRY_PATTERNS = {
    "real_estate": r"\b(real estate|realtor|realty|property|propertie|rental|airbnb|mortgage|zillow|landlord|tenant)\b",
    "healthcare": r"\b(medical|health|healthcare|clinic|dental|dentist|therapy|therapist|pharma\w*|hospital|nurse|doctor|patient|fitness|nutrition|wellness)\b",
    "education": r"\b(school|university|student|elearning|e learning|academy|education|educational)\b",
    "ecommerce": r"\b(ecommerce|online store|shopify|amazon|etsy|ebay|dropshipping|walmart)\b",
    "crypto_web3": r"\b(crypto|cryptocurrency|blockchain|nft|web3|defi|token|bitcoin|ethereum|solana)\b",
    "finance": r"\b(fintech|trading|forex|insurance|banking|bank|loan|investment|investor|stock)\b",
    "legal": r"\b(law firm|attorney|lawyer|legal practice|paralegal)\b",
}
_INDUSTRY_RES = {tag: re.compile(p) for tag, p in INDUSTRY_PATTERNS.items()}


def industry_tags(text: str) -> list[str]:
    return [tag for tag, pattern in _INDUSTRY_RES.items() if pattern.search(text)]


# ---------------------------------------------------------------- scoring


@dataclass
class RuleResult:
    category: str | None              # None: no rule matched (left to the classifier)
    method: str                       # "rule", "two_tasks", "no_match"
    score: int = 0
    matched_terms: list[str] = field(default_factory=list)
    secondary: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)


def score_text(text: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Category scores (sum of weights of distinct matching patterns) and matched terms."""
    words = text.split()
    hits: dict[int, tuple[str, int, str]] = {}
    for n in range(1, _MAX_WORDS + 1):
        for i in range(len(words) - n + 1):
            gram = " ".join(words[i : i + n])
            for index, category, weight in _PHRASES.get(gram, ()):
                hits.setdefault(index, (category, weight, gram))
    for index, category, weight, pattern in _REGEX_RULES:
        match = pattern.search(text)
        if match:
            hits.setdefault(index, (category, weight, match.group(0)))
    scores: dict[str, int] = {}
    terms: dict[str, list[str]] = {}
    for index in sorted(hits):
        category, weight, term = hits[index]
        scores[category] = scores.get(category, 0) + weight
        terms.setdefault(category, []).append(term)
    return scores, terms


_HAS_CACHE: dict[str, re.Pattern[str]] = {}


def _has(text: str, pattern: str) -> bool:
    """Whole-word search; plain alternatives are normalized like the titles."""
    compiled = _HAS_CACHE.get(pattern)
    if compiled is None:
        parts = "|".join(_normalize_pattern(part) for part in pattern.split("|"))
        compiled = _HAS_CACHE[pattern] = re.compile(rf"\b(?:{parts})\b")
    return compiled.search(text) is not None


# Pairwise tie-breaks (guide section 4): (winner, loser, condition on the text or
# None for always). Applied in order; a loser is removed only if both are present.
_STRONG_AI = r"chatbot|chat bot|llm|gpt|chatgpt|openai|machine learning|deep learning|ai agent|ai developer|ai engineer|ai model|nlp|computer vision|langchain|rag|fine tune|finetune|genai|generative ai|ai automation|ai integration|ai app|ai tool|ai assistant|ai solution|prompt engineer\w*|voice agent|voice ai|conversational ai|neural network|pytorch|tensorflow|mediapipe|opencv|yolo"
_AI_AS_TOOL_OUTPUT = ("video_animation", "design_creative", "writing_content", "audio_music", "photography")
_BUILD_WEB = r"develop\w*|developer|build|builder|wordpress|webflow|wix|shopify|elementor|woocommerce|html|css|php|react|fullstack|frontend|backend|landing page|website|web page|webpage|site|funnel"
_BUILDING = r"build\w*|develop\w*|developer|code|coding|program\w*|backend|frontend|fullstack|saas|api|react|nextjs|django|laravel|php|wordpress|webflow|wix|shopify|html|css|elementor"
_DATA_TOOL = r"powerbi|tableau|looker|looker studio|data studio|excel|google sheet|spreadsheet|analy\w*|kpi|report\w*|metric"
# (winner, loser, condition or None for always[, unless]): the loser is removed
# when both are present, the condition matches and the "unless" pattern does not.
_PAIR_RULES: list[tuple] = [
    ("mobile_development", "web_development", None),                                       # T1
    ("mobile_development", "software_it", None),                                           # T1
    ("ai_ml", "software_it", _STRONG_AI),                                                  # T2
    ("ai_ml", "web_development", _STRONG_AI),                                              # T2
    ("ai_ml", "data_analytics", _STRONG_AI),                                               # T2
    ("ai_ml", "mobile_development", _STRONG_AI),                                           # T2
    ("software_it", "web_development", r"scraper|scraping|scrape|crawler|data extraction"),  # T6: scraping a website is not building one
    ("design_creative", "web_development", r"illustrat\w*|artist|artwork|art|drawing|icon", _BUILDING),  # T5: art for a website
    ("web_development", "data_analytics", r"dashboard", _DATA_TOOL),                     # T7: a coded dashboard is a product
    ("software_it", "data_analytics", r"dashboard", _DATA_TOOL),                         # T7
    ("web_development", "sales_lead_generation", r"build\w*|develop\w*|developer|backend|frontend|saas|app|api"),  # building a sales product
    ("software_it", "sales_lead_generation", r"build\w*|develop\w*|developer|backend|frontend|saas|app|api"),
    ("software_it", "digital_marketing", r"api|sdk|script|integration|automation"),       # building for ads is software
    ("web_development", "software_it", None),                                              # T4
    ("web_development", "design_creative", _BUILD_WEB),                                    # T4 vs T5
    ("design_creative", "web_development", r"figma|ui ux|ui design|ux design|wireframe|mockup|mock up"),  # T5
    ("design_creative", "mobile_development", r"figma|ui ux|ui design|ux design|wireframe|mockup|mock up"),  # T5
    ("software_it", "data_analytics", r"scraper|scraping|scrape|crawler|automation|automate|api|script|bot|vba|macro|apps script"),  # T6
    ("data_analytics", "admin_virtual_assistance", r"analysis|analyst|dashboard|powerbi|tableau|excel formula|excel expert|statistic\w*|looker|model"),  # T7
    ("admin_virtual_assistance", "data_analytics", r"data entry|copy paste|typing|typist|data collection|list building|web research|internet research|online research|data mining"),  # T8
    ("writing_content", "software_it", r"video|youtube|ad|explainer|reel|tiktok|podcast|film|movie|commercial|play|story"),  # T9 (a script for a video is writing, not code)
    ("writing_content", "video_animation", r"script|scriptwriter|script writer|writer|writing|copywriter"),  # T9
    ("audio_music", "video_animation", r"voiceover|voice actor|voice talent|voice artist|narrator|narration|dubbing"),  # T10
    ("design_creative", "video_animation", r"thumbnail|banner|post design|graphic"),       # T11
    ("design_creative", "digital_marketing", r"thumbnail|banner|cover|cover photo|post design|social media graphic|flyer|logo|channel art"),  # T11
    ("video_animation", "digital_marketing", r"video edit\w*|video editor|editing|edit video|videographer|ugc video|ugc creator|animation|animator|filming|film"),  # T12, T26
    ("digital_marketing", "design_creative", r"social media manager|social media management|social media marketing|seo|ppc|google ad|facebook ad|meta ad|ad campaign|media buyer"),  # T13
    ("digital_marketing", "writing_content", r"seo strategy|seo audit|seo specialist|seo expert|seo manager|social media manager|marketing manager|content strategy"),  # T13
    ("digital_marketing", "video_animation", r"social media manager|youtube growth|youtube channel manager|ugc campaign|ugc strategy|influencer"),  # T13, T27
    ("sales_lead_generation", "digital_marketing", r"lead generation|lead gen|appointment sett\w*|setter|cold call\w*|cold email|cold outreach|closer|telemarket\w*|business development|sale rep\w*"),  # T14
    ("ecommerce_operations", "web_development", r"listing|product upload|upload product|store manager|product research|inventory|fba|etsy|ebay|amazon seller|dropship\w*"),  # T15
    ("web_development", "ecommerce_operations", r"develop\w*|developer|theme|setup|set up|build|builder|website|landing page|liquid|custom code|store design"),  # T4
    ("ecommerce_operations", "admin_virtual_assistance", r"amazon|etsy|ebay|shopify|ecommerce|listing|product upload|upload product|walmart"),  # T15
    ("digital_marketing", "ecommerce_operations", r"amazon ppc|amazon ad|ppc|ad campaign|ad|ad manager|advertising|sponsored", r"api|sdk|script|integration|develop\w*|developer|build\w*"),  # T16
    ("software_it", "ecommerce_operations", r"apify|scrap\w*|crawl\w*|data extraction"),  # T6
    ("customer_service", "admin_virtual_assistance", r"customer service|customer support|chat support|support agent|call center|call centre|helpdesk|help desk|customer success|customer care|live chat"),  # T17
    ("customer_service", "sales_lead_generation", r"customer service|customer support|chat support|support agent|helpdesk|help desk|inbound call"),  # T17
    ("business_project_management", "admin_virtual_assistance", r"project manager|project management|operations manager|operation manager|consultant|business plan|product manager"),  # T18
    ("digital_marketing", "accounting_finance", r"seo|seo audit|google ad|facebook ad|ppc|marketing"),  # SEO/ads audit is marketing
    ("digital_marketing", "business_project_management", r"pr|public relation|press release|press|media outreach|publicity|pitch\w* (?:\w+ )?media|ad|ppc|seo|social media|campaign|marketing"),  # T13: PR, ads and SEO managers are marketing
    ("hr_recruiting", "business_project_management", r"recruit\w*|headhunt\w*|talent acquisition|hr|human resource"),  # recruitment consulting is HR
    ("writing_content", "legal", r"article|blog|post|newsletter|content writer|copywrit\w*"),  # writing about a legal topic
    ("accounting_finance", "business_project_management", r"bookkeep\w*|accountant|accounting|tax|financial model\w*|financial statement|cfo|payroll|valuation"),  # T19
    ("accounting_finance", "data_analytics", r"bookkeep\w*|accountant|accounting|tax|financial model\w*|financial statement|cfo|payroll|valuation|financial analys\w*"),  # T19
    ("engineering_architecture", "design_creative", r"cad|openscad|autocad|solidwork\w*|revit|sketchup|interior design\w*|architect\w*|floor plan|pcb|technical drawing|kitchen design|landscape design"),  # T20
    ("photography", "design_creative", r"photographer|photography|photo shoot|photoshoot|retouch\w*|photo edit\w*|edit photo|background removal|headshot"),  # T21
    ("translation_transcription", "writing_content", r"translat\w*|transcri\w*|subtitl\w*|caption\w*|locali[sz]ation"),  # T22
    ("education_tutoring", "writing_content", r"tutor\w*|teach\w*|course|curriculum|lesson|instructor|trainer"),  # T23
    ("legal", "business_project_management", None),                                       # T24
    ("legal", "admin_virtual_assistance", None),                                           # T24
    ("accounting_finance", "hr_recruiting", r"payroll"),                                   # T34
]


# Work outside all 22 functions (guide section 5): consumer-style testing and
# survey or research participation. Technical testing (QA, software tester,
# test automation) is Software & IT and is never matched here.
_OUT_OF_SCOPE = (
    r"mystery shop\w*|secret shopper|paid survey\w*|survey participant\w*|"
    r"(?:take|complete|fill|answer|do) (?:\w+ ){0,4}survey|"
    r"participate in (?:a |an |our |the )*(?:survey|study|research)|focus group|"
    r"beta tester|product tester|usability test\w* participant\w*|user testing participant\w*|"
    r"test (?:a |an |our |my )?physical product"
)
_TECHNICAL_TESTING = r"qa|quality assurance|software test\w*|software tester|test automation|automated test\w*|unit test\w*"
# Words that alone never say what the work is (T30).
_NO_FUNCTION = r"chatter"


def _apply_ai_as_tool(scores: dict[str, int], text: str) -> None:
    """T3: AI used as a tool for another output -> the output's category wins."""
    if "ai_ml" in scores and not _has(text, _STRONG_AI):
        if any(c in scores for c in _AI_AS_TOOL_OUTPUT):
            scores.pop("ai_ml")


# T25: "recruitment / recruiting" followed by a job role means the job is that
# role ("recruiting video editors"). The title stays HR when the word after it
# names recruitment work itself, or when other HR words appear ("recruiter").
_RECRUIT_INTRO = r"recruitment|recruiting"
_RECRUIT_WORK = (
    r"(?:recruitment|recruiting) (?:process|agency|agencie|consultant|consulting|specialist|coordinator|"
    r"strategy|strategist|campaign|manager|partner|assistant|team|lead|officer|support|outsourcing|firm|expert)"
)


def _apply_recruitment(scores: dict[str, int], terms: dict[str, list[str]], text: str) -> None:
    hr_terms = set(terms.get("hr_recruiting", []))
    if "hr_recruiting" not in scores or len(scores) < 2:
        return
    if hr_terms <= {"recruitment", "recruiting"} and not _has(text, _RECRUIT_WORK):
        scores.pop("hr_recruiting")


def _apply_pairs(scores: dict[str, int], text: str) -> None:
    for winner, loser, condition, *unless in _PAIR_RULES:
        if winner in scores and loser in scores and (condition is None or _has(text, condition)):
            if unless and _has(text, unless[0]):
                continue
            scores.pop(loser)


def _resolve(text: str, min_score: int) -> tuple[dict[str, int], dict[str, int], dict[str, list[str]]]:
    """Raw scores, scores after threshold and tie-breaks, and matched terms."""
    raw, terms = score_text(text)
    scores = {c: s for c, s in raw.items() if s >= min_score}
    if scores:
        _apply_recruitment(scores, terms, text)
        _apply_ai_as_tool(scores, text)
        _apply_pairs(scores, text)
    return raw, scores, terms


def _ranked(scores: dict[str, int]) -> list[str]:
    return sorted(scores, key=lambda c: (-scores[c], c))


# Two-deliverable rule (guide section 4). The title is split at joiners; each
# part is categorized on its own. Two parts with strong evidence (score >= 3)
# for different functions are two separate pieces of work. A part marked as
# minor ("a small logo", "also") gives priority to the other part.
_JOINER = re.compile(r"\s(?:and|&|\+)\s|\s/\s")
_MINOR = r"small|minor|quick|simple|also|bonus|optional|basic"
STRONG_PART_SCORE = 3
# Pairs settled unconditionally by a tie-break are one piece of work in two
# technologies ("iOS & mobile game developer", "Python and React developer").
_SAME_WORK = {frozenset(rule[:2]) for rule in _PAIR_RULES if rule[2] is None}


def _part_categories(title: str, min_score: int) -> list[tuple[str, bool]]:
    """(top category, is_minor) for every joined part with strong evidence."""
    found: list[tuple[str, bool]] = []
    for part in _JOINER.split(title.casefold()):
        text = category_text(part)
        _, scores, _ = _resolve(text, min_score)
        if scores:
            top = _ranked(scores)[0]
            if scores[top] >= STRONG_PART_SCORE:
                found.append((top, _has(text, _MINOR)))
    return found


def categorize_title(title_clean: object, min_score: int = 2) -> RuleResult:
    """Apply the rules to one title. A category needs at least ``min_score`` points."""
    text = category_text(title_clean)
    if not text:
        return RuleResult(None, "no_match")
    raw, scores, terms = _resolve(text, min_score)
    all_matched = _ranked(raw)
    if _has(text, _OUT_OF_SCOPE) and not _has(text, _TECHNICAL_TESTING):
        found = re.search(rf"\b(?:{_OUT_OF_SCOPE})\b", text)
        return RuleResult(OTHER, "rule", 0, [found.group(0)] if found else [], all_matched, dict(scores))
    if not scores:
        if _has(text, _NO_FUNCTION):
            return RuleResult(OTHER, "rule", 0, ["chatter"], all_matched, {})
        return RuleResult(None, "no_match", matched_terms=[t for c in all_matched for t in terms[c]])
    best = _ranked(scores)[0]
    secondary = [c for c in all_matched if c != best]

    if isinstance(title_clean, str) and _JOINER.search(title_clean.casefold()):
        parts = _part_categories(title_clean, min_score)
        major = list(dict.fromkeys(c for c, minor in parts if not minor))
        distinct = list(dict.fromkeys(c for c, _ in parts))
        if len(major) == 1 and len(distinct) > 1:
            best = major[0]                      # the other part is marked minor
            secondary = [c for c in all_matched if c != best]
        elif len(major) > 1 and not (len(major) == 2 and frozenset(major) in _SAME_WORK):
            matched = [t for c in major for t in terms.get(c, [])]
            return RuleResult(OTHER, "two_tasks", 0, matched, major + [c for c in all_matched if c not in major],
                              dict(scores))
    return RuleResult(best, "rule", scores.get(best, raw.get(best, 0)), terms.get(best, []), secondary, dict(scores))
