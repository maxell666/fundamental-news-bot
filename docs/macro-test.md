# Essai gratuit de résultat macro

Essai unique : Chicago PMI d'octobre, le **30 octobre 2026 à
13:45 UTC / 14:45 Europe/Paris / 09:45 America/New_York**.
Il s'agit d'un essai technique, distinct du projet Annonces éco V4.

Le consensus et le précédent sont lus dans le calendrier JSON public de
Forex Factory et enregistrés avant l'heure prévue. Leur date, devise,
intitulé et unité doivent correspondre exactement à l'événement.
Le résultat est lu sur la page publique d'ISM Chicago, avec validation de
la période et de la date. Le chiffre de septembre encore affiché avant
l'annonce ne doit jamais être envoyé comme chiffre d'octobre.

Le message privé porte la mention TEST : résultat, consensus, précédent,
écart et lecture macro conditionnelle. Un PMI mesure l'activité ; il
n'entraîne pas automatiquement un biais identique pour tous les actifs.
Aucun résultat ni consensus manquant n'est inventé. Si aucun résultat valide
n'est obtenu dans la fenêtre de trois minutes, le test signale son échec.

## Exécution et mesures

Le workflow séparé démarre à 13:35 UTC, avec un départ de secours à 13:40 UTC.
Il attend l'heure publique puis vérifie la page toutes les dix secondes,
pendant trois minutes au maximum. Il respecte les refus et la temporisation
du serveur. GitHub peut retarder ses tâches programmées : le code refuse un
départ en dehors de la fenêtre et ne capture pas un consensus après l'annonce.

L'état macro_test_state.json est distinct de celui des actualités.
L'intention d'envoi est sauvegardée dans GitHub avant l'appel Telegram.
Un envoi incertain ne fait pas l'objet d'une répétition automatique.
Les départs sont sérialisés et lisent main au démarrage.

Les rapports macro_audit mesurent l'heure prévue, le démarrage, la première
observation valide et la confirmation de l'API Telegram. Cette confirmation
n'est pas l'heure de notification sur le téléphone. La date effective de mise
en ligne n'est pas fournie par la source.

**Aucun délai inférieur à une minute n'est garanti avant cet essai réel.**
Les abonnés MNI reçoivent par ailleurs le Chicago PMI trois minutes avant
l'heure publique selon Forex Factory ; le test porte sur l'accès public gratuit.

Les secrets TELEGRAM_BOT_TOKEN et CHAT_ID sont utilisés uniquement pour
l'envoi. Aucun secret ni identifiant du destinataire n'est journalisé.
Les alertes d'actualités et cron-job.org conservent leur configuration.

## Vérification sans envoi

```bash
python -m unittest discover -s tests -v
python macro_watch.py --check --config config/macro_chicago_test.json
```

Le mode check ne lit aucun secret et n'écrit pas d'état d'envoi. Il vérifie
l'accès courant et l'extraction du communiqué, même s'il est encore ancien.
La date exacte de 2026 empêche un nouvel essai annuel.

## Sources

- [Calendrier MNI](https://www.mnimarkets.com/chicago-business-barometer-aka-chicago-pmi-publication-calendar)
- [Résultat public ISM Chicago](https://chicago.ismworld.org/news-publications/reports/research-survey/)
- [Consensus public](https://nfs.faireconomy.media/ff_calendar_thisweek.json)
- [Définition et avance abonnés](https://www.forexfactory.com/calendar/189-us-chicago-pmi)

Les communiqués ECI du BLS ont répondu HTTP403 depuis le runner le 29 octobre.
L'API BLS v1 est écartée : sa documentation mentionne un
[décalage d'un jour](https://www.bls.gov/bls/api_features.htm).
Ne pas contourner ces refus ni remplacer silencieusement les résultats par
un flux retardé. L'accès à la page PMI a été contrôlé depuis le runner ;
la vitesse de mise à jour reste à mesurer.
