ATPL_NAME = "ATPL"
ATPL_PREFIX = "C"
ATPL_SUBJECTS = [
    "Meteorology", "General Navigation", "Radio Navigation", "Operational Procedures",
    "Principles of Flight", "VFR/IFR Communication", "Human Performance", "Air Law",
    "Airframe, Systems and Engines", "Instrumentation", "Mass and Balance", "Performance",
    "Flight Planning",
]


def refuse_if_data(apps):
    """Stop the programmes change set on a database that already holds groups or subjects."""
    if apps.get_model("roster", "Group").objects.exists() or apps.get_model(
        "scoring", "Subject"
    ).objects.exists():
        raise RuntimeError(
            "Delete db.sqlite3 and run migrate again (programmes change set, PLAN.md)."
        )
