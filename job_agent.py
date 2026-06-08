"""
Job Agent for Kannan -- v2 (Pharma + Universities + Research Institutes)
------------------------------------------------------------------------
Think of this script like a research assistant who:
  1. Visits pharma AND university/institute career pages every morning
  2. Writes down every job posting it finds
  3. Compares to yesterday's list -> flags ONLY new ones
  4. Asks Claude: "Does this match Kannan's profile?"
  5. Emails you only the strong matches

NEW IN v2:
  - RSS feeds: Nature Careers + Science Careers (AAAS)
    (These are like academic job aggregators -- one feed covers
    hundreds of universities and institutes at once)
  - USAJobs API: NIH, NCI, NIMH, NINDS, NIDA, NIAAA
  - More Greenhouse institutes: CZI, Fred Hutch, Jackson Lab, Wistar,
    Buck Institute, Allen Institute, Rockefeller
  - HigherEdJobs RSS feed (university postdoc listings)

HOW TO RUN LOCALLY:
  pip install requests anthropic feedparser
  Set env vars (see README), then: python job_agent.py

HOW IT RUNS AUTOMATICALLY:
  GitHub Actions runs this every weekday at 8 AM ET (see .github/workflows/daily.yml)
"""

import requests
import json
import os
import smtplib
import datetime
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import anthropic
import feedparser   # NEW: reads RSS feeds like a structured news ticker

# ============================================================
# YOUR PROFILE SUMMARY
# Claude reads this to decide if a job is worth emailing you
# ============================================================
MY_PROFILE = """
Kannan Thangamani, Ph.D. | Postdoctoral Research Associate, Northeastern University, Boston, MA
12+ years research experience. Contract ends September 2026, actively seeking next role.
VISA: F-1 OPT (work authorized, no sponsorship needed for OPT period), pursuing O-1A.

EDUCATION:
- PhD Neuroscience, University of Texas at San Antonio (2017-2023)
- B.Tech Biotechnology, SRM Institute of Science and Technology, Chennai (2012-2016)
- Consulting Workshop (10 weeks), Enventure, 2025: case interviews, market sizing, M&A, profitability

AWARDS: Dean's Postdoctoral Research Award (2025), Best Poster x2 (2022, 2023), DBT-JRF Fellow (2016-17), INSA-IAS Summer Research Fellowship (2013)

CORE RESEARCH EXPERTISE:
- Neuroimmunology: stress-driven neutrophil activation, NET (neutrophil extracellular trap) formation, stress-immune-behavior axis
- Innate immunity: neutrophil biology, host-pathogen interaction (Coxiella burnetii), cytokine profiling, innate immune signaling
- iPSC disease modeling: hiPSC-derived cortical neurons, dopamine neurons (VTA), Alzheimer's model (PSEN1/PSEN2), addiction model
- Behavioral neuroscience: CUS models, sucrose preference, anxiety assays
- Human subjects research: IRB-approved study design, 30+ donors, consent management

WET LAB TECHNIQUES (hands-on, proficient):
- Flow cytometry (multi-color, ImageStream), ELISA, western blot, immunofluorescence
- Confocal microscopy (Zeiss LSM 710/880), live cell imaging, CellProfiler, ImageJ
- Patch clamp electrophysiology, stem cell culture, neuronal differentiation protocols
- Statistical analysis: R, Python, GraphPad Prism

COMPUTATIONAL (self-taught, supporting skill only -- NOT a primary expertise):
- scRNA-seq data analysis (self-taught; can interpret and run pipelines but NOT a dedicated bioinformatician)
- NOT suitable for roles where scRNA-seq is the primary job function (e.g. 10x Genomics, dedicated computational roles)

PUBLICATIONS:
1. First-author: Psychoneuroendocrinology (2026) — stress hormones, neutrophils, NET formation, behavioral consequences
2. Co-author: Nature Communications (2019) — VTA astrocytes orchestrate avoidance/approach behavior
3. Co-author: Toxicology in Vitro (2025) — estrogen effects on T-cell leukemia
4. Co-author: Archives of Rheumatology (2020) — sex-based differences in RA cytokine signaling
5. Co-author: Journal of Neuroimmunology (2020) — neuroendocrine-immune aging
6. In submission: Coxiella burnetii delays apoptosis in primary human neutrophils

LEADERSHIP & OPERATIONS:
- Built research lab from scratch: 20+ workflows, $25K budget, scaled 0→6 researchers in 8 months
- Managed and trained 6 direct reports; enabled 2 master's thesis completions
- GLP/GDP compliance, SOP development, procurement

LOOKING FOR (in order of preference):
1. Postdoctoral positions: neuroimmunology, stress biology, innate immunity, neuroinflammation
2. Scientist I/II: immunology, neuroimmunology, inflammation at pharma/biotech
3. Field Application Scientist / Applications Scientist: confocal/multiphoton microscopy, flow cytometry, imaging platforms (Zeiss, Leica, Nikon, BD, Akoya, 10x)
4. Life science strategy consulting (entry/junior): health care, biopharma, market access, competitive intelligence
5. Medical Science Liaison (MSL): immunology, neuroscience therapeutic areas
6. Computational biology / imaging scientist roles

TARGET INSTITUTIONS (postdoc):
  Harvard, MIT, Stanford, UCSF, Johns Hopkins, Rockefeller, Salk, Buck Institute,
  Jackson Lab, Fred Hutchinson, Allen Institute, Wistar, Cold Spring Harbor,
  NIH intramural, Scripps, Moffitt, MD Anderson, Mayo Clinic, NYU, Columbia,
  Yale, Duke, Vanderbilt, UT Southwestern, Broad Institute

TARGET COMPANIES (industry/consulting):
  Genentech, AstraZeneca, J&J, Novartis, Pfizer, AbbVie, BMS, Regeneron, Biogen, Moderna,
  Zeiss, Leica Microsystems, Nikon, BD Biosciences, Akoya Biosciences, 10x Genomics,
  Putnam Associates, L.E.K. Consulting, IQVIA, ZS Associates, Analysis Group, Evidera,
  Charles River Associates, Inovalon, Guidehouse
"""

