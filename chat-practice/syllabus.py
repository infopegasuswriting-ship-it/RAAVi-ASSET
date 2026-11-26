"""Cambridge O Level Pakistan Studies 2059, 2027. Primary coverage per item."""
AREAS = {
    "H": [
        ("Religious thinkers", ["Religious reform"]),
        ("Mughal decline and British expansion", ["Mughal decline", "Company expansion"]),
        ("Uprising of 1857", ["1857 uprising"]),
        ("Sir Syed Ahmad Khan", ["Aligarh"]),
        ("Urdu and regional languages", ["Languages"]),
        ("Early Pakistan Movement", ["Representation"]),
        ("Khilafat Movement", ["Khilafat"]),
        ("Pakistan Movement, 1927–39", ["Constitutional proposals"]),
        ("Negotiations and partition, 1940–47", ["Transfer of power"]),
        ("Jinnah, Iqbal and Rahmat Ali", ["Political ideas"]),
        ("Establishing Pakistan", ["Independence settlement"]),
        ("Stability and government after Jinnah", ["Early ministries", "Agrarian reform"]),
        ("Creation of Bangladesh", ["East Pakistan"]),
        ("Bhutto and Zia", ["Bhutto and Zia"]),
        ("Governments, 1988–99", ["Governments 1988–99"]),
        ("International relations", ["Foreign relations"]),
    ],
    "G": [
        ("Land, location, drainage and climate", ["Location", "Administrative areas and cities", "Relief", "Climate"]),
        ("Natural resources and sustainability", ["Water", "Irrigation geography", "Forests", "Minerals", "Fishing"]),
        ("Power", ["Power"]),
        ("Agriculture", ["Agriculture"]),
        ("Industry", ["Industry"]),
        ("Trade", ["Trade", "Trade institutions"]),
        ("Transport and telecommunications", ["Transport", "Development"]),
        ("Population and employment", ["Population"]),
    ],
}
AREA_FOR = {(s,topic): title for s,areas in AREAS.items() for title,topics in areas for topic in topics}
