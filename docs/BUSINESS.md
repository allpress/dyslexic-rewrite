# Unwind Words as a micro-SaaS

Written September 2026. The engine stays MIT and free; the website keeps a free tier that
does everything a single reader needs for a page at a time. "Pro" sells convenience —
whole books, a library, Kindle delivery, the better engine — and pays the hosting bill.
That is the open-core shape most successful tiny SaaS products use, and it keeps the
promise the project started with: the tool that helps someone read is free.

## 1. What is built (as of this document)

| Layer | Free | Pro ($5 / month or $39 / year, founding price) |
|---|---|---|
| Paste & read with rewrites, phonetic map, read-aloud | up to 20,000 characters | up to 200,000 |
| Sample books (Gutenberg classics) | yes | yes |
| "Which kind of reader am I?" screening, A/B reading tests, personal profile | yes | yes |
| Book conversion (EPUB / TXT / MD → dyslexia-friendly EPUB) | **one book, ever** (≤ 60k words) | unlimited (≤ 300k words each) |
| Library, read on the site, download EPUB, send to Kindle | for that one book | yes |
| Re-run a book after the profile changes | — | yes |
| Higher-quality engine (hosted LLM behind the fidelity gate) | — | when the server has a model configured |
| Open-source CLI (`pip install dyslexic-rewrite`) | everything, forever | — |

Infrastructure already in the repo: Stripe Checkout + Billing Portal + webhooks
(`server/billing.py`), plan gating and quotas, `/pricing`, account section on the
profile page, background book worker with a rewrite cache (`server/library.py`),
server-rendered SEO pages for each sample book (`/books/<slug>`), sitemap and robots,
newsletter capture with unsubscribe, cookie-free page counters, `/api/admin/stats`,
privacy / terms / about pages. `python -m server.billing grant EMAIL --months 3` gifts
Pro to a tester without Stripe.

## 2. The budget

Zero-marketing baseline (prices checked 2026-09-21, see RESEARCH-style caveat: they drift):

| Item | Monthly |
|---|---|
| Fly.io machine, shared-cpu-1x, 1 GB (already running) | $5.70 |
| Fly Postgres (small, unmanaged, already provisioned) | ~$2–5 |
| Fly volume (audio + books), 3 GB | $0.45 |
| Domain (unwindwords.com, ~$15/yr) | $1.25 |
| Resend (transactional + 1,000 marketing contacts) | $0 on the free tier (100 emails/day) |
| Stripe | $0 fixed; 2.9 % + $0.30 per charge |
| Analytics | $0 (our own cookie-free counters + Google Search Console) |
| Newsletter | $0 (stored in our DB; send via Resend) |
| Hosted LLM for Pro conversions | ~$0.10 per book (DeepSeek `deepseek-flash`, cached) — only when a Pro user converts |
| **Total** | **≈ $10–13 / month** |

Break-even at that baseline is **three Pro subscribers**. With a $100/month test-ads
budget the total is ≈ $115 and break-even is ~25 monthly or ~4 yearly subscribers.
Stripe takes $0.45 of a $5 charge and $1.43 of a $39 charge, so yearly is worth pushing.

What not to buy yet: Plausible ($9), Buttondown after 100 subscribers ($9), Fly
scaling, a second region, any SaaS boilerplate. Nothing in the plan needs them before
~200 paying subscribers.

## 3. Positioning and what we can honestly say

Nobody else does personalised word-level rewriting for dyslexic readers. The closest
things are Rewordify (free, generic synonym swapping, not dyslexia-specific, no
personalisation), Helperbird's "AI simplify" (a bolt-on, $35/yr, not personalised) and
the appearance tools — Bionic Reading ($2–10/mo, bolds word fragments), BeeLine
($2–5/mo, colour gradients), Speechify ($139/yr, text-to-speech only). Our price sits
inside the $2–10/month band this audience already pays, and undercuts Helperbird Pro.

Claims we make: rewrites trigger words and straightens sentences; every change is
reversible; phonetic respellings; read-aloud; a 10-minute screening that gives a profile,
not a diagnosis; open source; your books never leave your library. Claims we never make:
"cures", "dyslexia font", "coloured overlays help", any number we have not measured,
any testimonial we did not receive in writing. The research doc (§1.7, §2) is the line.

