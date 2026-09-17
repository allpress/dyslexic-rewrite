"""Test passages: original prose written for this project, in matched pairs.

Each pair has two passages of similar length, register and difficulty, and each passage carries
five multiple-choice questions that can only be answered from the text. The pairs deliberately
contain the trigger families the rewriter targets (heteronyms re-used with different meanings,
phrasal verbs, near-homophones, long sentences with embedded clauses) so that original vs
rewritten actually differ.

To add a pair: two dicts with the same `pair` key. Keep both within ~10% of each other in words.
"""

PASSAGES = [
    # ------------------------------------------------------------------ pair: lighthouse
    {
        "slug": "lighthouse-keeper", "pair": "lighthouse", "level": "general", "title": "The Lighthouse Keeper",
        "body": """Marta had kept the lighthouse on Gull Point for eleven years, and in all that time she had never once slept through a storm. The wind, which came in off the water every autumn like a debt collector, would wind itself around the tower and hum in the iron stairs until the whole building seemed to sing.

On the night the freighter lost its way, the lamp had been lit for an hour when the radio crackled. A voice, thin and far off, asked whether the light was working, because from the deck of the ship it looked as though it had gone out. Marta climbed the two hundred steps to check, even though she could see the beam sweeping the rain from her kitchen window, and found the glass fogged with salt on the seaward side.

She cleaned it with a rag she kept in her coat, and while she worked she thought about the keeper before her, an old man named Teodor who had refused to leave when the light was made automatic. The council had let him stay as a caretaker, which was the kind of decision councils make when they would rather not argue. He had taught her to read the weather from the colour of the water and to tear a strip of cloth from an old sheet rather than waste a new one.

By the time she came down, the freighter had turned. The captain radioed to say thank you, and to ask, a little sheepishly, whether the keeper was a man or a woman, because his chart still listed Teodor.""",
        "questions": [
            {"id": "lh1", "prompt": "How long had Marta kept the lighthouse?", "options": ["Two years", "Eleven years", "Twenty years", "Since she was a child"], "answer": 1},
            {"id": "lh2", "prompt": "Why did the ship's radio call?", "options": ["To report a fire on board", "To ask for the weather", "Because the light looked like it had gone out", "To ask for directions to the harbour"], "answer": 2},
            {"id": "lh3", "prompt": "What did Marta find at the top of the tower?", "options": ["A broken bulb", "Glass fogged with salt", "A bird's nest", "The door blown open"], "answer": 1},
            {"id": "lh4", "prompt": "Who was Teodor?", "options": ["The ship's captain", "Marta's brother", "The keeper before Marta", "A council member"], "answer": 2},
            {"id": "lh5", "prompt": "What did the captain ask at the end?", "options": ["Whether the keeper was a man or a woman", "Whether the harbour was open", "How old the lighthouse was", "Whether Marta needed help"], "answer": 0},
        ],
    },
    {
        "slug": "ferry-clerk", "pair": "lighthouse", "level": "general", "title": "The Ferry Clerk",
        "body": """Jonah sold tickets at the ferry office in Harrow Bay for nine years, and in all that time he had never once missed the first crossing. The tide, which crept up the slipway every morning like a cat that did not want to be noticed, would lead the boats out one at a time until the harbour stood empty.

On the morning the school trip went wrong, the office had been open for an hour when the phone rang. A teacher, breathless and a little cross, asked whether the ten o'clock boat had already left, because from the car park it looked as though the ramp was up. Jonah walked down to the pier to check, even though he could see the ferry from his window, and found the ramp raised because a crate of lead pipes had been left across it.

He rolled the crate aside with the porter's help, and while he pushed he thought about the clerk before him, a woman named Ines who had refused to retire when the office switched to printed tickets. The company had let her stay on as a greeter, which was the sort of choice companies make when they would rather not have a fuss. She had taught him to read the sky from the gulls and to wind the old clock in the office every Friday rather than trust the new one.

By the time he got back, the children were boarding. The teacher came over to say thank you, and to ask, a little embarrassed, whether the office still took cash, because her list said tickets could only be bought from Ines.""",
        "questions": [
            {"id": "fc1", "prompt": "How long had Jonah sold tickets at the ferry office?", "options": ["Four years", "Nine years", "Fifteen years", "Since he left school"], "answer": 1},
            {"id": "fc2", "prompt": "Why did the teacher phone?", "options": ["To cancel the trip", "Because the ramp looked like it was up", "To ask about the weather", "To complain about the price"], "answer": 1},
            {"id": "fc3", "prompt": "What was blocking the ramp?", "options": ["A parked car", "A crate of lead pipes", "A fallen sign", "A pile of ropes"], "answer": 1},
            {"id": "fc4", "prompt": "Who was Ines?", "options": ["The teacher", "The porter's wife", "The clerk before Jonah", "The ferry captain"], "answer": 2},
            {"id": "fc5", "prompt": "What did the teacher ask at the end?", "options": ["Whether the office still took cash", "Whether the boat was safe", "How long the crossing took", "Whether Jonah was new"], "answer": 0},
        ],
    },
    # ------------------------------------------------------------------ pair: kitchen
    {
        "slug": "sourdough", "pair": "kitchen", "level": "general", "title": "Starting a Sourdough",
        "body": """A sourdough starter is nothing more than flour, water and patience, but the patience is the part most people get wrong. On the first day you mix equal weights of flour and water in a jar, cover it loosely, and leave it somewhere warm. Nothing will seem to happen, which is normal, and the temptation to stir it or move it or add more flour should be resisted.

By the third day the mixture will smell sour and a little like beer, and small bubbles will have appeared near the top. This is the point at which you begin to feed it: throw half away, then add fresh flour and water. It feels wasteful, and it is, but a starter that is not fed grows weak and eventually dies, whereas one that is fed on the same schedule every day will double in size within a few hours of each feeding.

Bakers argue about which flour is best. Rye gets a starter going fastest because it carries more of the wild yeast the process depends on, while plain white flour is slower to wake up but easier to keep. Whichever you choose, use the same one every day, since switching confuses the balance of yeast and bacteria that gives sourdough its taste.

After a week, drop a spoonful into a glass of water. If it floats, the starter has trapped enough gas to raise a loaf, and you can bake with it. If it sinks, feed it for a few more days and try again. The oldest starters in the world have been fed like this, day after day, for more than a century.""",
        "questions": [
            {"id": "sd1", "prompt": "What should you do on the first day?", "options": ["Bake a small loaf", "Mix equal weights of flour and water and leave it", "Add yeast from a packet", "Put the jar in the fridge"], "answer": 1},
            {"id": "sd2", "prompt": "By the third day the starter smells like what?", "options": ["Vinegar", "Bread", "Beer", "Nothing at all"], "answer": 2},
            {"id": "sd3", "prompt": "What happens to a starter that is not fed?", "options": ["It gets stronger", "It turns to dough", "It grows weak and dies", "It doubles in size"], "answer": 2},
            {"id": "sd4", "prompt": "Why does rye flour get a starter going fastest?", "options": ["It is cheaper", "It carries more wild yeast", "It absorbs more water", "It has no gluten"], "answer": 1},
            {"id": "sd5", "prompt": "What does it mean if a spoonful of starter floats?", "options": ["It has gone bad", "It needs more flour", "It is ready to bake with", "It is too wet"], "answer": 2},
        ],
    },
    {
        "slug": "pickling", "pair": "kitchen", "level": "general", "title": "Pickling Cucumbers",
        "body": """A jar of pickles is nothing more than cucumbers, salt and time, but the time is the part most people get impatient with. On the first day you wash the cucumbers, pack them into a clean jar with a few cloves of garlic and a sprig of dill, and pour over a brine of salt dissolved in water. Nothing will seem to happen, which is normal, and the urge to open the jar or add vinegar to speed things up should be resisted.

By the third day the brine will turn cloudy and a few bubbles will rise when you tap the glass. This is the point at which you check the seal: the cucumbers must stay under the surface, so weigh them down with a small dish if they float. It feels fussy, and it is, but any cucumber that sits above the brine will spoil, whereas the ones that stay submerged will slowly sour from the inside out over the next week.

Cooks argue about how much salt to use. A weak brine sours the cucumbers quickly but leaves them soft, while a stronger brine is slower to work but keeps them crisp for months. Whichever you choose, keep the jar at the same temperature every day, since a warm afternoon followed by a cold night upsets the balance of bacteria that gives a pickle its taste.

After a week, cut one open. If it is sour all the way through and still snaps when you bend it, the batch is done and can go in the fridge. If the middle is still plain, close the jar and wait a few more days. Some families keep a brine going like this, jar after jar, for generations.""",
        "questions": [
            {"id": "pk1", "prompt": "What goes into the jar on the first day?", "options": ["Cucumbers, garlic, dill and brine", "Cucumbers and vinegar", "Cucumbers and sugar", "Cucumbers and oil"], "answer": 0},
            {"id": "pk2", "prompt": "What does the brine look like by the third day?", "options": ["Clear", "Cloudy", "Green", "Frozen"], "answer": 1},
            {"id": "pk3", "prompt": "What happens to a cucumber that sits above the brine?", "options": ["It sours faster", "It stays crisp", "It spoils", "It turns sweet"], "answer": 2},
            {"id": "pk4", "prompt": "What does a stronger brine do?", "options": ["Sours the cucumbers faster", "Keeps them crisp for months", "Makes them soft", "Turns them cloudy"], "answer": 1},
            {"id": "pk5", "prompt": "How do you know the batch is done?", "options": ["The jar stops bubbling", "The brine turns clear", "A cut pickle is sour through and still snaps", "The garlic turns blue"], "answer": 2},
        ],
    },
    # ------------------------------------------------------------------ pair: workplace
    {
        "slug": "the-audit", "pair": "workplace", "level": "general", "title": "The Audit",
        "body": """When the auditors arrived on Monday, nobody in the accounts office had been told, which was the first sign that the week would not go as planned. Priya, who had run the office for six years and had never once had a set of books sent back, was asked to produce every invoice from the previous quarter before lunch.

The problem, it turned out, was not the invoices but the way they had been filed. A temp hired over the summer had sorted them by the date they were paid rather than the date they were issued, so that a bill from March could sit behind one from June, and the auditors, who worked from issue dates, kept finding gaps that were not really gaps at all.

Priya explained this three times. The lead auditor, a polite man named Okafor who wrote everything down in a green notebook, listened each time and then asked for the same records again in a slightly different order. By Wednesday she had stopped explaining and simply re-filed the entire quarter herself, staying until nine to do it.

On Friday Okafor closed his notebook and said that the books were clean, that the filing had cost them two days, and that he would note in his report that the office was under-staffed. Priya thanked him, went back to her desk, and wrote a memo asking for the temp's contract to be extended, on the grounds that anyone who could invent a filing system that baffled three auditors was worth keeping.""",
        "questions": [
            {"id": "au1", "prompt": "What was the first sign the week would go badly?", "options": ["The computers were down", "Nobody had been told the auditors were coming", "Priya was on holiday", "The invoices were missing"], "answer": 1},
            {"id": "au2", "prompt": "How had the temp sorted the invoices?", "options": ["By supplier name", "By the date they were paid", "By the date they were issued", "By amount"], "answer": 1},
            {"id": "au3", "prompt": "What did Okafor write in?", "options": ["A laptop", "A red folder", "A green notebook", "The margins of the invoices"], "answer": 2},
            {"id": "au4", "prompt": "What did Priya do by Wednesday?", "options": ["Called her manager", "Went home early", "Re-filed the entire quarter herself", "Asked the temp to come back"], "answer": 2},
            {"id": "au5", "prompt": "What did Priya's memo ask for?", "options": ["A new filing cabinet", "The temp's contract to be extended", "A week off", "A different auditor"], "answer": 1},
        ],
    },
    {
        "slug": "the-inspection", "pair": "workplace", "level": "general", "title": "The Inspection",
        "body": """When the inspector arrived on Tuesday, nobody in the kitchen had been warned, which was the first hint that the week would not run smoothly. Dario, who had managed the kitchen for seven years and had never once failed an inspection, was asked to show the temperature logs for every fridge going back three months before the lunch service started.

The trouble, it emerged, was not the logs but the way they had been kept. A new cook hired in the spring had written the readings in Celsius on some days and Fahrenheit on others, so that a fridge could appear to swing from four degrees to thirty-nine overnight, and the inspector, who expected Celsius throughout, kept finding faults that were not really faults at all.

Dario explained this twice. The inspector, a brisk woman named Halvorsen who photographed everything with a small camera, listened each time and then asked to see the same fridges again with a thermometer of her own. By Thursday he had stopped explaining and simply rewrote the entire three months in Celsius, staying after close to do it.

On Friday Halvorsen put away her camera and said the kitchen was safe, that the logs had cost her a day and a half, and that she would note in her report that the staff needed a single system. Dario thanked her, went back to the pass, and pinned a memo by the fridges asking the new cook to stay on, on the grounds that anyone who could keep both scales in his head at once would make a fine sous-chef.""",
        "questions": [
            {"id": "in1", "prompt": "What was the first hint the week would go badly?", "options": ["The fridges had broken", "Nobody had been warned the inspector was coming", "Dario was late", "The logs were lost"], "answer": 1},
            {"id": "in2", "prompt": "What had the new cook done with the readings?", "options": ["Forgotten to take them", "Written them in two different scales", "Written them in pencil", "Rounded them up"], "answer": 1},
            {"id": "in3", "prompt": "What did Halvorsen use to record things?", "options": ["A notebook", "A tablet", "A small camera", "A voice recorder"], "answer": 2},
            {"id": "in4", "prompt": "What did Dario do by Thursday?", "options": ["Bought a new fridge", "Rewrote three months of logs in Celsius", "Closed the kitchen", "Sent the cook home"], "answer": 1},
            {"id": "in5", "prompt": "What did Dario's memo ask for?", "options": ["New thermometers", "The new cook to stay on", "A day off", "A different inspector"], "answer": 1},
        ],
    },
]


def seed(conn) -> int:
    """Insert or update every passage. Returns the number written."""
    import json
    n = 0
    for p in PASSAGES:
        words = len(p["body"].split())
        conn.execute(
            "INSERT INTO passages (slug, pair, title, level, words, body, questions) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (slug) DO UPDATE SET pair=EXCLUDED.pair, title=EXCLUDED.title, level=EXCLUDED.level, "
            "words=EXCLUDED.words, body=EXCLUDED.body, questions=EXCLUDED.questions",
            (p["slug"], p["pair"], p["title"], p["level"], words, p["body"], json.dumps(p["questions"])),
        )
        n += 1
    conn.commit()
    return n