# ============================================================
# SOURCE 1: GREENHOUSE COMPANIES
# Pharma + research institutes that use Greenhouse job boards
# ============================================================
GREENHOUSE_COMPANIES = {
    # -- VERIFIED RESEARCH INSTITUTES --
    "chanzuckerberginitiative": "Chan Zuckerberg Initiative",
    "czimaginginstitute":       "CZ Imaging Institute",
    "biohub":                   "CZ Biohub (SF/Chicago/NY)",

    # -- VERIFIED BIOTECH/PHARMA --
    "nilotherapeutics":         "Nilo Therapeutics (neuro+immunology)",
    "xairatherapeutics":        "Xaira Therapeutics",
    "recursionpharmaceuticals": "Recursion Pharmaceuticals",
    "inceptive":                "Inceptive",
    "parsebiosciences":         "Parse Biosciences",
    "akoyabio":                 "Akoya Biosciences",
    "vertex":                   "Vertex Pharmaceuticals",
    "illumina":                 "Illumina",
    "precisionbiosciences":     "Precision BioSciences",
    "tenaxtherapeutics":        "Tenax Therapeutics",
    "kymera":                   "Kymera Therapeutics",
    "imago-biosciences":        "Imago BioSciences",
    "springbioscience":         "Spring Bioscience",
}

# ============================================================
# SOURCE 2: LEVER COMPANIES
# ============================================================
LEVER_COMPANIES = {
    "flagship-pioneering":   "Flagship Pioneering",
    "cytovale":              "CytoVale",
    "immunovant":            "Immunovant",
    "45drives":              "45 Drives",
}

