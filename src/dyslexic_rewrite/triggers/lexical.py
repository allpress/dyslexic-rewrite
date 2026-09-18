"""Word-level detectors: heteronyms, phrasal verbs, re-used ambiguous words, personal triggers,
rare words, long words.

The "ambiguity" detector is the heart of Doug's hypothesis: the same spelling showing up
nearby with a different job ("wind up the clock" ... "the wind blows") makes the reader's
brain reload the word mid-sentence. We flag the *second* occurrence (and later ones) and
point back at the first.
"""

from __future__ import annotations

from ..nlp import is_content, load_data, zipf
from .base import Trigger


def _heteronym_table() -> dict:
    return load_data("heteronyms.json")


def _alts_for(word: str, pos: str) -> list[str]:
    entry = _heteronym_table()["words"].get(word.lower())
    if not entry:
        return []
    return list(entry.get(pos, []))


def _hint_for(word: str, pos: str) -> str:
    entry = _heteronym_table()["words"].get(word.lower())
    if not entry:
        return ""
    return entry.get("_hint", {}).get(pos, "")


def _sent_index_of(doc):
    """Map token index -> sentence index."""
    idx = {}
    for si, sent in enumerate(doc.sents):
        for t in sent:
            idx[t.i] = si
    return idx


# ---------------------------------------------------------------------------------------
# heteronym: one spelling, more than one pronunciation/meaning
# ---------------------------------------------------------------------------------------
def detect_heteronyms(doc, profile) -> list[Trigger]:
    table = _heteronym_table()["words"]
    safe = {w.lower() for w in profile.safe_words}
    sidx = _sent_index_of(doc)
    out = []
    for tok in doc:
        lw = tok.lower_
        if lw in safe or lw not in table:
            continue
        # Only flag when the word is used in a sense that HAS a different-sounding twin.
        # A noun "wind" in a text that never uses the verb still costs a decode, so we flag
        # at low score and let ambiguity/phonetic detectors raise it.
        entry = table[lw]
        pos = "VERB" if tok.pos_ == "AUX" else tok.pos_
        if pos not in entry:
            continue
        alts = _alts_for(lw, pos)
        hint = _hint_for(lw, pos)
        out.append(Trigger(
            kind="heteronym", sent_index=sidx.get(tok.i, 0),
            start=tok.idx, end=tok.idx + len(tok.text), text=tok.text,
            reason=f"'{tok.text}' has more than one pronunciation/meaning (used here as {pos.lower()})",
            score=0.4, alternatives=alts, pos=pos, tag=tok.tag_, hint=hint,
        ))
    return out


# ---------------------------------------------------------------------------------------
# phrasal: "wind up", "put up with" — the literal parts mislead
# ---------------------------------------------------------------------------------------
def detect_phrasal(doc, profile) -> list[Trigger]:
    table = _heteronym_table()["phrasal_verbs"]
    safe = {w.lower() for w in profile.safe_words}
    sidx = _sent_index_of(doc)
    out = []
    toks = list(doc)
    n = len(toks)
    for i, tok in enumerate(toks):
        if tok.pos_ not in ("VERB", "AUX"):
            continue
        # try 3-word then 2-word particles
        for width in (3, 2):
            if i + width > n:
                continue
            window = toks[i:i + width]
            if any(t.is_punct for t in window):
                continue
            key = " ".join([tok.lemma_.lower()] + [t.lower_ for t in window[1:]])
            if key in table and key not in safe:
                # require the particle to depend on the verb (prt/prep/advmod) to avoid "wind up the hill" false hits
                if not any(t.head == tok and t.dep_ in ("prt", "prep", "advmod") for t in window[1:]):
                    continue
                entry = table[key]
                has_object = any(c.dep_ in ("dobj", "obj") for c in tok.children)
                wants = entry.get("object", "any")
                if (wants == "no" and has_object) or (wants == "yes" and not has_object):
                    continue  # literal use ("wind up the clock"), not the idiom
                alts = entry["alts"]
                # keep the verb's inflection for the first alternative when it is a single verb
                alts_infl = [_inflect_like(a, tok) for a in alts]
                out.append(Trigger(
                    kind="phrasal", sent_index=sidx.get(tok.i, 0),
                    start=tok.idx, end=window[-1].idx + len(window[-1].text),
                    text=doc.text[tok.idx: window[-1].idx + len(window[-1].text)],
                    reason=f"phrasal verb '{key}' — its parts do not mean what the whole means",
                    score=0.6, alternatives=alts_infl, pos="VERB",
                ))
                break
    return out


