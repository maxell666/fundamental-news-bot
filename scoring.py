"""Le score suit la pertinence de l'événement, pas le nombre de mots sensibles."""

from filter import assess_news


def compute_score(text, description=""):
    return assess_news(text, description).score
