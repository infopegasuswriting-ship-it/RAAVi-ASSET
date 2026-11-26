"""Facilitate one learner's local, chapter-by-chapter chat sessions."""
import argparse
import json
import math
import sys
import random
import time
from pathlib import Path
from syllabus import AREA_FOR, AREAS
from catalogue import catalogue

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "sessions.json"
LETTERS = "ABCD"
SOURCES = {"C27":"Cambridge O Level Pakistan Studies 2059, 2027 syllabus",
           "M":"MAP MARVELS","X":"6 Mark Question Examples by KH",
           **{f"S{i}":f"SOLVED HISTORY SEC {i} NOTES BY KH" for i in range(1,4)},
           **{f"H{i}":f"Hist Book {i} UP" for i in range(1,4)},
           **{f"G{i}":f"Geo Book {i} UP" for i in range(1,3)}}
DAY = 86400
COOLDOWN = 62 * DAY
CHAPTERS = {
    "History": [AREAS["H"][i-1][0] for i in (2,1,*range(3,17))],
    "Geography": ["Topography","Climate","Water resources","Forests","Minerals","Fishing",
                  "Agriculture","Power","Industry","Trade","Transport and telecommunications","Population and employment"]}
GEO_UNITS = [
    ["Location","Administrative areas and cities","Relief"], ["Climate"], ["Water","Irrigation geography"],
    ["Forests"], ["Minerals"], ["Fishing"], ["Agriculture"], ["Power"], ["Industry"],
    ["Trade","Trade institutions"], ["Transport","Development"], ["Population"]]
GEO_CHAPTER = {topic:name for name,topics in zip(CHAPTERS["Geography"],GEO_UNITS) for topic in topics}

def bank():
    result={}
    for row in (ROOT/"questions.txt").read_text(encoding="utf-8-sig").splitlines():
        family,subject,topic,skill,refs,stem,key,*tail=row.split("|")
        choices=[key,*tail[:-1]]
        assert len(set(choices))==len(choices)==4 and stem not in result
        area=AREA_FOR[subject,topic]
        chapter=area if subject=="H" else GEO_CHAPTER[topic]
        result[stem]=dict(family=family,subject=subject,area=area,chapter=chapter,topic=topic,skill=skill,refs=refs,key=key,choices=choices,why=tail[-1])
    def chapter_for(subject, topic):
        return AREA_FOR[subject,topic] if subject=="H" else GEO_CHAPTER[topic]
    for item in catalogue(result, chapter_for):
        stem=item.pop("stem")
        choices=[item["key"],*item.pop("wrong")]
        assert len(set(choices))==len(choices)==4 and stem not in result, stem
        topic,subject=item["topic"],item["subject"]
        result[stem]=dict(**item,chapter=chapter_for(subject,topic),
                          area=AREA_FOR[subject,topic],choices=choices)
    return result

def remaining_minutes(subject,history,now):
    starts=[s["started"] for s in history if s["subject"] in (subject,"Both")]
    if not starts:return 0
    return max(0, math.ceil((max(starts)+DAY-now)/60))

def availability(subject,history,now):
    minutes=remaining_minutes(subject,history,now)
    if not minutes:return f"{subject} — Available"
    hours,minutes=divmod(minutes,60)
    return f"{subject} — Limit reached. {hours}h {minutes:02d}m until you can start a new test."

def draw(items,subject,history,rng,now):
    if subject not in CHAPTERS:
        raise ValueError("Choose History or Geography.")
    if remaining_minutes(subject,history,now):
        raise ValueError(availability(subject,history,now))
    last_seen={}
    stem_seen={}
    detail_seen={}
    for session in history:
        for turn in session["turns"]:
            q=items.get(turn["stem"])
            if q:
                family=q["family"]
                seen=max(session["started"],turn.get("shown",0),turn.get("answered",0))
                last_seen[family]=max(last_seen.get(family,0),seen)
                stem_seen[turn["stem"]]=max(stem_seen.get(turn["stem"],0),seen)
                for detail in q.get("components",[family]):
                    detail_seen[detail]=max(detail_seen.get(detail,0),seen)
    turns=[]
    for chapter in CHAPTERS[subject]:
        pool=[stem for stem,q in items.items() if q["subject"]==subject[0] and q["chapter"]==chapter
              and last_seen.get(q["family"],float("-inf"))<=now-COOLDOWN]
        if not pool:
            raise ValueError(f"No complete session available. {chapter} has exhausted its eligible questions. No start was used.")
        rng.shuffle(pool)
        def priority(stem):
            q=items[stem]
            details=q.get("components",[q["family"]])
            latest=max(detail_seen.get(detail,float("-inf")) for detail in details)
            return (stem in stem_seen, last_seen.get(q["family"],float("-inf")), latest>now-7*DAY,
                    q["skill"] in ("matching","timeline"), latest)
        stem=min(pool,key=priority)
        q=items[stem]
        options=q["choices"][:]
        rng.shuffle(options)
        turns.append(dict(stem=stem,choices=options,repeat=q["family"] in last_seen))
    rng.shuffle(turns)
    return turns

