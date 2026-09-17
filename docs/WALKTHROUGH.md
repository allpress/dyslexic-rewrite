# Going live — the human steps (same shape as Chowder)

Everything below is a one-time account action only you can do. Everything else is in the repo.

1. **GitHub repo.** Create `allpress/dyslexic-rewrite` (public — it's open source). Push `main` from
   `~/Documents/dyslexic-rewrite`:
   `git remote add origin git@github.com:allpress/dyslexic-rewrite.git && git push -u origin main`
   Or hand Claude a fine-grained token with *Contents: read/write*, *Actions: read/write*, *Secrets: read/write*,
   *Workflows: read/write* on that repo and it will push and run the workflows.
2. **Repo secrets** (Settings → Secrets and variables → Actions):
   - `FLY_API_TOKEN` — from `fly tokens create deploy -x 999999h` (or a personal token).
   - `RESEND_API_KEY` — your existing Resend account; make a new key named `dyslexic-rewrite`.
   - Variable `LOGIN_FROM_EMAIL` — `login@<your domain>` once the domain is verified in Resend; until then
     leave unset and sign-in emails come from `login@example.com`, which Resend will reject — so for the very
     first deploy without a domain, leave `RESEND_API_KEY` unset too and the code shows on screen.
3. **Provision** — Actions tab → *Provision (one-time)* → Run. Creates the Fly app `dyslexic-rewrite`,
   Postgres `dyslexic-rewrite-db` (attached as `DATABASE_URL`), and sets `SESSION_SECRET`.
4. **Deploy** — happens on every push to `main` (or Actions → *Deploy* → Run). First deploy takes ~5 min
   (spaCy model download). Check `https://dyslexic-rewrite.fly.dev/api/health`.
5. **Domain** — buy it (Squarespace Domains works as before), then:
   - `fly certs add <domain>` and `fly certs add www.<domain>` (Actions → *Ops* → `certs add <domain>`),
   - DNS: apex A/AAAA → the Fly app's IPs (`fly ips list`), `www` CNAME → `dyslexic-rewrite.fly.dev`,
   - Resend → Domains → add the domain → copy its DKIM/SPF records into DNS → set `LOGIN_FROM_EMAIL`,
     re-run *Provision* to push the secrets.
6. **Rename the wordmark** — `web/src/components/Nav.tsx`, `web/index.html` `<title>`, `fly.toml` `APP_NAME`.
