# Essai macro actif

Le prochain essai est l’**ISM Manufacturing PMI d’octobre 2026**, publié
**lundi 2 novembre à 16:00 Europe/Paris / 15:00 UTC / 10:00 New York**.
Le changement d’heure américain du 1er novembre est pris en compte.

La configuration active est `config/macro_active_test.json`. L’ancienne
configuration Chicago est conservée comme historique, sans être réarmée.

**Disponibilité non validée au 30 octobre :** les deux contrôles réels depuis
GitHub ont reçu HTTP503 pour les pages ISM cible et historique. Le consensus
JSON est accessible, mais son événement de lundi n’est pas encore dans la
semaine courante. L’essai reste programmé à titre expérimental ; sa source
n’est pas annoncée comme opérationnelle. Son retour à la normale est une
condition à l’obtention d’un résultat. Aucun flux de remplacement non vérifié
n’est utilisé.

## Données et critères de réussite

- Le lecteur vérifie la page officielle du rapport d’octobre. Un rapport de
  septembre ou d’une autre année ne peut pas devenir le résultat attendu.
- La page de septembre sert uniquement au contrôle préalable de l’accès et du
  parseur. Son PMI de 54,5 n’est jamais présenté comme le résultat d’octobre.
- Le consensus et le précédent sont lus dans le JSON public Forex Factory,
  pour le titre, la devise et l’horaire exacts de l’annonce. Ils sont figés
  avant publication, puis une dernière lecture peut les rafraîchir avant T0.
- Le consensus visible le 30 octobre sur le calendrier web est 54,7. Il n’est
  pas codé comme valeur attendue : le lecteur doit prendre la valeur réellement
  présente avant l’annonce du lundi.
- Le flux JSON « this week » bascule avec la semaine. Avant que l’événement
  de lundi y figure, le contrôle indique `event_not_listed_yet` et
  `ready=false`. Cet état attendu ne valide pas le consensus.
- Le résultat, les nouvelles commandes, l’emploi et les prix payés sont lus
  séparément lorsqu’ils sont disponibles. Un sous-indice ne remplace pas le
  chiffre principal. Sans consensus propre à un sous-indice, aucun écart
  aux attentes n’est inventé.

## Déclenchement et confirmation

Le déclenchement principal passe par les exécutions du bot d’actualités
initiées par cron-job.org. Le petit répartiteur ne demande le démarrage du
lecteur séparé qu’entre T−10 minutes et T−15 secondes, pour la date exacte
configurée. Les actualités continuent indépendamment.

Un déclenchement GitHub de secours est également prévu à 14:50 et 14:55 UTC
le 2 novembre. Les exécutions du lecteur sont sérialisées et relisent main
au démarrage afin de retrouver le dernier état sauvegardé.

Après vérification de l’identité Telegram, du consensus préannonce et de la
sauvegarde distante, un message **TEST DÉMARRÉ** est prévu vers **15:50 Paris**.
Il indique le statut d’accès à la source constaté à ce moment, y compris une
indisponibilité. Ce message confirme le lancement du lecteur ; il ne garantit
pas la disponibilité du résultat et ne prétend pas que l’annonce est publiée.

Le lecteur attend 16:00 Paris puis consulte la source toutes les dix secondes,
pendant trois minutes au maximum. Les refus d’accès et Retry-After sont
respectés, y compris ceux reçus lors du contrôle de démarrage. Il transmet
ensuite un résultat confirmé ou un message
d’indisponibilité. Une donnée tardive n’est pas envoyée comme résultat rapide.

Le délai réel de mise en ligne du site n’est pas garanti. Le contrôle de
démarrage et la mesure de latence font partie de l’essai.

## État et absence de doublons

L’état `macro_test_state.json` est séparé des actualités. Le consensus et le
démarrage sont sauvegardés dans GitHub avant l’attente. Les intentions d’envoi
de la confirmation puis du résultat sont réservées avant leurs appels Telegram.

Une confirmation de démarrage incertaine n’est pas répétée ; l’observation du
résultat peut continuer. Un envoi de résultat incertain n’est pas répété.
Le test prévoit au plus une confirmation de démarrage puis un résultat
ou un avis d’échec.

La date exacte de 2026 est contrôlée : le cron ne réactive pas l’essai les
années suivantes. Aucun résultat du Chicago PMI du 30 octobre n’est rejoué.

## Message et limites de la mesure

Le message contient résultat, consensus figé, précédent, surprise, période,
heure prévue et première détection. La lecture vise uniquement EUR/USD,
GBP/USD, GER30, USD/CHF, SP500, NAS100 et US30. Un PMI mesure l’activité :
croissance, bénéfices et taux peuvent produire des effets opposés sur les
indices. Les prix payés ne deviennent pas automatiquement une surprise
d’inflation.

Les audits distinguent T0 prévu, démarrage, premier résultat valide et
confirmation de l’API Telegram. Cette confirmation n’est pas l’heure de la
notification sur le téléphone. La source ne fournit pas l’heure effective de
mise en ligne. Aucun délai inférieur à une minute n’est encore démontré.

## Couverture actuelle

Le lecteur structuré couvre les prototypes **Chicago PMI et ISM manufacturier**.
La collecte rapide autonome des **CPI, NFP et décisions FOMC n’est pas implémentée**.
Le module d’actualités peut interpréter un résultat et son consensus explicitement
rapportés dans une dépêche ; cela ne remplace pas cette collecte structurée.

Le premier essai Chicago du 30 octobre n’a jamais démarré via l’horaire GitHub.
Le raccordement à cron-job et le parseur du mot « dipped » ont ensuite été
corrigés. Aucune mesure de latence n’a été obtenue sur cette publication.

## Contrôle sans envoi

```bash
python -m unittest discover -s tests -v
python macro_watch.py --check --config config/macro_active_test.json
```

Le mode check ne lit aucun secret Telegram et n’écrit pas d’état d’envoi.
Il contrôle séparément le rapport cible, le rapport historique et le calendrier.
Les audits ne contiennent ni token ni identifiant du destinataire.

## Sources

- [Calendrier officiel ISM](https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/)
- [Rapport cible d’octobre](https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/october/)
- [Rapport historique de septembre](https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/september/)
- [Calendrier du 2 novembre](https://www.forexfactory.com/calendar?day=nov2.2026)
- [Consensus JSON public](https://nfs.faireconomy.media/ff_calendar_thisweek.json)

Les communiqués ECI du BLS avaient répondu HTTP403 depuis le runner. L’API BLS
v1 mentionne un [décalage d’un jour](https://www.bls.gov/bls/api_features.htm) ;
elle n’est pas utilisée comme résultat immédiat et aucun refus n’est contourné.
