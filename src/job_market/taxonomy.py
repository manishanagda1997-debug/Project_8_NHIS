"""The job-function taxonomy (decision D-026; definitions in docs/labelling_guide.md).

Categories describe the work the freelancer does, not the client's industry.
The order here is display order only; it is not a priority order.
"""

from __future__ import annotations

TAXONOMY_VERSION = "1.0"
OTHER = "other_unclear"

# id -> (display name, one-line definition)
CATEGORIES: dict[str, tuple[str, str]] = {
    "web_development": ("Web Development", "build or fix websites and web apps (WordPress, Shopify setup, landing pages, full stack)"),
    "mobile_development": ("Mobile Development", "build or fix phone/tablet apps (iOS, Android, Flutter, React Native)"),
    "software_it": ("Software & IT", "non-web programming, scripts, automation, scraping, APIs, games, blockchain, DevOps, IT support"),
    "ai_ml": ("AI & Machine Learning", "AI is the core of the work: chatbots, LLM/GPT apps, ML models, computer vision"),
    "data_analytics": ("Data & Analytics", "analyse and present data: Excel models, Power BI, dashboards, statistics"),
    "design_creative": ("Design & Creative", "static visuals: logos, branding, UI/UX mock-ups, illustration, thumbnails, 3D renders"),
    "video_animation": ("Video & Animation", "moving images: video editing, filming, animation, motion graphics, UGC video creation"),
    "photography": ("Photography", "photo shoots and photo editing/retouching"),
    "writing_content": ("Writing & Content", "original text: articles, copywriting, scripts, ghostwriting, proofreading"),
    "translation_transcription": ("Translation & Transcription", "translation, localisation, transcription, subtitles"),
    "digital_marketing": ("Digital Marketing", "SEO, social media management, paid ads, email marketing, UGC/influencer campaigns"),
    "sales_lead_generation": ("Sales & Lead Generation", "lead generation, appointment setting, cold calling/email, closing, B2B sales"),
    "admin_virtual_assistance": ("Admin & Virtual Assistance", "virtual/executive assistant, data entry, typing, manual research"),
    "customer_service": ("Customer Service", "support for a client's customers by chat, email or phone"),
    "accounting_finance": ("Accounting & Finance", "bookkeeping, tax, payroll calculation, financial statements and models, billing"),
    "legal": ("Legal", "contracts, trademarks, company registration, visas, compliance"),
    "engineering_architecture": ("Engineering & Architecture", "CAD, mechanical/electrical/civil engineering, PCB, architecture, interior design"),
    "audio_music": ("Audio & Music", "voice-over, narration, podcast editing, music, mixing"),
    "ecommerce_operations": ("E-commerce Operations", "run online stores: Amazon/Etsy/eBay listings, product upload, product research"),
    "business_project_management": ("Business, Project Management & Consulting", "project/operations management, consulting, business plans, sourcing"),
    "education_tutoring": ("Education & Tutoring", "tutoring, teaching, course creation, training programmes"),
    "hr_recruiting": ("HR & Recruiting", "recruiting, headhunting, HR policies and processes"),
    OTHER: ("Other / Unclear", "the title does not say what the work is, or the work is outside all 22 categories"),
}

CATEGORY_IDS = tuple(CATEGORIES)
