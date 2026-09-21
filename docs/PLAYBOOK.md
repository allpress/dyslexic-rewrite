# Launch playbook — unwindwords.com

The step-by-step I'll walk you through. Everything I could do without your accounts is done
and marked ✅. Everything else is a click you make, marked 👤, with the exact text ready in
`docs/launch/`. Nothing here posts, pays or publishes on your behalf — that is always you.

## 0. What exists now (v0.6)

Reading: paste, web-page import, sample books, rewrites with reversible changes, phonetic map,
read-aloud with word highlighting, dictionary on tap, reading settings (fonts, spacing,
themes, ruler, spotlight, auto-scroll, immersive mode), dictation into the box.
Profile: 10-minute screening → five-axis radar → settings applied; A/B reading tests;
learned writing style. Library (Pro): EPUB/TXT/MD/PDF/DOCX → dyslexia-friendly EPUB, read on
site, download, send to Kindle, AI chapter summaries, hosted-engine rewrites. Browser
extension "Unwind this page" (unpublished; loads unpacked). Billing (Stripe, free tier + Pro
$5/mo or $39/yr). Feedback widget + weekly rollup skill. SEO book pages, sitemap, newsletter,
cookie-free counters, privacy/terms/about.

Helperbird parity, honestly stated: we match its reading-side features (fonts, spacing,
ruler, focus, overlays as comfort settings, TTS with highlighting, dictionary, summarise,
simplify, PDF, reading mode, dictation, immersive mode, extension) and we do what it doesn't
(personalised rewriting, screening-driven profiles, book conversion, Kindle). We do not do its
writing-side tools (grammar checker, word prediction, speech-to-math, equation editor, sticky
notes, OCR) — those are a different product and I would not chase them.

## 1. Day 0 — switch the money and the engine on (👤 ~40 minutes)

1. 👤 **Stripe** — `server/API.md` → Billing has the seven steps. Product "Unwind Words Pro",
   prices $5/month and $39/year, webhook to `https://unwindwords.com/api/billing/webhook`,
   customer portal on. Put `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
   `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_YEARLY` in GitHub → Settings → Secrets.
2. 👤 **DeepSeek** — create an API key at platform.deepseek.com, add ~$5 of credit (that is
   fifty books). GitHub secrets: `DYSREWRITE_LLM_API_KEY`, and
   `DYSREWRITE_LLM_BASE_URL=https://api.deepseek.com/v1`, `DYSREWRITE_LLM_MODEL=deepseek-flash`.
3. 👤 **Admin + notifications** — GitHub secrets `ADMIN_KEY` (any long random string; it is
   what the rollup skill and the stats page use) and `FEEDBACK_NOTIFY_EMAIL=allpress@gmail.com`.
4. 👤 Run the **"Sync secrets"** workflow in the Actions tab. The next deploy picks them up
   (or re-run "Deploy"). Then: `dysrewrite llm-check` from a Fly console, or just convert a
   book as a Pro user and look at `cost_usd` on the book.
5. 👤 **hello@unwindwords.com** — Squarespace → Domains → Email forwarding → to your Gmail.
6. ✅ Everything the site needs is deployed; `python -m server.billing grant EMAIL --months 3`
   (Fly console) gifts Pro to testers before Stripe is live.
7. 👤 **Buy Pro yourself** on yearly with a real card, confirm the Profile page flips, then
   refund yourself in Stripe. That is the whole billing test.

## 2. Week 1 — five readers, one of them Jennifer

- 👤 Gift Pro to five people you can talk to. Ask each to: do the screening, convert one book
  they actually want to read, read a chapter with the map on, and press the Feedback button
  once with anything at all.
- ✅ The weekly rollup skill (`.claude/skills/feedback-rollup`) turns what they say into
  themes and fixes; run it with "do the feedback rollup" in Claude Code in the repo.
- 👤 Google Search Console: add the property, submit `https://unwindwords.com/sitemap.xml`.
- Gate: five converted books and one "I'd pay for this" before any public post.

## 3. Week 2 — the launch week (👤 posting; ✅ text ready)

Order matters: HN first (technical audience, links the repo), Product Hunt two days later
(needs the HN traffic for early upvotes), directories the same afternoon, Reddit as a person
on day 4, newsletter #1 on day 5 to everyone who signed up during the week.

| Day | Channel | Ready text |
|---|---|---|
| Tue 08:00 ET | Show HN | `docs/launch/show-hn.md` |
| Tue | Newsletter welcome is already automatic on signup | `docs/launch/emails.md` |
| Thu 00:01 PT | Product Hunt | `docs/launch/product-hunt.md` |
| Thu | AlternativeTo, SaaSHub, There's An AI For That, Indie Hackers product page | `docs/launch/directories.md` |
| Fri | Reddit: r/dyslexia, r/ADHD (read rules first; some ban promotion), r/SideProject, r/microsaas | `docs/launch/reddit.md` |
| Sat | Newsletter #1 | `docs/launch/emails.md` |
| following week | Outreach to Understood.org, AbilityNet, BDA tech list, IDA chapters | `docs/launch/outreach.md` |

While you post, I watch `/api/admin/stats` and `/api/admin/feedback/summary` and fix what
breaks; the rollup skill runs on Sunday.

## 4. Weeks 3–12 — the engine that costs nothing

- ✅/👤 A public-domain classic a week: `docs/launch/classics.md` lists twenty with Gutenberg
  ids in the order schools assign them. Adding one is a text file in `server/data/samples/`
  plus an index entry; the SEO page and the cache appear on deploy. I can do these; you
  approve the list.
- 👤 Short demo videos (30–60 s screen recordings, no face): scripts in
  `docs/launch/videos.md`. TikTok, YouTube Shorts, Instagram Reels, same file.
- 👤 Build in public, weekly, numbers from `/api/admin/stats`: template in
  `docs/launch/build-in-public.md`.
- ✅ Extension: `extension/README.md` has the store checklist. 👤 Chrome Web Store developer
  account ($5 one-off) and Firefox AMO (free) — submit `extension/web-ext-artifacts/*.zip`.
- 👤 Classroom plan when the first tutor asks: one more Stripe price ($3/reader/year, min 10).

## 5. Paid ads — one month, one channel, $100 (👤)

Only after the free channels have run for two weeks, so there is a baseline. Copy and
targeting in `docs/launch/ads.md`. Reddit Ads on r/dyslexia + r/ADHD interest targeting is the
first test (cheapest CPM for this audience); Google Search on "dyslexia friendly books" /
"dyslexia reading app" is the second. Measure cost per Pro subscriber against organic; stop
if it loses. At $5/month the payback on a $10 acquisition is two months — fine on yearly,
marginal on monthly, which is why every CTA nudges yearly.

## 6. What I watch, and when I tell you

Every rollup: signups, accounts, Pro, books, A/B WPM delta, battery averages, top tripped
words, the three things I fixed, drafts of replies. Immediately: any drop over 30 % week on
week, any failed conversion pattern, any Stripe webhook failure (billing_events table).

## 7. The moat, restated

Nobody else has the heteronym data or a screening that changes how the text is rewritten.
Publishing the first A/B result — even a null one — is the post that makes the project
credible to the orgs in `outreach.md`. That is the research goal in `RESEARCH.md` §3.1, and
it is also the marketing plan.
