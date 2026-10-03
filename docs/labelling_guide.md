# Job-category labelling guide

**Version:** taxonomy 1.0 (frozen 3 October 2026; any change creates version 1.1 and requires a fresh blind test sample)
**Used for:** the 150-title development set and the 350-title blind test set
(Notebook 03). The same definitions drive the keyword rules, so a human label
and a rule label always mean the same thing.

---

## 1. The one question to ask

> **What work will the freelancer actually do?**

Label the **job function** (the work), not the client's industry, the
platform, or who is hiring.

- "Real Estate **Virtual Assistant**" → Admin & Virtual Assistance (the work is VA work; real estate is the client's industry)
- "**Hiring** a WordPress developer" → Web Development (the role being hired, not "HR")
- "**AI** video editor" → Video & Animation (AI is a tool; the output is video)

## 2. How to label

1. Read **only the title**. Do not look at pay, country, date, or the job link.
2. Choose **exactly one** category (section 3).
3. If two categories fit, apply the **tie-break rules** (section 4).
4. If the title does not say what the work is, choose **Other / Unclear**
   (section 5). Do not guess from one vague word.
5. Tick **unsure** whenever you hesitate between two categories, even if you
   picked one. Unsure ticks are not mistakes; they show where the taxonomy is
   hard.
6. Non-English titles: label them if you understand the work (translate in
   your head or with a translator); otherwise Other / Unclear.
7. Label in one or two sittings and re-read this guide before each sitting.
8. **Blind test only:** you see the title only, never a predicted category.
   Do not change any label after you finish, and do not discuss individual
   titles with anyone who builds the rules.

## 3. The 22 categories

Each entry: **what it covers**, typical titles, and **what it does not cover**
(with where those titles go instead).

### 1. `web_development` — Web Development
Building, fixing or changing websites and web apps: WordPress, Shopify themes
and store setup, Webflow, Wix, landing pages, front end, back end of a web
app, full stack.
- *Examples:* "WordPress website fix", "Shopify theme customization", "Landing page in Webflow", "Full stack developer (React + Node)", "Bubble.io web app"
- *Not:* mobile apps → Mobile; scripts/automation/APIs without a website → Software & IT; pure visual mock-ups in Figma → Design.

### 2. `mobile_development` — Mobile Development
Building or fixing apps for phones and tablets: iOS, Android, Flutter, React
Native, Swift, Kotlin, app-store publishing.
- *Examples:* "Flutter developer for delivery app", "iPhone application problem", "React Native app bug fixes", "Publish app to Google Play"
- *Not:* app UI design only → Design; app marketing/ASO → Digital Marketing.

### 3. `software_it` — Software & IT
Programming that is not a website or mobile app, plus IT operations: Python or
Java programs, scripts, automation (Zapier, Make), web scraping, APIs and
integrations, browser extensions, desktop software, games, blockchain and
smart contracts, DevOps, cloud, servers, databases, cybersecurity, IT support.
- *Examples:* "Python script to automate reports", "Web scraper for real estate listings", "Zapier integration with HubSpot", "Unity game developer", "AWS server setup", "Create an ERC-20 token"
- *Not:* AI/LLM/chatbot/ML as the core → AI & ML; dashboards/analysis → Data & Analytics.

### 4. `ai_ml` — AI & Machine Learning
Work whose core is artificial intelligence: chatbots, LLM/GPT apps, AI agents,
machine-learning models, computer vision, NLP, model training or fine-tuning,
prompt engineering.
- *Examples:* "AI chatbot for customer support", "Fine-tune an LLM", "Computer vision model for defect detection", "GenAI development", "Prompt engineer"
- *Not:* AI used as a tool to make other output ("AI video", "AI-written blog", "AI art") → category of the output (Video, Writing, Design).

### 5. `data_analytics` — Data & Analytics
Analysing data and presenting it: data analysis, data science (statistics,
non-AI modelling), Excel/Google Sheets formulas and models, Power BI, Tableau,
Looker, dashboards, SQL queries for reporting, survey analysis.
- *Examples:* "Power BI dashboard", "Excel formulas for inventory", "Data analyst for sales data", "Statistical analysis for research"
- *Not:* typing or collecting data → Admin; financial statements/models → Accounting & Finance; ML model building → AI & ML; scraping → Software & IT.

### 6. `design_creative` — Design & Creative
Static visual design: graphic design, logos, branding, UI/UX and Figma
mock-ups, illustration, social-media post graphics, thumbnails, banners,
flyers, packaging, book covers, presentations/slides design, 3D modelling and
rendering (non-engineering), t-shirt and merch design.
- *Examples:* "Logo design for bakery", "UI/UX designer for SaaS dashboard (Figma)", "YouTube thumbnail designer", "Brand book for my company", "3D product render", "Pitch deck design"
- *Not:* moving images → Video & Animation; photo shoots/retouching → Photography; CAD/technical drawings/interior design → Engineering & Architecture.

### 7. `video_animation` — Video & Animation
Moving images: video editing, YouTube/TikTok/Reels editing, short-form
content editing, animation (2D/3D), motion graphics, explainer videos,
videography (filming).
- *Examples:* "Video editor for YouTube channel", "Motion graphics for ad", "2D explainer animation", "Simple unboxing videos", "Videographer for event", "UGC video creator for skincare brand"
- *Not:* writing the script → Writing; voice-over → Audio & Music; managing the channel's strategy/growth → Digital Marketing.

### 8. `photography` — Photography
Taking photos and editing photos: photo shoots (product, event, portrait,
real estate), photo retouching, background removal, photo editing.
- *Examples:* "Product photographer", "Wedding proposal photographer", "Retouch 50 product photos", "Edit photo"
- *Not:* turning photos into illustrations/cartoons → Design; filming video → Video.

### 9. `writing_content` — Writing & Content
Writing original text: articles, blogs, copywriting, website copy, scripts
(YouTube, ads, video), ghostwriting, books and e-books, proofreading and
editing text, technical writing, resumes, grant writing, academic writing.
- *Examples:* "SEO blog writer", "YouTube scriptwriter", "Ghostwriter for memoir", "Proofread my thesis", "Sales page copywriter"
- *Not:* translating existing text → Translation; SEO strategy/audits → Digital Marketing; course design → Education.

### 10. `translation_transcription` — Translation & Transcription
Converting language or speech to text: translation, localisation,
transcription, subtitles/captions, interpretation.
- *Examples:* "English to Spanish translation", "Transcribe 3 hours of audio", "Arabic subtitles for videos", "Localise app into German"
- *Not:* voice recording in a language → Audio & Music; writing new content in a language → Writing.

### 11. `digital_marketing` — Digital Marketing
Promoting a business online: SEO, social-media management and strategy,
paid ads (Google, Facebook/Meta, TikTok, Amazon ads), PPC, email marketing,
influencer and UGC campaigns (strategy, finding and managing creators), content strategy, growth marketing, ASO,
tracking/analytics setup for marketing (GA4, pixels).
- *Examples:* "Social media manager", "Google Ads specialist", "SEO audit", "Klaviyo email flows", "UGC campaign manager", "GA4 tracking issue"
- *Not:* finding/contacting leads, appointment setting, closing deals → Sales; designing the post graphics → Design; editing the ad video → Video.

### 12. `sales_lead_generation` — Sales & Lead Generation
Finding customers and selling directly: lead generation, lead lists,
appointment setting, cold calling, cold email outreach, telemarketing, sales
closing, business development, B2B sales.
- *Examples:* "Real estate appointment setters", "B2B lead generation", "Cold caller for solar company", "High-ticket closer", "Help me find customers in Eastern Europe"
- *Not:* running ads or email newsletters → Digital Marketing; supporting existing customers → Customer Service.

### 13. `admin_virtual_assistance` — Admin & Virtual Assistance
General office and assistant work: virtual assistant, executive/personal
assistant, data entry, copy-paste, typing, online research, list building by
hand, email and calendar management, CRM updating, document formatting.
- *Examples:* "Virtual assistant for e-commerce store", "Data entry from PDFs to Excel", "Type handwritten pages", "Executive assistant", "Real estate virtual assistance"
- *Not:* customer-facing support → Customer Service; managing projects or operations → Business & PM; bookkeeping → Accounting.

### 14. `customer_service` — Customer Service
Helping a client's customers: customer support by chat, email or phone,
help desk, call-centre agent, customer success, chat moderation.
- *Examples:* "Customer support agent (chat)", "Inbound call centre representative", "Zendesk support specialist", "Chat support for subscriber questions"
- *Not:* outbound selling → Sales; internal admin tasks → Admin.

### 15. `accounting_finance` — Accounting & Finance
Money records and analysis: bookkeeping, accounting, QuickBooks/Xero,
payroll, tax returns, financial statements, financial models, valuation,
CFO services, medical or other billing, invoicing.
- *Examples:* "Bookkeeper for start-up", "Cleaning up the books", "Financial model for pitch deck", "US tax return", "Medical biller"
- *Not:* business plans and strategy → Business & PM; Excel dashboards not about finance → Data.

### 16. `legal` — Legal
Legal work: legal advice, contracts, terms and privacy policies, trademarks
and patents, company registration and legal formalities, visas and
immigration paperwork, compliance (GDPR and similar), bankruptcy.
- *Examples:* "Contract review", "Trademark registration", "Company registration in Tunisia", "E2 visa help", "GDPR compliance review"
- *Not:* writing a general blog about law → Writing.

### 17. `engineering_architecture` — Engineering & Architecture
Physical-world engineering and building design: CAD (AutoCAD, SolidWorks,
Revit), mechanical, electrical and civil engineering, PCB and electronics,
Arduino/embedded hardware, product engineering and prototyping, architecture,
floor plans, interior design.
- *Examples:* "AutoCAD floor plan", "PCB design for sensor", "SolidWorks part model", "Interior design for living room", "Structural engineer stamp"
- *Not:* 3D renders for marketing → Design; embedded *software only* → Software & IT.

### 18. `audio_music` — Audio & Music
Sound work: voice-over and narration, podcast editing and production, music
composition, singing, mixing and mastering, sound design, audiobook
narration.
- *Examples:* "Female voice-over for ad", "English and Zulu narration", "Podcast editor", "Compose music for game"
- *Not:* transcribing audio to text → Translation & Transcription.

### 19. `ecommerce_operations` — E-commerce Operations
Running online stores and marketplaces (not building the website):
Amazon/Etsy/eBay/Walmart store management, product listing and upload,
product research, dropshipping operations, inventory, Amazon FBA operations.
- *Examples:* "Amazon product listing optimisation", "Etsy store manager", "Upload 200 products to Shopify", "Product research for dropshipping"
- *Not:* Shopify theme/setup → Web; Amazon PPC/ads → Digital Marketing; store customer emails → Customer Service.

### 20. `business_project_management` — Business, Project Management & Consulting
Running and improving a business: project management, product management,
operations management, business consulting and strategy, business plans,
business and competitor research reports (rules T31-T33), coaching, sourcing and procurement agents, process
improvement.
- *Examples:* "Project manager for website launch", "Business plan for café", "Operations manager", "Sourcing agent in China", "Business consultant for start-up"
- *Not:* financial models → Accounting & Finance; recruiting → HR; executive assistant → Admin.

### 21. `education_tutoring` — Education & Tutoring
Teaching and learning: tutoring, language teaching, online course creation,
curriculum and lesson design, training programmes, exam preparation, coaching
a skill (music lessons, sports).
- *Examples:* "Math tutor for high school", "Piano teacher", "Create an online course on Excel", "Leadership training programme"
- *Not:* writing an essay or thesis for someone → Writing; corporate business coaching → Business & PM.

### 22. `hr_recruiting` — HR & Recruiting
Human-resources work done for the client: recruiting and headhunting,
sourcing candidates, HR policies and handbooks, HR administration of payroll
and employee processes (calculating payroll is Accounting, rule T34),
talent acquisition.
- *Examples:* "Recruiter for tech roles", "Headhunter for sales managers", "HR consultant for employee handbook"
- *Not:* a title that simply says "Hiring …" for another role → the role's category ("Hiring video editor" → Video).

### `other_unclear` — Other / Unclear
See section 5.

## 4. Tie-break rules (when two categories fit)

Apply the **first rule that matches**. Each rule names the pair it settles.

| # | When the title has… | …choose | Not |
|---|---|---|---|
| T1 | iOS, Android, mobile app, Flutter, React Native, Swift, Kotlin | Mobile | Web, Software |
| T2 | AI, LLM, GPT, chatbot, machine learning, computer vision as the **core of the work** | AI & ML | Software, Data, Web |
| T3 | AI only as a **tool** for another output ("AI video", "AI art", "AI-written") | category of the output | AI & ML |
| T4 | website, web app, WordPress, Shopify theme/setup, landing page, front end, full stack | Web | Software, Design |
| T5 | UI/UX, Figma, mock-up, wireframe **without** building/coding | Design | Web, Mobile |
| T6 | script, automation, scraper, API, integration, extension, game, smart contract (no website) | Software & IT | Web |
| T7 | analysis, dashboard, Excel/Sheets formulas, Power BI, statistics | Data & Analytics | Admin |
| T8 | data entry, copy-paste, typing, manual research, list building | Admin | Data |
| T9 | script **writing** for video/YouTube/ads | Writing | Video |
| T10 | voice-over or narration, even "for video" | Audio & Music | Video |
| T11 | thumbnail, static social post graphics, banner | Design | Video, Marketing |
| T12 | editing or filming video for ads/social | Video | Marketing |
| T13 | manage social media / run ads / SEO / email campaigns | Digital Marketing | Design, Writing, Sales |
| T14 | lead generation, appointment setting, cold calling/email, closing | Sales | Marketing |
| T15 | Amazon/Etsy/eBay listing, store management, product upload | E-commerce Operations | Web, Admin |
| T16 | Amazon ads / PPC | Digital Marketing | E-commerce |
| T17 | customer-facing support (chat, phone, email to customers) | Customer Service | Admin, Sales |
| T18 | project manager, operations manager, consultant, business plan | Business & PM | Admin |
| T19 | bookkeeping, tax, financial statements/models, billing | Accounting & Finance | Business, Data |
| T20 | CAD, technical drawings, interior design, architecture, PCB | Engineering & Architecture | Design |
| T21 | photo shoot, photo retouching/editing | Photography | Design |
| T22 | translation, transcription, subtitles | Translation & Transcription | Writing |
| T23 | tutoring, teaching, course creation | Education & Tutoring | Writing |
| T24 | contracts, trademark, legal formalities, visas, compliance | Legal | Business, Admin |
| T25 | "Hiring X" / "Looking for X" | category of X | HR |
| T26 | UGC: **creating/filming** the video asset | Video & Animation | Digital Marketing |
| T27 | UGC: strategy, finding or managing creators, campaigns | Digital Marketing | Video |
| T28 | "chatter": answering customer questions | Customer Service | Sales, Other |
| T29 | "chatter": selling, upselling, converting subscribers | Sales | Customer Service |
| T30 | "chatter" with no clue about the task | Other / Unclear | — |
| T31 | market research: collecting/analysing data statistically | Data & Analytics | Business, Admin |
| T32 | market research: business/competitor research, strategic report | Business & PM | Data, Admin |
| T33 | market research: manual internet research, list building | Admin | Data, Business |
| T34 | payroll: calculating/processing, payroll accounting | Accounting & Finance | HR |
| T35 | payroll: HR administration, employee processes | HR & Recruiting | Accounting |
| T36 | "content creator" with video/reels/filming stated | Video & Animation | Marketing |
| T37 | "content creator" with writing/blog/copy stated | Writing & Content | Marketing |
| T38 | "content creator" with campaign/social strategy stated | Digital Marketing | Video, Writing |
| T39 | "content creator" with no format stated | Other / Unclear | — |

**Tie-break rules vs two deliverables.** The rules above apply when *one
piece of work* could belong to two categories ("Webflow developer/designer" is
one job → Web). A title that names **two separate pieces of work** of
different functions is handled differently:

- if the title gives one of them priority, label that one
  ("Build a website and make a small logo" → Web);
- if they look **equally important** ("Logo and website", "Data entry and
  image editing"), choose **Other / Unclear**, tick **unsure**, and write both
  categories in the note. Do not invent a winner: picking the "more technical"
  one would systematically inflate technical categories in the demand counts.
  The pipeline stores both as secondary matches.

Check before freezing: if more than 5% of the development titles end up in
Other / Unclear through this rule, the rule is reviewed.

## 5. When to choose Other / Unclear

Choose **Other / Unclear** when:
- the title does not say what the work is: "Easy job", "Testing time",
  "Need help", "Facebook", "Grap", "Transfer ownership";
- the work is outside all 22 categories: mystery shopping, product testing
  for pay, physical errands, modelling for photos, adult-content work whose
  function is not one of the 22 (when the function is clear, label the
  function: an adult-site video editor is Video, a subscriber-sales chatter is
  Sales);
- the title is in a language you cannot understand.

Do **not** choose Other just because a title is short. "Logo", "SEO",
"Bookkeeping" are short but clear.

## 6. Industry tags (not labelled by hand)

Industry describes the **client's sector**, not the work. It is stored
separately as `industry_tag` (a job can have several, or none) and never
changes demand shares. It is assigned by keyword rules and spot-checked, not
labelled in the development or blind sets.

| Tag | Examples of title words |
|---|---|
| `real_estate` | real estate, realtor, property, rental, Airbnb, mortgage |
| `healthcare` | medical, health, clinic, dental, therapy, pharma, fitness |
| `education` | school, university, students, e-learning |
| `ecommerce` | e-commerce, online store, Shopify, Amazon, Etsy, dropshipping |
| `crypto_web3` | crypto, blockchain, NFT, Web3, token, DeFi |
| `finance` | fintech, trading, forex, insurance, banking, loans |
| `legal` | law firm, attorney, legal practice |

## 7. Label file format

Each labelling file is a spreadsheet with these columns:

| Column | Filled by | Meaning |
|---|---|---|
| `sample_id` | pipeline | stable ID of the row in the sample |
| `title` | pipeline | the job title exactly as cleaned (`title_clean`) |
| `category` | **you** | one category ID from section 3 (dropdown) |
| `unsure` | **you** | tick if you hesitated |
| `note` | **you** (optional) | short reason for hard cases |

The development and blind files never share a title key (`title_key`), so
the same job wording cannot appear in both.
