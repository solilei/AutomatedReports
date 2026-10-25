from scoring.models import CadetScore, ScoreSet


def make_score_set(instructor, subject, group, rows):
    score_set = ScoreSet.objects.create(instructor=instructor, subject=subject, group=group)
    for cadet, values in rows.items():
        CadetScore.objects.create(score_set=score_set, cadet=cadet, **values)
    return score_set