# ============================================================
# SOURCE 3: RSS FEEDS (NEW)
#
# RSS is like a news feed but for job postings.
# Think of it like a PubMed alert -- instead of new papers,
# it sends you new job listings.
# 
# Nature Careers and Science Careers each aggregate postings
# from hundreds of universities and institutes worldwide.
# One RSS URL = hundreds of institutions covered. Very efficient.
# ============================================================
RSS_FEEDS = {
    # Nature Careers -- filtered to your keywords
    # You can customize the search by editing the URL
    "nature_immunology":   (
        "https://www.nature.com/naturecareers/jobs.rss"
        "?subject=immunology&field=postdoc",
        "Nature Careers (Immunology)"
    ),
    "nature_neuroscience": (
        "https://www.nature.com/naturecareers/jobs.rss"
        "?subject=neuroscience&field=postdoc",
        "Nature Careers (Neuroscience)"
    ),

    # Science Careers (AAAS) -- covers US universities extensively
    "science_postdoc": (
        "https://jobs.sciencecareers.org/jobs/rss/?k=postdoc+immunology",
        "Science Careers (AAAS)"
    ),
    "science_neuro": (
        "https://jobs.sciencecareers.org/jobs/rss/?k=postdoc+neuroscience",
        "Science Careers (AAAS)"
    ),

    # HigherEdJobs -- university HR listings, postdoc category
    "highered_postdoc": (
        "https://www.higheredjobs.com/rss/jobFeed.cfm?type=2&JobCat=21",
        "HigherEdJobs (Postdoc)"
    ),

    # New Scientist Jobs (UK + international)
    "newscientist": (
        "https://jobs.newscientist.com/jobs/rss/?k=immunology+neuroscience",
        "New Scientist Jobs"
    ),

    # jobRxiv -- academic preprint community job board, heavy on postdocs
    "jobrxiv_postdoc": (
        "https://jobrxiv.org/job-category/postdoc/feed/",
        "jobRxiv (Postdoc)"
    ),

    # Science Careers extra searches
    "science_innate": (
        "https://jobs.sciencecareers.org/jobs/rss/?k=innate+immunity+postdoc",
        "Science Careers (AAAS)"
    ),
    "science_neuroimmuno": (
        "https://jobs.sciencecareers.org/jobs/rss/?k=neuroimmunology",
        "Science Careers (AAAS)"
    ),

    # Nature Careers extra
    "nature_inflammation": (
        "https://www.nature.com/naturecareers/jobs.rss?subject=inflammation&field=postdoc",
        "Nature Careers (Inflammation)"
    ),
}

# ============================================================
# SOURCE 4: USAJOBS API (NEW) -- for NIH and federal positions
#
# USAJobs is the official US federal government job site.
# All NIH labs (NCI, NIMH, NINDS, NIDA, etc.) post here.
# They have a free, official API -- very reliable.
#
# You need a free API key from: https://developer.usajobs.gov/APIRequest/Index
# Add it as USAJOBS_API_KEY in your GitHub secrets.
# ============================================================
USAJOBS_API_KEY  = os.environ.get("USAJOBS_API_KEY", "")
USAJOBS_EMAIL    = os.environ.get("USAJOBS_EMAIL", "")  # the email you register with

USAJOBS_SEARCHES = [
    ("immunologist postdoc",           ""),
    ("neuroscience postdoc NIH",       "Bethesda, Maryland"),
    ("neuroimmunology",                ""),
    ("postdoctoral fellow immunology", ""),
    ("research biologist neuroscience",""),
    ("microbiologist immunology",      ""),
]

