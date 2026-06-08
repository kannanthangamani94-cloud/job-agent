# Job Agent -- Setup Guide
# Kannan's daily pharma/institute career page monitor

## What this does
Every weekday morning at 8 AM, this agent:
1. Visits career pages of 15+ pharma companies and research institutes
2. Finds jobs posted since yesterday
3. Filters by keywords (immunology, neuroscience, imaging, etc.)
4. Asks Claude AI if each job matches your profile
5. Emails you only the strong matches (score 6+/10)

## SETUP (one time, takes ~20 minutes)

---

### Part 1: Get your tools ready

1. Create a free account at https://github.com  
   (Think of GitHub as Google Drive, but for code)

2. Create a new repository (like a folder):
   - Click the green "New" button
   - Name it: job-agent
   - Set it to "Private" (your profile info stays private)
   - Click "Create repository"

3. Upload the files:
   - Upload job_agent.py to the root of the repository
   - Create folder: .github/workflows/
   - Upload daily.yml into that folder

---

### Part 2: Set up Gmail to send emails

Gmail requires an "App Password" (not your regular password) 
for automated scripts. Think of it like a valet key -- 
it only works for this one purpose.

1. Go to your Google Account > Security
2. Turn on 2-Step Verification if not already on
3. Search for "App Passwords" in the search bar
4. Create a new App Password -- name it "job-agent"
5. Copy the 16-character password it gives you (e.g., abcd efgh ijkl mnop)
   Remove spaces: abcdefghijklmnop
   SAVE THIS -- you only see it once

---

### Part 3: Add your secret keys to GitHub

These are stored in GitHub's secure vault -- like a locked 
drawer that only your script can open.

1. In your GitHub repository, click "Settings"
2. Left sidebar: "Secrets and variables" > "Actions"
3. Click "New repository secret" and add these four:

   Name: ANTHROPIC_API_KEY
   Value: sk-ant-... (from console.anthropic.com > API Keys)

   Name: SENDER_EMAIL
   Value: your.gmail@gmail.com

   Name: SENDER_PASSWORD
   Value: abcdefghijklmnop (the 16-char app password from Part 2)

   Name: RECIPIENT_EMAIL
   Value: the email where you want job alerts (can be same Gmail)

---

### Part 4: Test it manually

1. In your GitHub repository, click the "Actions" tab
2. Click "Daily Job Agent" in the left sidebar
3. Click "Run workflow" > "Run workflow" (green button)
4. Watch it run -- click on the run to see live logs
5. Check your email within 2-3 minutes

---

### Part 5: Add more companies (optional)

Open job_agent.py and look for the GREENHOUSE_COMPANIES 
and LEVER_COMPANIES dictionaries.

To find a company's API slug:
- Greenhouse: visit https://boards.greenhouse.io/TRYCOMPANYNAME
  If it loads, that's the slug. Example: boards.greenhouse.io/broadinstitute
- Lever: visit https://jobs.lever.co/TRYCOMPANYNAME
  If it loads, that's the slug. Example: jobs.lever.co/astrazeneca

Example companies to add:
  Greenhouse: "calico", "denali", "alector", "23andme", "insitro"
  Lever: "recursion", "flagship-pioneering"

---

## COSTS

- GitHub Actions: FREE (2,000 minutes/month free, you'll use ~3 min/day)
- Anthropic API: ~$0.01-0.05 per day (very cheap, Claude Sonnet is fast)
- Gmail: FREE

Total: basically free.

---

## CUSTOMIZATION

Edit MY_PROFILE in job_agent.py to update your profile summary.
Edit KEYWORDS to add/remove search terms.
Change the cron schedule (0 12 * * 1-5) to adjust timing:
  - "0 12 * * *" = every day including weekends
  - "0 8 * * 1-5" = 8 AM UTC (3 AM ET) weekdays -- adjust hour as needed

---

## TROUBLESHOOTING

If no email arrives after running:
1. Check the Actions log for errors (red X means something failed)
2. Verify all 4 secrets are set correctly in Settings > Secrets
3. Check your spam folder
4. Run locally to test: 
   export ANTHROPIC_API_KEY="sk-ant-..."
   export SENDER_EMAIL="you@gmail.com"
   ... etc
   python job_agent.py