def _inflect_like(phrase: str, verb_tok) -> str:
    """Best-effort: match tense/person of a replacement's first word to the original verb."""
    words = phrase.split()
    head, rest = words[0], words[1:]
    tag = verb_tok.tag_
    if tag == "VBD" or tag == "VBN":
        head = _past(head)
    elif tag == "VBZ":
        head = _third_person(head)
    elif tag == "VBG":
        head = _ing(head)
    return " ".join([head] + rest)


_IRREGULAR_PAST = {"go": "went", "come": "came", "take": "took", "give": "gave", "make": "made",
                   "hold": "held", "run": "ran", "find": "found", "see": "saw", "get": "got",
                   "put": "put", "bring": "brought", "think": "thought", "show": "showed",
                   "stand": "stood", "mean": "meant", "leave": "left", "lose": "lost",
                   "end": "ended", "finish": "finished", "set": "set", "quit": "quit"}


def _past(w: str) -> str:
    if w in _IRREGULAR_PAST:
        return _IRREGULAR_PAST[w]
    if w.endswith("e"):
        return w + "d"
    if w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
        return w[:-1] + "ied"
    return w + "ed"


def _third_person(w: str) -> str:
    if w.endswith(("s", "sh", "ch", "x", "z")):
        return w + "es"
    if w.endswith("y") and w[-2] not in "aeiou":
        return w[:-1] + "ies"
    return w + "s"


def _ing(w: str) -> str:
    if w.endswith("ie"):
        return w[:-2] + "ying"
    if w.endswith("e") and w not in ("be", "see", "flee"):
        return w[:-1] + "ing"
    return w + "ing"


# ---------------------------------------------------------------------------------------
# ambiguity: same spelling, different job, close together
# ---------------------------------------------------------------------------------------
def detect_ambiguity(doc, profile) -> list[Trigger]:
    window = max(0, int(profile.ambiguity_window_sentences))
    safe = {w.lower() for w in profile.safe_words}
    sidx = _sent_index_of(doc)
    seen: dict[str, list] = {}   # lower text -> [(tok, sent_index, sense_key)]
    out = []
    for tok in doc:
        if not tok.is_alpha or len(tok.text) < 3:
            continue
        if tok.is_stop and tok.pos_ not in ("VERB", "NOUN", "ADJ"):
            continue
        if tok.pos_ in ("PUNCT", "SPACE", "X", "SYM", "NUM", "DET", "PRON", "PART", "CCONJ", "SCONJ", "ADP", "INTJ"):
            continue
        lw = tok.lower_
        if lw in safe:
            continue
        # "sense" approximated by coarse POS + lemma; wind/VERB/wind vs wind/NOUN/wind differ
        pos = {"AUX": "VERB", "PROPN": "NOUN"}.get(tok.pos_, tok.pos_)
        sense = (pos, tok.lemma_.lower())
        si = sidx.get(tok.i, 0)
        prior = seen.setdefault(lw, [])
        clash = None
        for (ptok, psi, psense) in reversed(prior):
            if si - psi > window:
                break
            if psense[0] != sense[0]:
                clash = (ptok, psense)
                break
        if clash is not None:
            ptok, psense = clash
            psi = sidx.get(ptok.i, 0)
            alts = _alts_for(lw, sense[0])
            reason = (f"'{tok.text}' is a {sense[0].lower()} here but a {psense[0].lower()} "
                      f"{si - psi} sentence(s) earlier — same spelling, different meaning")
            if alts or not _alts_for(lw, psense[0]):
                # defuse the later occurrence (or just flag it when nothing safe is known)
                out.append(Trigger(
                    kind="ambiguity", sent_index=si,
                    start=tok.idx, end=tok.idx + len(tok.text), text=tok.text, reason=reason,
                    score=0.8, alternatives=alts, related=[(ptok.idx, ptok.idx + len(ptok.text))],
                    pos=sense[0], tag=tok.tag_, hint=_hint_for(lw, sense[0]),
                ))
            else:
                # the later use has no safe swap, but the earlier one does: defuse that one instead
                out.append(Trigger(
                    kind="ambiguity", sent_index=psi,
                    start=ptok.idx, end=ptok.idx + len(ptok.text), text=ptok.text,
                    reason=(f"'{ptok.text}' is a {psense[0].lower()} here but a {sense[0].lower()} "
                            f"{si - psi} sentence(s) later — same spelling, different meaning"),
                    score=0.8, alternatives=_alts_for(lw, psense[0]),
                    related=[(tok.idx, tok.idx + len(tok.text))], pos=psense[0], tag=ptok.tag_,
                    hint=_hint_for(lw, psense[0]),
                ))
        prior.append((tok, si, sense))
    return out


