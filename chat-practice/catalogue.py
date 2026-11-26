"""Build the local practice catalogue from authored prompts and source-linked events."""
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations, permutations
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent
SUPPLEMENTS = {
    "month": "January February March April May June July August September October November December".split(),
    "season": ["Winter", "Summer", "Spring", "Autumn"],
    "work": ["Now or Never", "Heer", "Tarana-e-Milli"],
    "province": ["Punjab", "Sindh", "Balochistan", "Khyber Pakhtunkhwa"],
    "river": ["Indus", "Jhelum", "Chenab", "Ravi", "Sutlej", "Kabul"],
    "country": ["Iran", "Turkey", "China", "Afghanistan", "India", "Bangladesh"],
    "city": ["Lahore", "Karachi", "Multan", "Peshawar", "Quetta"],
}

def identifier(text):
    return sha256(text.encode()).hexdigest()[:16]

def lines(name):
    return [x.strip() for x in (ROOT/name).read_text(encoding="utf-8-sig").splitlines()
            if x.strip() and not x.startswith("#")]

def recall():
    records = []
    for line in lines("recall-facts.txt"):
        if line.startswith("@"):
            subject, topic = line[1:].split("|")
            continue
        refs, kind, stem, key, *wrong = line.split("|")
        records.append(dict(subject=subject, topic=topic, refs=refs, skill=kind, stem=stem,
                            key=key, wrong=wrong, family="R-"+identifier(stem)))
    for item in records:
        if item["wrong"]:
            continue
        kind, key = item["skill"], item["key"]
        rng = random.Random(item["stem"])
        if kind in ("count","year"):
            number = int(key)
            distance = [1,2,3,4] if kind=="count" else [1,2,3,4,5,7]
            candidates = [str(number+sign*delta) for delta in distance for sign in (-1,1)
                          if number+sign*delta>0]
        else:
            candidates = [r["key"] for r in records if r["skill"]==kind and r["subject"]==item["subject"]]
            candidates += SUPPLEMENTS.get(kind, [])
        choices = sorted(set(candidates)-{key})
        if len(choices)<3:
            raise ValueError((kind, key, choices))
        rng.shuffle(choices)
        if kind in ("person", "institution", "city", "place"):
            near = {r["key"] for r in records if r["topic"]==item["topic"] and r["skill"]==kind}
            volume = {r["key"] for r in records if r["refs"][:2]==item["refs"][:2] and r["skill"]==kind}
            choices.sort(key=lambda value:(value not in near,value not in volume))
        item["wrong"] = choices[:3]
    for item in records:
        item["why"] = "Keyed detail in the cited notes: "+item["key"]+"."
    return records

def combine(parts, stem, options, skill, why):
    ids = sorted(p["family"] for p in parts)
    refs = dict.fromkeys(ref for p in parts for ref in p["refs"].split(";"))
    return dict(subject=parts[0]["subject"], topic=parts[0]["topic"], refs=";".join(refs),
                stem=stem, key=options[0], wrong=options[1:], skill=skill, why=why,
                family=skill+"-"+identifier(" ".join(ids)), components=ids)

def catalogue(base, chapter_for):
    records = recall()
    events = {}
    for line in lines("timeline.txt"):
        fragment, label = line.split("|")
        event, = [q for q in records if q["skill"]=="year" and fragment in q["stem"]]
        events[event["family"]] = label
    by_chapter = defaultdict(list)
    for q in records:
        by_chapter[chapter_for(q["subject"], q["topic"])].append(q)
    totals = Counter(q["chapter"] for q in base.values())
    for chapter, facts in by_chapter.items():
        output = facts[:]
        rng = random.Random("RAAVi "+chapter)
        dated = [q for q in facts if q["family"] in events]
        sets = list(combinations(dated, 3))
        rng.shuffle(sets)
        for group in sets:
            if len({p["key"] for p in group}) != 3:
                continue
            group = sorted(group, key=lambda q:int(q["key"]))
            labels = [events[q["family"]] for q in group]
            display = sorted(labels)
            codes = {name:chr(65+i) for i,name in enumerate(display)}
            order = [codes[name] for name in labels]
            key = " → ".join(order)
            wrong = sorted({" → ".join(seq) for seq in permutations(order)}-{key})
            stem = "Which sequence runs from earliest to latest? "+ "  ".join(codes[label]+". "+label for label in display)
            why = " → ".join(name+" ("+q["key"]+")" for name,q in zip(labels,group))+"."
            output.append(combine(group, stem, [key,*rng.sample(wrong,3)], "timeline",why))
        for size in (2,3):
            sets = list(combinations(facts,size))
            rng.shuffle(sets)
            for group in sets:
                if totals[chapter]+len(output)>=200:
                    break
                if len({p["key"].casefold() for p in group})!=size:
                    continue
                if any(len(p["key"])>=3 and p["key"].casefold() in other["stem"].casefold()
                       for p in group for other in group if other is not p):
                    continue
                if size==3 and all(p["family"] in events for p in group):
                    continue
                stem = "Which row answers these clues in order? "+"  ".join(f"({i}) {p['stem']}" for i,p in enumerate(group,1))
                masks = [0,1,2,3] if size==2 else [0,3,5,6]
                foils = [rng.choice(p["wrong"]) for p in group]
                options = [" / ".join(foils[i] if mask & (1<<i) else p["key"]
                                      for i,p in enumerate(group)) for mask in masks]
                why = "  ".join(f"({i}) {p['key']} [{p['refs']}]" for i,p in enumerate(group,1))
                output.append(combine(group, stem, options, "matching",why))
        assert len(output)+totals[chapter]==200, chapter
        yield from output
