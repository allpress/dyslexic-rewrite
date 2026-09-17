"""Deterministic rule-based rewriter. No model, no network, runs anywhere.

What it does, in order, per sentence:
  1. Substitute words the reader asked us to (personal), phrasal verbs, and words re-used
     with a different meaning nearby (ambiguity). Optionally rare/long words when the profile
     turns on `simplify_vocab`.
  2. Straighten the sentence when its shape is the problem: split coordinated clauses,
     peel off trailing ", which ..." clauses, and turn leading "Because X, Y" into "X. So Y."
  3. Everything else that was flagged is kept as a *note* so the reader view can show it.

Plain heteronyms on their own are never auto-replaced: the evidence says silent word swaps
do not help on average, so those are shown on demand instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..protect import Protected, is_protected
from ..triggers.base import Trigger
from .model import Change, SentenceRewrite

SUBSTITUTE_KINDS = ("personal", "phrasal", "ambiguity")
VOCAB_KINDS = ("rare", "long")
SUBSTITUTE_THRESHOLD = 0.45
SPLIT_THRESHOLD = 0.3

# Leading subordinators we can safely turn into a two-sentence form.
_LEAD_SCONJ = {
    "because": "So", "since": None, "although": "But", "though": "But", "even though": "But",
    "when": "Then", "after": "Then", "once": "Then", "while": None, "if": None, "unless": None,
    "whereas": "But",
}


@dataclass
class _Cell:
    text: str
    ws: str
    tok: object            # spaCy token or None
    change: Change | None = None
    note: Trigger | None = None
    break_before: bool = False
    drop: bool = False


def _match_case(src: str, repl: str) -> str:
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def rewrite_sentence(sent, sent_index: int, triggers: list[Trigger], profile,
                     protected: list[Protected], simplify_vocab: bool = False) -> SentenceRewrite:
    toks = list(sent)
    cells = [_Cell(t.text, t.whitespace_, t, drop=t.is_space) for t in toks]
    by_start = {t.idx: i for i, t in enumerate(toks)}

    # --- 1. substitutions ---------------------------------------------------------------
    taken: set[int] = set()
    kinds_order = list(SUBSTITUTE_KINDS) + (list(VOCAB_KINDS) if simplify_vocab else [])
    for kind in kinds_order:
        for tr in triggers:
            if tr.kind != kind or tr.start not in by_start:
                continue
            i = by_start[tr.start]
            if i in taken or not tr.alternatives:
                continue
            if tr.score * profile.weight(tr.kind) < SUBSTITUTE_THRESHOLD:
                continue
            if is_protected(tr.start, tr.end, protected):
                continue
            # a single verb with its own particle ("wind up the clock") needs the phrasal rule, not a word swap
            if kind != "phrasal" and any(c.dep_ == "prt" for c in toks[i].children):
                continue
            # find the last token covered by the trigger (phrasal verbs span several)
            j = i
            while j + 1 < len(toks) and toks[j + 1].idx < tr.end:
                j += 1
            if any(k in taken for k in range(i, j + 1)):
                continue
            repl = _match_case(tr.text, tr.alternatives[0])
            cells[i].change = Change(
                original=tr.text, replacement=repl, kind=tr.kind, reason=tr.reason,
                alternatives=tr.alternatives,
            )
            cells[i].ws = cells[j].ws
            for k in range(i + 1, j + 1):
                cells[k].drop = True
            taken.update(range(i, j + 1))

    # --- 2. notes for everything flagged but not changed --------------------------------
    for tr in triggers:
        if tr.kind == "syntax" or tr.start not in by_start:
            continue
        i = by_start[tr.start]
        if i in taken or cells[i].note is not None:
            continue
        if tr.kind in ("rare", "long") and tr.score * profile.weight(tr.kind) < 0.35:
            continue
        cells[i].note = tr

    # --- 3. sentence shape --------------------------------------------------------------
    syn = [t for t in triggers if t.kind == "syntax" and t.start == sent.start_char]
    if syn and syn[0].score * profile.weight("syntax") >= SPLIT_THRESHOLD:
        _split_leading_subordinate(sent, toks, cells)
        _split_coordinated_clauses(sent, toks, cells)
        _split_trailing_relative(sent, toks, cells)
        _split_semicolons(sent, toks, cells)
        cells = _lift_subject_relative(sent, toks, cells)

    return SentenceRewrite(index=sent_index, original=sent.text, segments=_to_segments(cells))


def _lift_subject_relative(sent, toks, cells) -> list[_Cell]:
    """'Mrs. Alvarez, who had lived here for years, said X.'
       -> 'Mrs. Alvarez had lived here for years. Mrs. Alvarez said X.'

    The clause wedged between subject and verb is the single most expensive shape for
    working memory. We lift it out into its own sentence first, then repeat the subject.
    """
    root = sent.root
    subj = next((t for t in root.children if t.dep_ in ("nsubj", "nsubjpass")), None)
    if subj is None:
        return cells
    rel = next((c for c in subj.children if c.dep_ == "relcl" and c.i < root.i), None)
    if rel is None:
        return cells
    r0 = rel.left_edge.i - sent.start
    r1 = rel.right_edge.i - sent.start
    if r0 <= 0 or toks[r0].lower_ not in ("who", "which", "that") or toks[r0 - 1].text != ",":
        return cells
    if r1 + 1 >= len(toks) or toks[r1 + 1].text != ",":
        return cells
    s0 = subj.left_edge.i - sent.start
    subj_cells = cells[s0:r0 - 1]          # the subject phrase, before the comma
    if not subj_cells or any(c.change or c.note for c in subj_cells):
        return cells                        # keep it simple: only lift plain subjects
    import copy
    lifted = [copy.copy(c) for c in subj_cells]
    lifted[-1].ws = " "
    body = [copy.copy(c) for c in cells[r0 + 1:r1 + 1]]   # clause minus the wh-word
    if not body:
        return cells
    body[0].text = body[0].text[:1].lower() + body[0].text[1:] if body[0].tok.pos_ != "PROPN" else body[0].text
    body[-1].ws = ""
    head = cells[:s0]
    rest = cells[r1 + 2:]                  # after the closing comma
    for c in (cells[r0 - 1], cells[r1 + 1]):
        c.drop = True
    subj_again = [copy.copy(c) for c in subj_cells]
    subj_again[-1].ws = " "
    subj_again[0].break_before = True
    subj_again[0].text = subj_again[0].text[:1].upper() + subj_again[0].text[1:]
    lifted[0].text = lifted[0].text[:1].upper() + lifted[0].text[1:]
    return head + lifted + body + subj_again + rest


# ----------------------------------------------------------------------------------------
# shape rules
# ----------------------------------------------------------------------------------------
def _clause_has_subject(verb) -> bool:
    return any(c.dep_ in ("nsubj", "nsubjpass", "expl") for c in verb.children)


def _split_coordinated_clauses(sent, toks, cells) -> None:
    """'X did A, and Y did B' -> 'X did A. Y did B.' when both halves have their own subject."""
    root = sent.root
    for t in toks:
        if t.dep_ == "conj" and t.head == root and t.pos_ in ("VERB", "AUX") \
                and _clause_has_subject(t) and _clause_has_subject(root):
            # the cc token that joins them sits just before the second clause's subtree
            left = t.left_edge.i - sent.start
            cc_i = None
            for k in range(left - 1, max(left - 3, -1), -1):
                if toks[k].dep_ == "cc":
                    cc_i = k
                    break
            if cc_i is None:
                continue
            cc = toks[cc_i].lower_
            # remove a comma right before the cc
            if cc_i - 1 >= 0 and toks[cc_i - 1].text == ",":
                cells[cc_i - 1].drop = True
                cells[cc_i - 2].ws = cells[cc_i - 1].ws if cc_i - 2 >= 0 else ""
            if cc in ("and",):
                cells[cc_i].drop = True
                cells[left].break_before = True
            elif cc in ("but", "yet"):
                cells[cc_i].text = "But"
                cells[cc_i].break_before = True
            elif cc == "so":
                cells[cc_i].text = "So"
                cells[cc_i].break_before = True
            elif cc == "or":
                cells[cc_i].text = "Or"
                cells[cc_i].break_before = True
            else:
                continue
            return  # one split per sentence per rule keeps things predictable


def _split_trailing_relative(sent, toks, cells) -> None:
    """'..., which V ...' at the end -> '... . It/They V ...'"""
    for t in toks:
        if t.dep_ != "relcl" or t.pos_ not in ("VERB", "AUX"):
            continue
        rel_start = t.left_edge.i - sent.start
        rel_end = t.right_edge.i - sent.start
        # must run to the end of the sentence (allowing final punctuation and trailing whitespace)
        last = max(i for i, x in enumerate(toks) if not x.is_space)
        if rel_end < last - 1:
            continue
        first = toks[rel_start]
        if first.lower_ not in ("which", "who", "that") or rel_start == 0:
            continue
        if toks[rel_start - 1].text != ",":
            continue  # restrictive clause: meaning would change
        head = t.head
        plural = head.tag_ in ("NNS", "NNPS")
        if head.ent_type_ == "PERSON" or head.pos_ == "PROPN" or first.lower_ == "who":
            pron = head.text  # repeat the name/person noun; safest for people
        else:
            pron = "They" if plural else "It"
        cells[rel_start - 1].drop = True
        cells[rel_start - 2].ws = "" if rel_start - 2 >= 0 else ""
        cells[rel_start].text = pron
        cells[rel_start].break_before = True
        return


def _split_leading_subordinate(sent, toks, cells) -> None:
    """'Because X, Y.' -> 'X. So Y.'"""
    if not toks or toks[0].pos_ != "SCONJ":
        return
    key = toks[0].lower_
    if len(toks) > 1 and f"{key} {toks[1].lower_}" in _LEAD_SCONJ:
        key = f"{key} {toks[1].lower_}"
    if key not in _LEAD_SCONJ or _LEAD_SCONJ[key] is None:
        return
    # the subordinate clause is the advcl whose left edge is token 0
    advcl = None
    for t in toks:
        if t.dep_ == "advcl" and t.left_edge.i == sent.start:
            advcl = t
            break
    if advcl is None:
        return
    end = advcl.right_edge.i - sent.start
    if end + 1 >= len(toks) or toks[end + 1].text != ",":
        return
    if end - len(key.split()) < 2:
        return  # too short to be worth it
    n_drop = len(key.split())
    for k in range(n_drop):
        cells[k].drop = True
    cells[n_drop].text = cells[n_drop].text[:1].upper() + cells[n_drop].text[1:]
    cells[end + 1].drop = True                 # the comma
    cells[end].ws = ""
    cells[end + 2].break_before = True
    cells[end + 2].text = _LEAD_SCONJ[key] + " " + cells[end + 2].text


def _split_semicolons(sent, toks, cells) -> None:
    for i, t in enumerate(toks):
        if t.text in (";",) and 0 < i < len(toks) - 1:
            cells[i].drop = True
            cells[i - 1].ws = ""
            cells[i + 1].break_before = True
            cells[i + 1].text = cells[i + 1].text[:1].upper() + cells[i + 1].text[1:]


# ----------------------------------------------------------------------------------------
def _to_segments(cells: list[_Cell]) -> list:
    segs: list = []
    buf = ""
    for c in cells:
        if c.drop:
            continue
        if c.break_before:
            if buf.rstrip():
                segs.append(("text", buf.rstrip() + ("." if not buf.rstrip().endswith(('.', '!', '?')) else "")))
                buf = ""
            elif segs and segs[-1][0] != "break":
                # ensure previous segment ends with a period
                pass
            segs.append(("break", None))
            buf = " "
        if c.change is not None:
            if buf:
                segs.append(("text", buf))
                buf = ""
            segs.append(("change", c.change))
            buf = c.ws
        elif c.note is not None:
            if buf:
                segs.append(("text", buf))
                buf = ""
            segs.append(("note", c.note))
            buf = c.ws
        else:
            buf += c.text + c.ws
    if buf:
        segs.append(("text", buf))
    return _fix_breaks(segs)


def _fix_breaks(segs: list) -> list:
    """Make sure text before a break ends in a period and text after starts capitalised."""
    out = []
    for i, (k, v) in enumerate(segs):
        if k == "break":
            # close the previous textual segment with a period
            j = len(out) - 1
            while j >= 0 and out[j][0] == "break":
                j -= 1
            if j >= 0:
                pk, pv = out[j]
                if pk == "text":
                    s = pv.rstrip()
                    if s and not s.endswith(('.', '!', '?', '"', '”')):
                        s += "."
                    out[j] = ("text", s)
                elif pk == "change":
                    pv.replacement = pv.replacement.rstrip()
                    if not pv.replacement.endswith(('.', '!', '?')):
                        out.append(("text", "."))
            out.append((k, v))
            continue
        # capitalise first letter after a break
        if out and out[-1][0] == "break":
            if k == "text":
                v = " " + v.lstrip()
                v = v[:1] + v[1:2].upper() + v[2:] if len(v) > 1 else v
            elif k == "change":
                v.replacement = v.replacement[:1].upper() + v.replacement[1:]
                out.append(("text", " "))
            elif k == "note":
                out.append(("text", " "))
        out.append((k, v))
    return out
