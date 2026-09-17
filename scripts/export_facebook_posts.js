/*
 * Export YOUR OWN Facebook posts as a writing sample for `dysrewrite learn`.
 *
 * Why: the personal profile is learned from how *you* write. Facebook posts are the
 * most natural writing most people have in one place.
 *
 * How:
 *   1. Log in to Facebook as yourself and open your activity log filtered to posts:
 *        https://www.facebook.com/me/allactivity?activity_history=false&category_key=STATUSCLUSTER
 *   2. Scroll to the bottom repeatedly (press End) until it stops loading older entries.
 *   3. Open DevTools (F12) -> Console, paste this whole file, press Enter.
 *   4. A file named my-posts.json downloads. Then:
 *        dysrewrite learn my-posts.json -o me.json
 *
 * What it keeps: status updates, photo/video captions, "feeling" posts — text you wrote.
 * What it drops: things you shared (someone else's words), Instagram cross-posts, and
 * birthday messages written on other people's walls (too short to say anything about style).
 *
 * Privacy: this runs entirely in your browser and only downloads a file to your computer.
 * Nothing is sent anywhere. Keep the file private; it is your own writing.
 */
(function () {
  const MIN_WORDS = 8;
  const DATE = /^(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}$/;
  const AUD = /^(Public|Friends|Friends of friends|Only me|Custom|Friends except.*|Specific friends|Close Friends|Shared with.*|.*'s friends.*|Your friends.*)$/;
  const TIME = /^\d{1,2}:\d{2} (AM|PM)$/;
  const SKIP_ACTION = /shared a |wrote on|Shared from Instagram/;

  const main = document.querySelector('[role="main"]') || document.body;
  const views = [...main.querySelectorAll('a[role="link"]')].filter(e => /^View$/.test(e.innerText.trim()));
  if (!views.length) { console.warn("No activity-log entries found. Are you on the activity log page?"); return; }

  // the entry = the largest ancestor that still contains exactly one "View" link
  function entryOf(v) {
    let c = v;
    for (let i = 0; i < 12; i++) {
      const p = c.parentElement; if (!p) break;
      const n = [...p.querySelectorAll('a[role="link"]')].filter(e => /^View$/.test(e.innerText.trim())).length;
      if (n > 1) return c;
      c = p;
    }
    return c;
  }

  const me = (document.querySelector('[role="main"] h1, [role="banner"] [aria-label*="profile"]')?.innerText || "").trim();
  let lastDate = "";
  const items = [];
  for (const v of views) {
    const lines = entryOf(v).innerText.split("\n").map(s => s.trim()).filter(Boolean);
    let i = 0, date = lastDate;
    if (DATE.test(lines[0])) { date = lines[0]; lastDate = date; i = 1; }
    let action = "";
    if (/^[A-Z][^\n]{1,60}? (updated|added|shared|is |was |wrote|posted|created|Shared)/.test(lines[i] || "")) { action = lines[i]; i++; }
    let end = lines.length;
    while (end > i && (lines[end - 1] === "View" || TIME.test(lines[end - 1]) || AUD.test(lines[end - 1]))) end--;
    const body = lines.slice(i, end).join("\n").trim();
    const words = body.split(/\s+/).filter(Boolean).length;
    if (!body || words < MIN_WORDS) continue;
    if (SKIP_ACTION.test(action) || /Shared from Instagram/.test(body)) continue;
    items.push({ date, action: action.replace(/^.*? (?=(updated|added|is |was |posted|created))/, ""), body, url: v.href });
  }
  const words = items.reduce((n, p) => n + p.body.split(/\s+/).filter(Boolean).length, 0);
  const payload = { exported: new Date().toISOString(), source: "facebook activity log, own posts only", posts: items.length, words, items };
  const blob = new Blob([JSON.stringify(payload, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "my-posts.json";
  document.body.appendChild(a); a.click(); a.remove();
  console.log(`Exported ${items.length} posts, ${words} words -> my-posts.json`);
})();
