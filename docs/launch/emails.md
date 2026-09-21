# Emails

All sent from hello@unwindwords.com via Resend (already verified for the domain). The
welcome is automatic on newsletter signup; the rest you send by hand or with a one-off
script — there is no bulk sender in the app yet, and under 1,000 contacts Resend's free tier
covers it.

## Welcome (automatic, already live — edit in server/marketing.py)

Subject: You're in — here's the free sample chapter

Thanks for signing up. Unwind Words rewrites the words that trip dyslexic readers and keeps
the original one tap away. Try a chapter right now, no account needed:
https://unwindwords.com/read?sample=wind-in-the-willows

When you have ten minutes, "Which kind of reader am I?" builds your profile:
https://unwindwords.com/assess

I read every reply. — Doug

## Newsletter #1 — launch week

Subject: Unwind Words is live (and what the research actually says)

Short: what it does in three lines; the before/after image; the three things to try (sample
chapter, screening, convert one book free); one honest paragraph on evidence (frequency and
length substitution: yes; sentence simplification: likely; fonts and overlays: no); the price
and the promise (reading tools free forever, engine open source); a reply-to-this-email ask
for one sentence of feedback.

## Newsletter — weekly classic

Subject: This week's dyslexia-friendly classic: <Title>

One paragraph on the book, the link to `/books/<slug>`, one tip from the rollup (a reader
setting people liked, a tripped word we fixed), and the numbers line if you're building in
public. Under 200 words.

## Pro thank-you (send by hand when the Stripe email arrives)

Subject: Thank you — and one question

You're one of the first people paying for Unwind Words, which means you're paying the
hosting bill for everyone reading for free. Thank you.

One question: what's the first book you want to convert? If it's public domain, tell me and
I'll make it a free page for everyone.

## Reply templates for the rollup

- Fixed: "Thanks for telling me about <thing>. It's fixed as of <date> — <one line on what
  changed>. If it's still wrong for you, reply to this and I'll look again."
- Planned: "Thanks — <thing> is on the list for <rough timing>. I'll email you when it ships."
- Not doing: "Thanks for the idea. I'm not going to do <thing> because <one honest reason>,
  but <alternative> might get you most of the way there."