# ---------------------------------------------------------------------------------------
# personal: words this reader told us trip them, plus their chosen replacements
# ---------------------------------------------------------------------------------------
def detect_personal(doc, profile) -> list[Trigger]:
    trig = {w.lower() for w in profile.trigger_words}
    repl = {k.lower(): v for k, v in profile.replacements.items()}
    if not trig and not repl:
        return []
    sidx = _sent_index_of(doc)
    out = []
    for tok in doc:
        lw = tok.lower_
        lemma = tok.lemma_.lower()
        hit = lw in trig or lemma in trig or lw in repl or lemma in repl
        if not hit:
            continue
        alts = []
        if lw in repl:
            alts.append(repl[lw])
        elif lemma in repl:
            alts.append(repl[lemma])
        alts += [a for a in _alts_for(lw, tok.pos_) if a not in alts]
        out.append(Trigger(
            kind="personal", sent_index=sidx.get(tok.i, 0),
            start=tok.idx, end=tok.idx + len(tok.text), text=tok.text,
            reason=f"'{tok.text}' is on this reader's trigger list",
            score=1.0, alternatives=alts, pos=tok.pos_, tag=tok.tag_, hint=_hint_for(lw, tok.pos_),
        ))
    return out


# ---------------------------------------------------------------------------------------
# rare / long words
# ---------------------------------------------------------------------------------------
def detect_rare(doc, profile) -> list[Trigger]:
    sidx = _sent_index_of(doc)
    safe = {w.lower() for w in profile.safe_words}
    vocab = profile.vocab_set()
    out = []
    for tok in doc:
        if not is_content(tok) or tok.pos_ == "PROPN" or tok.lower_ in safe:
            continue
        if tok.lower_ in vocab or tok.lemma_.lower() in vocab:
            continue  # the reader uses this word themselves; it is not rare *for them*
        z = zipf(tok.lower_, profile.language)
        if 0 < z < profile.min_zipf:
            alts = _synonyms(tok, profile)
            out.append(Trigger(
                kind="rare", sent_index=sidx.get(tok.i, 0),
                start=tok.idx, end=tok.idx + len(tok.text), text=tok.text,
                reason=f"'{tok.text}' is an uncommon word (frequency {z:.1f} on a 1–7 scale)",
                score=min(1.0, (profile.min_zipf - z) / 2.0 + 0.3), alternatives=alts, pos=tok.pos_,
                tag=tok.tag_,
            ))
    return out


def detect_long(doc, profile) -> list[Trigger]:
    sidx = _sent_index_of(doc)
    safe = {w.lower() for w in profile.safe_words}
    out = []
    for tok in doc:
        if not is_content(tok) or tok.pos_ == "PROPN" or tok.lower_ in safe:
            continue
        if len(tok.text) > profile.max_word_length:
            out.append(Trigger(
                kind="long", sent_index=sidx.get(tok.i, 0),
                start=tok.idx, end=tok.idx + len(tok.text), text=tok.text,
                reason=f"'{tok.text}' is {len(tok.text)} letters long",
                score=min(1.0, 0.3 + (len(tok.text) - profile.max_word_length) * 0.1),
                alternatives=_synonyms(tok, profile), pos=tok.pos_, tag=tok.tag_,
            ))
    return out


def _synonyms(tok, profile) -> list[str]:
    """Plain-word alternatives for a token: curated table first, then WordNet if installed.

    Alternatives are ranked so words the reader already uses (profile.vocabulary) come first,
    then by frequency. Stays empty when nothing safe is known — flagging is still useful.
    """
    alts = list(_alts_for(tok.lower_, tok.pos_))
    try:
        from nltk.corpus import wordnet as wn  # optional extra
        posmap = {"NOUN": wn.NOUN, "VERB": wn.VERB, "ADJ": wn.ADJ, "ADV": wn.ADV}
        wpos = posmap.get(tok.pos_)
        if wpos:
            cands = set()
            for syn in wn.synsets(tok.lemma_.lower(), pos=wpos)[:3]:
                for lemma in syn.lemmas():
                    name = lemma.name().replace("_", " ")
                    if name.lower() != tok.lemma_.lower() and name.count(" ") <= 1:
                        cands.add(name)
            base_z = zipf(tok.lower_, profile.language)
            for c in cands:
                if zipf(c, profile.language) > base_z + 0.3 and len(c) <= len(tok.text):
                    alts.append(c)
    except Exception:
        pass
    vocab = profile.vocab_set()
    seen, ranked = set(), []
    for a in alts:
        if a.lower() in seen:
            continue
        seen.add(a.lower())
        ranked.append(a)
    ranked.sort(key=lambda a: (0 if a.lower() in vocab else 1, -zipf(a, profile.language)))
    return ranked[:3]