def report(session,items):
    turns=session["turns"]
    graded=[t for t in turns if "response" in t]
    correct=sum(t["response"]==items[t["stem"]]["key"] for t in graded)
    lines=[f'{session["subject"]}: {correct}/{len(turns)} marks; {len(graded)}/{len(turns)} answered or skipped.']
    order=CHAPTERS["History"]+CHAPTERS["Geography"]
    for turn in sorted(turns,key=lambda t:order.index(items[t["stem"]]["chapter"])):
        q=items[turn["stem"]]
        if "response" not in turn: symbol="· Pending"
        elif turn["response"] is None: symbol="— Skipped (0)"
        elif turn["response"]==q["key"]: symbol="✓"
        else: symbol="✗"
        lines.append(f'{symbol}  {q["chapter"]}')
    return "\n".join(lines)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["start","next","answer","report","status"])
    parser.add_argument("value",nargs="?")
    args=parser.parse_args()
    items=bank()
    history=json.loads(LOG.read_text(encoding="utf8")) if LOG.exists() else []
    now=time.time()
    for old in history:
        if "started" not in old: old["started"]=LOG.stat().st_mtime
    if args.action=="status":
        while True:
            clock=time.time()
            print("   |   ".join(availability(subject,history,clock) for subject in CHAPTERS),end="\n" if not sys.stdout.isatty() else "\r",flush=True)
            if not sys.stdout.isatty() or not any(remaining_minutes(s,history,clock) for s in CHAPTERS):return
            time.sleep(1)
    if args.action=="start":
        if args.value not in CHAPTERS:parser.error("Choose History or Geography.")
        if remaining_minutes(args.value,history,now):
            parser.exit(0,availability(args.value,history,now)+"\n")
        if any(s["subject"]==args.value and any("response" not in t for t in s["turns"]) for s in history):
            parser.error(f"Resume your open {args.value} session with next {args.value}.")
        try: turns=draw(items,args.value,history,random.SystemRandom(),now)
        except ValueError as error: parser.error(str(error))
        history.append(dict(subject=args.value,started=now,turns=turns))
    if not history:parser.error("Start a History or Geography session first.")
    candidates=history
    if args.action in ("next","report") and args.value:
        candidates=[s for s in history if s["subject"]==args.value]
        if not candidates:parser.error("No saved session for that subject.")
    session=max(reversed(candidates),key=lambda s:s.get("active",s["started"]))
    if args.action=="start":session=history[-1]
    if args.action!="report":session["active"]=now
    pending=[t for t in session["turns"] if "response" not in t]
    if args.action=="answer":
        value=(args.value or "").strip().upper()
        if not pending or value not in (*LETTERS,"SKIP"):parser.error("Provide A, B, C, D or skip for the open question.")
        t=pending.pop(0)
        q=items[t["stem"]]
        t["answered"]=now
        t["response"]=None if value=="SKIP" else t["choices"][LETTERS.index(value)]
        print("Correct." if t["response"]==q["key"] else "Answer: "+q["key"]+".",q["why"],"Source:",q["refs"])
    if pending and args.action!="report":pending[0]["shown"]=now
    if args.action!="report":
        tmp=LOG.with_suffix(".tmp")
        tmp.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf8")
        tmp.replace(LOG)
    if args.action=="report" or not pending:
        print(report(session,items))
        for subject in CHAPTERS:print(availability(subject,history,now))
    else:
        t=pending[0]
        print(f"Question {len(session['turns'])+1-len(pending)}/{len(session['turns'])}",t["stem"],sep="\n")
        q=items[t["stem"]]
        if q["skill"]=="map pin":
            print("Show","city-pins.png" if q["refs"]=="M:3" else "barrage-pins.png")
        for letter,opt in zip(LETTERS,t["choices"]):print(letter,opt)

if __name__=="__main__":main()