# ============================================================
# SOURCE 5: WORKDAY COMPANIES
# Large pharma/biotech that use Workday (not Greenhouse/Lever)
# API format: POST /wday/cxs/{tenant}/{board}/jobs with JSON body
# ============================================================
WORKDAY_COMPANIES = {
    # (tenant, board, display_name)
    "modernatx":  ("modernatx",  "M_tx",     "Moderna"),
    "regeneron":  ("regeneron",  "Careers",  "Regeneron"),
    "biogen":     ("biibhr",     "external", "Biogen"),
    "abbvie":     ("abbvie",     "global",   "AbbVie"),
    "novartis":   ("novartis",   "novartis_careers", "Novartis"),
}

WORKDAY_KEYWORDS = [
    "immunology", "neuroimmunology", "neuroscience", "postdoctoral",
    "postdoc", "innate immunity", "inflammation", "neutrophil",
    "scientist", "field application", "imaging",
]

# ============================================================
# KEYWORDS -- pre-filter before Claude scoring
# ============================================================
KEYWORDS = [
    # Core science
    "immunology", "neuroimmunology", "neuroscience", "neuroinflammation",
    "innate immunity", "neutrophil", "inflammation", "cytokine",
    "iPSC", "stem cell", "single cell", "scRNA",
    "flow cytometry", "confocal", "microscopy", "imaging",
    "microglia", "astrocyte", "T cell", "myeloid", "lymphocyte",
    "brain", "neuro", "immune", "stress", "behavioral",
    "host pathogen", "NET", "extracellular trap",
    # Job titles - academic
    "postdoc", "post-doc", "postdoctoral", "fellow", "research associate",
    # Job titles - industry science
    "scientist", "research scientist", "biologist", "immunologist",
    "computational biology", "bioinformatics",
    # Job titles - imaging/instruments
    "field application scientist", "applications scientist",
    "application specialist", "field scientist", "imaging specialist",
    "microscopy specialist", "flow cytometry specialist",
    # Job titles - consulting
    "consulting", "consultant", "life science strategy", "scientific consultant",
    "medical science liaison", "MSL", "market access", "health economics",
    "competitive intelligence", "business analyst", "life science",
    # Companies/platforms
    "Zeiss", "Leica", "Nikon", "Akoya", "spatial biology", "spatial genomics",
    "CODEX", "multiphoton", "lightsheet", "CellProfiler",
]

# ============================================================
# SETTINGS
# ============================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SENDER_EMAIL      = os.environ.get("SENDER_EMAIL", "")
SENDER_PASSWORD   = os.environ.get("SENDER_PASSWORD", "")
RECIPIENT_EMAIL   = os.environ.get("RECIPIENT_EMAIL", "")
SEEN_JOBS_FILE    = "seen_jobs.json"

# ============================================================
# MEMORY FUNCTIONS
# ============================================================
def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_jobs(seen_ids):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen_ids), f)

def make_id(prefix, text):
    """
    Create a stable unique ID by hashing text.
    This is like creating a fingerprint for a job posting --
    even if the URL changes slightly, the same job gets the 
    same ID so we don't email you duplicates.
    """
    return prefix + "_" + hashlib.md5(text.encode()).hexdigest()[:16]