One legal note worth a lawyer's five minutes later: Bionic Reading patents and trademarks
its bolding technique aggressively; we do not bold fragments and should not add that.

## 4. Path to subscribers

Sequence, not a menu. Each step has a number that says whether to move on.

**Week 1–2: make Pro purchasable and the free path irresistible.**
1. Create the Stripe products (steps are in `server/API.md`, Billing), put the four
   secrets in GitHub, run "Sync secrets", deploy. Test with a real card on yearly, then
   refund yourself.
2. Set up hello@unwindwords.com forwarding at Squarespace (free).
3. Gift Pro to five readers you can talk to (`grant EMAIL --months 3`), including
   Jennifer. Watch them use the library. Fix what they trip on before anyone pays.
4. Submit the sitemap to Google Search Console; the `/books/<slug>` pages are the
   SEO seed ("read The Wind in the Willows, dyslexia-friendly").
   Gate to move on: five people have converted a book and one says they'd pay.

**Week 3–4: the launch, in the order that compounds.**
5. Show HN: "Unwind Words – open-source tool that rewrites books for dyslexic readers".
   HN likes open source with a real story; link the repo, lead with Jennifer's trigger
   words and the heteronym probe (nobody has that data). Have the email capture ready.
6. Product Hunt the same week (credibility and a backlink, not traffic).
7. Directories, one afternoon: AlternativeTo (alternative to Speechify / Bionic
   Reading / Helperbird), SaaSHub, There's An AI For That, AbilityNet's tools list,
   Understood.org's free-assistive-tech article (pitch the author; it is a real page
   that gets updated), the IDA state chapters' assistive-technology pages, BDA's
   technology resources.
8. Reddit, carefully. r/dyslexia (~39k) and r/ADHD are support communities that often
   ban promotion; read the rules, then post as a person: "I built this for my wife, it's
   free and open source, here's what her reading looked like before and after" — with
   the sample-book link, not the pricing page. r/microsaas, r/SideProject and
   r/indiehackers want numbers: post the launch retrospective with real figures.
   Gate: 500 signups on the newsletter or 100 accounts, whichever first.

**Month 2–3: the content engine that costs nothing.**
9. Add a public-domain classic every week as a `/books/<slug>` page (the cache makes it
   free; each is a long-tail search page and a newsletter issue). Target the books
   schools assign: Frankenstein, Pride and Prejudice, Huck Finn, Sherlock, Jekyll and
   Hyde, The Call of the Wild.
10. Short demo videos (30–60 s, screen recording, no face needed) for TikTok / Shorts:
    "why *wind* stops a dyslexic reader cold", "watch a paragraph get unwound".
    Dyslexia TikTok is large and under-served by tools that do anything real.
11. Build in public, weekly: MRR, signups, what the A/B tests show. The heteronym
    finding, whichever way it goes, is a post people will share.
12. Tutors and SENCOs: a "Pro for classrooms" price ($3/reader/year, minimum 10) is a
    single Stripe price away and is how Helperbird makes most of its money. Add it when
    the first tutor asks.

**Only then: paid ads.** $100/month on one channel (Reddit ads on r/dyslexia and r/ADHD,
or Google on "dyslexia friendly books") for one month, measured against the free
channels' cost per subscriber. Stop if it loses to organic; it usually does at this size.

## 5. Numbers to watch (all in `/api/admin/stats?key=…`)

- Visitors → accounts (target 5 %); accounts → first book converted (target 40 %);
  first book → Pro (target 10 %). At 1,000 visitors/month that is 2 new Pro/month —
  which is why the free tier gives exactly one book: it is the conversion moment.
- Yearly share of Pro (target > 50 %; nudge with the price copy).
- Churn: readers who convert one book and leave. Kindle delivery and the weekly classic
  are the retention levers.
- The research metric: WPM gain on the A/B test by profile axis. Publishing that is the
  moat; nobody else can.

## 6. Three-month goal

30 Pro subscribers (~$150 MRR, covers hosting ten times over and funds the DeepSeek tier
for every conversion), 1,000 newsletter readers, 20 classics as SEO pages, one published
result from the heteronym probe. If it gets there, the next decisions are the classroom
plan and a browser extension. If it does not, the free tool still exists and still
helps, which was the point.
