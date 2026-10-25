ATTRIBUTES = [
    ("attentiveness", "Attentiveness / Engagement", "Attentiveness Engagement"),
    ("motivation", "Motivation / Diligence / Enthusiasm", "Motivation Diligence Enthusiasm"),
    ("discipline", "Discipline / Courtesy", "Discipline Courtesy"),
    ("attire", "Attire / Appearance", "Attire Appearance"),
    ("teamwork", "Teamwork", "Teamwork"),
    (
        "communication",
        "Communication / Participation / Interaction",
        "Comms. Participation Interaction",
    ),
]
ATTRIBUTE_FIELDS = [a[0] for a in ATTRIBUTES]
SCORE_CHOICES = [
    (5, "5 – A Excellent"),
    (4, "4 – B Above standard"),
    (3, "3 – C Meets standard"),
    (2, "2 – D Below standard"),
    (1, "1 – E Unacceptable"),
]
BLANK_COUNTS_AS = 3
