"""Prompts served by GET /api/read-aloud-prompts.

Read-aloud passages are original prose written for this project, kept warm and easy, and each
one deliberately reuses a heteronym in two senses, a phrasal verb, and a near-homophone pair —
the same trigger families the rewriter targets — so an offline pipeline can later compare how
someone reads them aloud against how the site rewrites text for them.

Free-speech prompts are questions meant to get someone talking for about a minute in their own
words, about something concrete and low-stakes.
"""

from __future__ import annotations

READ_ALOUD = [
    {
        "id": "sunday-bread",
        "title": "Sunday Bread",
        "text": (
            "Every Sunday morning I get up early to bake bread. I set out the flour and water "
            "first, then read the recipe card out loud so I don't skip a step, even though I "
            "could read it from memory by now. The dough starts as a loose, sticky mess, but if "
            "you fold it and wait, it will slowly form into something smooth. I put the bowl by "
            "the window, where a little wind slips in and cools the kitchen while the loaf "
            "rises. Before I carry the finished loaf next door, I wind a bit of string around "
            "the basket so it doesn't spill."
        ),
    },
    {
        "id": "learning-to-row",
        "title": "Learning to Row",
        "text": (
            "My uncle taught me to row on a quiet lake behind his house. The first time out, he "
            "made me read the safety card twice before we set off, and I remember how the oars "
            "felt too big for my hands. Later that summer I read a whole book about currents "
            "just so I would sound like I knew what I was doing. It rained the day we finally "
            "got it quite right, gliding past the reeds without a single splash. He still "
            "teases me about the morning I rowed us in a slow circle instead of a straight line."
        ),
    },
    {
        "id": "the-old-bike",
        "title": "The Old Bike",
        "text": (
            "The bike in our shed used to belong to my grandfather, who kept it under an old "
            "lead sheet to stop the rust. He taught me to look after it properly, oiling the "
            "chain and checking where the brakes wore thin. Once the tyres were fixed, he would "
            "lead me down the lane on my first proper ride, calling out directions from behind. "
            "I never knew where I would end up wearing that helmet of his, a little too big and "
            "always sliding forward. These days I look after the bike myself, and I still take "
            "the same lane he showed me."
        ),
    },
    {
        "id": "sunday-market",
        "title": "Sunday Market",
        "text": (
            "On Saturdays the market stalls stay open late, but by evening most sellers start to "
            "close up for the night. I like to pick out a few ripe tomatoes and something sweet "
            "before the good ones are gone. Last week I ran through the whole row of stalls "
            "twice, and a friend joked that I threw my whole morning at finding the perfect "
            "peach. My favourite stall sits close to the fountain, where the smell of fresh "
            "bread drifts over from the bakery next door. We always end up staying longer than "
            "planned, just talking by the flowers."
        ),
    },
]

FREE_SPEECH = [
    {
        "id": "room-you-changed",
        "title": "A room you changed",
        "text": "Tell us about a room you changed — what it looked like before, and what you did to it.",
    },
    {
        "id": "meal-you-cook",
        "title": "A meal you cook",
        "text": "Talk us through a meal you like to cook, from start to finish, as if you were teaching someone.",
    },
    {
        "id": "directions-home",
        "title": "Directions to your place",
        "text": "Imagine giving directions to your home from the nearest station or main road. Talk us through it.",
    },
    {
        "id": "skill-you-taught-yourself",
        "title": "A skill you taught yourself",
        "text": "Describe a skill you taught yourself, how you got started, and what was hardest about learning it.",
    },
]


def all_prompts() -> list[dict]:
    """Every prompt in the {id, kind, title, text, words} shape the API returns."""
    out = []
    for p in READ_ALOUD:
        out.append({"id": p["id"], "kind": "read_aloud", "title": p["title"], "text": p["text"],
                    "words": len(p["text"].split())})
    for p in FREE_SPEECH:
        out.append({"id": p["id"], "kind": "free_speech", "title": p["title"], "text": p["text"], "words": 0})
    return out


PROMPTS_BY_ID = {p["id"]: p for p in all_prompts()}