# ============================================================
# FETCH: GREENHOUSE
# ============================================================
def fetch_greenhouse_jobs(slug, company_name):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        jobs = []
        for job in r.json().get("jobs", []):
            jobs.append({
                "id":       f"greenhouse_{slug}_{job['id']}",
                "title":    job.get("title", ""),
                "company":  company_name,
                "location": job.get("location", {}).get("name", ""),
                "url":      job.get("absolute_url", ""),
                "source":   "Greenhouse",
                "type":     "pharma/institute"
            })
        print(f"  {company_name}: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"  ERROR {company_name}: {e}")
        return []

# ============================================================
# FETCH: LEVER
# ============================================================
def fetch_lever_jobs(slug, company_name):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        jobs = []
        for job in r.json():
            jobs.append({
                "id":       f"lever_{slug}_{job['id']}",
                "title":    job.get("text", ""),
                "company":  company_name,
                "location": job.get("categories", {}).get("location", ""),
                "url":      job.get("hostedUrl", ""),
                "source":   "Lever",
                "type":     "pharma/institute"
            })
        print(f"  {company_name}: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"  ERROR {company_name}: {e}")
        return []

# ============================================================
# FETCH: RSS FEEDS (NEW)
#
# feedparser reads an RSS feed like a list of headlines.
# Each "entry" in the feed is one job posting.
# We pull out the title, link, and a snippet of the description.
# ============================================================
def fetch_rss_jobs(feed_key, feed_url, feed_name):
    try:
        feed = feedparser.parse(feed_url)
        jobs = []
        for entry in feed.entries:
            title   = entry.get("title", "")
            link    = entry.get("link", "")
            summary = entry.get("summary", "")[:300]  # first 300 chars of description

            # Extract organization from title if possible
            # Many RSS entries format as "Job Title - Institution"
            parts   = title.split(" - ")
            org     = parts[-1].strip() if len(parts) > 1 else feed_name

            jobs.append({
                "id":          make_id(f"rss_{feed_key}", title + link),
                "title":       parts[0].strip() if len(parts) > 1 else title,
                "company":     org,
                "location":    "",            # RSS often doesn't include location
                "url":         link,
                "source":      feed_name,
                "type":        "university/institute",
                "description": summary        # extra context for Claude
            })
        print(f"  {feed_name}: {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"  ERROR {feed_name}: {e}")
        return []

# ============================================================
# FETCH: USAJOBS (NEW)
#
# The US federal government has a proper API for job listings.
# Think of it as a PubMed API but for government jobs.
# NIH's intramural program posts hundreds of postdoc positions here.
# ============================================================
def fetch_usajobs(keyword, location=""):
    if not USAJOBS_API_KEY or not USAJOBS_EMAIL:
        return []
    
    headers = {
        "Host":            "data.usajobs.gov",
        "User-Agent":      USAJOBS_EMAIL,
        "Authorization-Key": USAJOBS_API_KEY
    }
    params = {
        "Keyword":         keyword,
        "ResultsPerPage":  25,
        "WhoMayApply":     "All"  # includes non-citizens
    }
    if location:
        params["LocationName"] = location

    try:
        r = requests.get(
            "https://data.usajobs.gov/api/search",
            headers=headers, params=params, timeout=15
        )
        r.raise_for_status()
        data = r.json()
        jobs = []
        for item in data.get("SearchResult", {}).get("SearchResultItems", []):
            pos = item.get("MatchedObjectDescriptor", {})
            title    = pos.get("PositionTitle", "")
            org      = pos.get("OrganizationName", "NIH")
            loc_list = pos.get("PositionLocation", [{}])
            loc      = loc_list[0].get("LocationName", "") if loc_list else ""
            url      = pos.get("PositionURI", "")
            job_id   = pos.get("PositionID", "")

            jobs.append({
                "id":       f"usajobs_{job_id}",
                "title":    title,
                "company":  org,
                "location": loc,
                "url":      url,
                "source":   "USAJobs (Federal/NIH)",
                "type":     "university/institute"
            })
        print(f"  USAJobs '{keyword}': {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"  ERROR USAJobs '{keyword}': {e}")
        return []

# ============================================================
# FETCH: WORKDAY
# Workday exposes a semi-public JSON API used by their career pages.
# POST to /wday/cxs/{tenant}/{board}/jobs with a search keyword.
# ============================================================
def fetch_workday_jobs(company_key, tenant, board, company_name):
    url = f"https://{tenant}.wd1.myworkdayjobs.com/wday/cxs/{tenant}/{board}/jobs"
    all_jobs = []
    for kw in WORKDAY_KEYWORDS[:4]:  # limit to 4 keywords to avoid rate limits
        try:
            r = requests.post(
                url,
                json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": kw},
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            if r.status_code != 200:
                continue
            for item in r.json().get("jobPostings", []):
                title    = item.get("title", "")
                ext_path = item.get("externalPath", "")
                loc_list = item.get("locationsText", "")
                job_url  = f"https://{tenant}.wd1.myworkdayjobs.com{ext_path}" if ext_path else ""
                job_id   = make_id(f"workday_{company_key}", title + ext_path)
                all_jobs.append({
                    "id":       job_id,
                    "title":    title,
                    "company":  company_name,
                    "location": loc_list,
                    "url":      job_url,
                    "source":   "Workday",
                    "type":     "pharma/biotech"
                })
        except Exception as e:
            print(f"  ERROR Workday {company_name} ({kw}): {e}")
            break
    # deduplicate by id
    seen = set()
    unique = []
    for j in all_jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)
    print(f"  {company_name} (Workday): {len(unique)} jobs")
    return unique

# ============================================================
# KEYWORD PRE-FILTER
# Checks title AND description snippet for RSS jobs
# ============================================================
def passes_keyword_filter(job):
    text = (
        job.get("title", "") + " " +
        job.get("location", "") + " " +
        job.get("description", "")
    ).lower()
    return any(kw.lower() in text for kw in KEYWORDS)

# ============================================================
# CLAUDE SCORING
# ============================================================
def claude_match(job, client):
    description_hint = ""
    if job.get("description"):
        description_hint = f"Description snippet: {job['description']}"

    prompt = f"""
You are a career advisor helping a postdoctoral neuroimmunologist evaluate job fit.

CANDIDATE PROFILE:
{MY_PROFILE}

JOB POSTING:
Title:    {job['title']}
Company:  {job['company']}
Location: {job['location'] or 'Not specified'}
Source:   {job['source']}
Type:     {job.get('type', '')}
URL:      {job['url']}
{description_hint}

Rate how well this job matches the candidate.
Respond ONLY with a JSON object like this (no extra text):
{{
  "score": 8,
  "fit_summary": "Strong postdoc match: neuroimmunology focus, well-funded lab",
  "apply": true,
  "job_type": "postdoc"
}}

Rules:
- score is 1-10 (10 = perfect fit)
- apply is true if score >= 4
- fit_summary is 1 sentence max
- job_type is one of: "postdoc", "scientist", "consulting", "other"
"""
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"    Claude error for {job['title']}: {e}")
        return {"score": 0, "fit_summary": "Error", "apply": False, "job_type": "other"}

# ============================================================
# EMAIL
# Now groups results by job type (postdoc vs scientist vs other)
# ============================================================
def send_email(matched_jobs):
    if not matched_jobs:
        print("No new matches today -- no email sent.")
        return

    today = datetime.date.today().strftime("%B %d, %Y")

    # Group by job type
    postdocs   = [j for j in matched_jobs if j.get("job_type") == "postdoc"]
    scientists = [j for j in matched_jobs if j.get("job_type") == "scientist"]
    others     = [j for j in matched_jobs if j.get("job_type") not in ("postdoc", "scientist")]

    subject = (
        f"Job Agent: {len(matched_jobs)} match(es) "
        f"[{len(postdocs)} postdoc | {len(scientists)} scientist] -- {today}"
    )

    def section(title, jobs):
        if not jobs:
            return []
        lines = [f"\n{'='*60}", f"  {title} ({len(jobs)} positions)", f"{'='*60}\n"]
        for job in sorted(jobs, key=lambda x: -x.get("score", 0)):
            lines += [
                f"SCORE:    {job.get('score', '?')}/10",
                f"ROLE:     {job['title']}",
                f"WHERE:    {job['company']}",
                f"LOCATION: {job['location'] or 'Not specified'}",
                f"SOURCE:   {job['source']}",
                f"WHY:      {job.get('fit_summary', '')}",
                f"LINK:     {job['url']}",
                "",
                "-" * 60,
                ""
            ]
        return lines

    body_lines = [
        f"Good morning! Your job agent found {len(matched_jobs)} new relevant posting(s) today.",
        f"Contract ends Sept 2026 -- {(datetime.date(2026,9,30) - datetime.date.today()).days} days from now.",
        ""
    ]
    body_lines += section("POSTDOCTORAL POSITIONS", postdocs)
    body_lines += section("SCIENTIST / INDUSTRY ROLES", scientists)
    body_lines += section("OTHER MATCHES", others)

    msg = MIMEMultipart()
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText("\n".join(body_lines), "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print(f"Email sent! {len(matched_jobs)} matches.")
    except Exception as e:
        print(f"Email error: {e}")

# ============================================================
# MAIN
# ============================================================
def main():
    print(f"\n{'='*60}")
    print(f"Job Agent v2 -- {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    seen_ids = load_seen_jobs()
    print(f"Memory: {len(seen_ids)} jobs seen in past runs.\n")

    all_jobs = []

    # -- Greenhouse --
    print("GREENHOUSE (pharma + institutes):")
    for slug, name in GREENHOUSE_COMPANIES.items():
        all_jobs.extend(fetch_greenhouse_jobs(slug, name))

    # -- Lever --
    print("\nLEVER (pharma + biotech):")
    for slug, name in LEVER_COMPANIES.items():
        all_jobs.extend(fetch_lever_jobs(slug, name))

    # -- RSS Feeds (universities + academic boards) --
    print("\nRSS FEEDS (academic job boards):")
    for key, (url, name) in RSS_FEEDS.items():
        all_jobs.extend(fetch_rss_jobs(key, url, name))

    # -- USAJobs (NIH, federal) --
    if USAJOBS_API_KEY:
        print("\nUSAJOBS (NIH + federal institutes):")
        for keyword, location in USAJOBS_SEARCHES:
            all_jobs.extend(fetch_usajobs(keyword, location))
    else:
        print("\nUSAJOBS: Skipped (no API key set)")

    # -- Workday (large pharma: Moderna, Regeneron, Biogen, AbbVie, Novartis) --
    print("\nWORKDAY (large pharma):")
    for key, (tenant, board, name) in WORKDAY_COMPANIES.items():
        all_jobs.extend(fetch_workday_jobs(key, tenant, board, name))

    print(f"\nTotal jobs fetched across all sources: {len(all_jobs)}")

    # -- Filter new only --
    new_jobs = [j for j in all_jobs if j["id"] not in seen_ids]
    print(f"New (not seen before): {len(new_jobs)}")

    # -- Keyword pre-filter --
    keyword_filtered = [j for j in new_jobs if passes_keyword_filter(j)]
    print(f"After keyword filter: {len(keyword_filtered)}")

    # -- Claude scoring --
    matched_jobs = []
    if keyword_filtered and ANTHROPIC_API_KEY:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        print(f"\nClaude scoring {len(keyword_filtered)} jobs...")
        for job in keyword_filtered:
            result = claude_match(job, client)
            tag = result.get("job_type", "?")
            print(f"  [{result['score']}/10][{tag}] {job['title']} @ {job['company']}")
            if result.get("apply"):
                job["score"]      = result["score"]
                job["fit_summary"] = result["fit_summary"]
                job["job_type"]   = result.get("job_type", "other")
                matched_jobs.append(job)
    else:
        print("Skipping Claude scoring (no API key or no filtered jobs)")
        matched_jobs = [{**j, "score": "?", "fit_summary": "No Claude scoring", "job_type": "other"}
                        for j in keyword_filtered]

    print(f"\nStrong matches to email: {len(matched_jobs)}")

    # -- Update memory --
    for job in new_jobs:
        seen_ids.add(job["id"])
    save_seen_jobs(seen_ids)

    # -- Send email --
    send_email(matched_jobs)

    print("\nDone!\n")

if __name__ == "__main__":
    main()
