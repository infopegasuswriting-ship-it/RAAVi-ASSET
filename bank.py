"""RAAVi-authored questions aligned to the two KH workbook topic sequences."""
import random
import re
from collections import Counter

# Subject, chapter, stem, correct choice, then three distractors.
HISTORY = [
("Religious reformers","A reformer wanted Muslims outside the scholarly elite to understand the Quran directly. Which intervention best served that aim?","Shah Waliullah’s Persian translation","The Faraizi campaign against unlawful taxes","The foundation of the MAO College","The establishment of the Scientific Society"),
("British expansion","A ruler died leaving an adopted heir. Which policy allowed the Company to deny succession and take the state?","Doctrine of Lapse","Subsidiary Alliance","Permanent Settlement","Separate electorates"),
("1857 uprising","Which change after the uprising directly altered who exercised sovereignty over British India?","The Crown took over government from the Company","The Company received a renewed trading monopoly","Provincial ministers gained responsible government","The Mughal emperor regained control over revenue"),
("Sir Syed Ahmad Khan","A historian claims Sir Syed sought to repair British–Muslim relations after 1857. Which evidence most directly supports that claim?","He wrote an analysis explaining Indian grievances to British readers","He promoted English-medium science instruction","He founded a society to translate scientific works","He established a college at Aligarh"),
("Languages","Which tension best explains opposition in East Pakistan to Urdu as the sole state language?","A national unifying symbol conflicted with the majority’s mother tongue","Bengali lacked an established literary tradition","Bengali was already the sole federal language","Urdu was the first language of most East Pakistanis"),
("Pakistan Movement 1905–1919","Which sequence puts all four political developments in chronological order?","Partition of Bengal, Simla Deputation, separate electorates, Lucknow Pact","Simla Deputation, Partition of Bengal, Lucknow Pact, separate electorates","Partition of Bengal, separate electorates, Simla Deputation, Lucknow Pact","Lucknow Pact, Simla Deputation, separate electorates, Partition of Bengal"),
("Khilafat Movement","Which development removed the institution that the Khilafat campaign sought to protect?","Abolition of the caliphate by Turkey in 1924","End of the Ottoman sultanate in 1922 alone","Suspension of non-cooperation in 1922","The Amritsar massacre in 1919"),
("Pakistan Movement 1927–1939","A constitutional proposal leaves residual powers with the provinces and protects separate electorates. Which programme fits both conditions?","Jinnah’s Fourteen Points","The Nehru Report","The Cripps offer alone","The 3 June Plan"),
("Pakistan Movement 1940–1947","Which feature distinguished the Cabinet Mission proposals from immediate partition into two sovereign states?","A limited union with provincial groupings","An immediate boundary commission for Punjab","Two independent dominions from August 1947","Division of the Indian army between two dominions"),
("Iqbal and Rahmat Ali","Which distinction between Iqbal’s 1930 address and Rahmat Ali’s 1933 pamphlet is accurate?","Iqbal discussed a consolidated north-western Muslim state; Rahmat Ali proposed the name Pakistan","Iqbal proposed the name Pakistan; Rahmat Ali chaired the Allahabad session","Both documents demanded identical eastern and western boundaries","Both documents were adopted as the Lahore Resolution"),
("Early challenges","Why could partition leave an irrigation canal in Pakistan vulnerable even when its command area lay wholly within Pakistan?","The headworks controlling its flow could lie across the border","Canal water could only be supplied by coastal rainfall","The boundary followed every canal from source to outlet","All irrigation works had been administered by princely states"),
("Early ministries","Why did parity between the two wings in the 1956 legislature matter for East Pakistan?","Equal seats denied the more populous wing a proportional majority","Parity reserved all federal ministries for the eastern wing","Parity abolished representation for the western provinces","Equal seats required a separate head of state for each wing"),
("Creation of Bangladesh","Which outcome of the 1970 election made delaying a transfer of power especially contentious?","The Awami League had a national assembly majority concentrated in the east","No party won a majority in East Pakistan","The PPP won a majority of all national assembly seats","The two largest parties won equal numbers nationally"),
("Bhutto and Zia","Which institutional change is associated with the Eighth Amendment under Zia?","Presidential power to dissolve the National Assembly under Article 58(2)(b)","Abolition of the presidency","First introduction of the One Unit scheme","Replacement of parliamentary elections with hereditary succession"),
("International relations","Why did Pakistan seek membership of Western-sponsored defence pacts in the 1950s?","To obtain military assistance amid regional security concerns","To join the Warsaw Pact’s integrated command","To acquire permanent UN Security Council membership","To settle the Indus waters dispute through a defence treaty"),
]
GEOGRAPHY = [
("Landforms","A river emerges from a steep mountain gorge onto a plain and splits into distributary channels over coarse sediment. Which process best explains the deposit?","Loss of transport capacity as gradient decreases","Marine deposition behind a coastal spit","Glacial abrasion beneath moving ice","Wind deflation removing fine material"),
("Climate","Two Pakistani cities have similar latitude and elevation. The coastal city has a smaller annual temperature range. Which explanation best isolates the maritime effect?","Water heats and cools more slowly than land","The coastal city receives more direct winter sunlight","Altitude increases seasonal temperature range at the coast","Monsoon rainfall fixes the same temperature year-round"),
("Water resources","A canal command has a rising water table and salt crusts despite adequate irrigation supply. Which intervention addresses both problems most directly?","Install drainage and flush salts with suitable water","Increase irrigation while leaving drainage unchanged","Seal field drains to retain more water","Switch to surface flooding throughout the year"),
("Forests","After upland clearance, a reservoir loses capacity faster despite unchanged rainfall totals. Which link best explains the observation?","Reduced interception and root cover increase erosion and sediment delivery","Reduced shade raises the dam’s concrete temperature","Reduced transpiration eliminates river discharge","Tree removal increases the reservoir’s original depth"),
("Mineral resources","A high-grade mineral deposit remains unworked in a remote district. Which evidence most directly establishes economic feasibility?","Recoverable output at expected prices covers extraction and transport costs","The ore has a high metal concentration alone","The deposit is visible at the surface in one outcrop","The district has low population density"),
("Fishing","Landings rise but catch per boat-day falls as fishing effort expands. Which conclusion is best supported?","More effort can conceal falling catch rates","The fish stock must be growing faster than effort","Each vessel is becoming more productive","The higher catch proves harvesting is sustainable"),
("Agriculture","A farm increases wheat output by 12% while harvested area rises by 20%. What happened to yield per hectare?","It fell by about 6.7%","It rose by 8%","It fell by exactly 8%","It rose by about 6.7%"),
("Power resources","Which constraint most directly reduces dependable hydroelectric output during a dry season even with installed turbine capacity unchanged?","Lower available discharge through turbines","Higher solar radiation at the site","Reduced national transmission distance","Lower fuel imports at thermal plants"),
("Industry","A fruit-processing plant locates near orchards despite a distant urban market. Which combination most strongly favours that choice?","Perishable bulky inputs and lower outward weight after processing","Non-perishable inputs and high finished-product bulk","Identical transport cost at every location","An output that must be sold immediately at the orchard"),
("Trade","Export revenue rises from 80 to 92 units while import spending rises from 100 to 118. How does the merchandise trade deficit change?","It widens by 6 units","It narrows by 12 units","It widens by 18 units","It narrows by 6 units"),
("Transport","For regular long-distance movement of heavy, low-value freight, when is rail most likely to outperform road on cost?","Large consistent loads connect terminals with little onward haulage","Small irregular loads need door-to-door delivery to scattered farms","The route has frequent transfers and short hauls","Deliveries change destination daily and stations are distant"),
("Population","Birth and death rates fall together, yet population grows rapidly for years. Which feature best explains demographic momentum?","A large cohort is entering childbearing ages","The crude death rate exceeds the birth rate","All age groups are equal in size","Life expectancy must be falling"),
("Climate","A western upland station receives a winter precipitation maximum. Which mechanism best accounts for it?","Westerly depressions with uplift over relief","Summer monsoon winds at their seasonal peak","Sea breezes acting uniformly across the Indus plain","Tropical cyclones crossing the coast every winter"),
("Water resources","Two farms receive equal canal allocations at their outlets. Which observation best explains a lower share reaching crops on one farm?","Longer unlined watercourses in permeable ground","Higher crop prices in the nearest city","A shorter distance from outlet to field","Greater use of lined channels"),
("Population","District A has more people but a lower population density than district B. What must be true?","A has a larger land area than B","A has a lower birth rate than B","B has more urban residents than A","B has the higher rate of natural increase"),
]
EXAMS = {
"History":[("1857 uprising","Explain why different groups in India took part in the uprising of 1857.",7),("Pakistan Movement 1927–1939","Explain why the Nehru Report led Jinnah to put forward his Fourteen Points.",7),("Pakistan Movement 1940–1947","How far was the outcome of the 1945–46 elections the most important reason for the creation of Pakistan in 1947? Explain your judgement.",14)],
"Geography":[("Water resources","Explain how canal irrigation can increase agricultural output yet reduce the productivity of some farmland in Pakistan.",7),("Industry","Explain why industrial development in Pakistan is concentrated in particular locations. Use examples.",7),("Power resources","To what extent can expanding hydroelectric power meet Pakistan’s energy needs? Evaluate its potential alongside other sources and reach a supported judgement.",14)]
}

def build(subject,mode,previous):
    subjects=["History","Geography"] if subject=="Both" else [subject]
    if mode=="exam":
        if len(subjects)==1:
            selected=[(subject,q) for q in EXAMS[subject]]
        else:
            random.shuffle(subjects)
            selected=[(s,random.choice(EXAMS[s][:2])) for s in subjects]
            selected.append((subjects[0], EXAMS[subjects[0]][2]))
        return [dict(subject=s,chapter=c,prompt=p,max=m) for s,(c,p,m) in selected]
    used=Counter(q["prompt"] for form in previous for q in form)
    coverage=Counter((q["subject"],q["chapter"]) for form in previous for q in form)
    result=[]
    for s in subjects:
        pool=list(HISTORY if s=="History" else GEOGRAPHY)
        chapters=set()
        for _ in range(10//len(subjects)):
            random.shuffle(pool)
            q=min(pool,key=lambda x:(x[0] in chapters,coverage[s,x[0]],used[x[1]]))
            pool.remove(q)
            chapter,prompt,key,*others=q
            options=[key,*others]
            random.shuffle(options)
            result.append(dict(subject=s,chapter=chapter,prompt=prompt,choices=options,key=key,max=1))
            chapters.add(chapter)
    random.shuffle(result)
    return result
