# Résultats récurrents des annonces importantes

Le cron-job existant exécute le bot toutes les cinq minutes. Le répartiteur
`important_macro.py --dispatch` cherche les annonces numériques expressément
retenues dans le calendrier de la semaine, pour USD, EUR, GBP et CHF. Dans les
dix minutes précédant une publication il déclenche le lecteur séparé. Celui-ci
fige les attentes, le précédent, l’identifiant et l’horaire avant publication,
puis contrôle les résultats toutes les dix secondes pendant trois minutes.

La source gratuite est le **calendrier public Forex Factory**, identifié comme
tel dans le message ; les résultats de cette nouvelle collecte ne sont pas
présentés comme directement confirmés par les instituts officiels. Le JSON
hebdomadaire fournit le programme ; les données JSON embarquées dans la page
journalière fournissent attentes et résultats. Aucun JavaScript n’est exécuté.
Les dates epoch éliminent les ambiguïtés de fuseau du site. Un refus HTTP401/403
arrête l’accès ; les délais Retry-After sont respectés. Aucun accès payant,
compte supplémentaire ni contournement n’est utilisé.

## Publications retenues

- États-Unis : CPI et core CPI, PCE, PPI, salaires, NFP, ADP, chômage,
  inscriptions au chômage, JOLTS, PIB, ventes au détail, PMI/ISM, confiance
  des ménages et taux Fed.
- Zone euro / Allemagne : inflation, PIB, PMI et taux BCE.
- Royaume-Uni : inflation, chômage, PIB, ventes au détail, PMI et taux BoE.
- Suisse : CPI, chômage et taux BNS.

La liste exacte des intitulés est dans `RULES`, avec leurs devises autorisées.
Les discours, élections, votes et communiqués sans valeur numérique ne sont pas
convertis en résultats. Ils continuent d’être traités par le bot d’actualités.
Pétrole et obligations restent couverts par les actualités ; cette collecte
ne mesure aucun prix ou rendement de marché.

## Lecture et envoi

Les chiffres simultanés arrivent dans un seul message. Les écarts d’inflation,
de taux et d’activité ne sont pas additionnés. Le chômage est interprété dans
le sens inverse des créations d’emplois. Des composantes contradictoires donnent
une conclusion mixte sans flèche ; une comparaison incomplète n’en produit pas
non plus. Le précédent ne remplace jamais une attente absente. Les suffixes
K/M/B sont normalisés et des unités incompatibles interdisent la comparaison.
La lecture reste conditionnelle : croissance et taux peuvent agir en sens
opposés sur les indices, et USD/CHF dépend aussi des flux vers le franc.

Pour Fed/BCE/BoE/BNS, l’analyse porte sur le **taux chiffré**, sans prétendre lire
le communiqué, la trajectoire annoncée ou la conférence de presse. Une décision
conforme ne signifie donc pas que l’événement ne bougera pas les marchés.

L’état `macro_events.json`, distinct des actualités et de l’ancien essai ISM,
conserve chaque groupe. La capture est sauvegardée avant l’attente, puis une
intention d’envoi est poussée sur GitHub avant le seul POST Telegram. Un envoi
incertain n’est jamais répété. Un état armé peut reprendre sa capture initiale.
Les lecteurs sont sérialisés et relisent main après attente en file.
Sans résultat complet dans la fenêtre, un avis d’indisponibilité est envoyé.

L’heure prévue, la première détection et l’acceptation Telegram sont conservées.
La notification sur téléphone n’est pas mesurée. Le test ISM a montré33secondes,
mais le calendrier public, cron-job et les files GitHub ne garantissent pas
ce délai pour les autres événements. Une exécution démarrée trop tard sans
capture préannonce ne fabrique pas de comparaison a posteriori.

## Vérification sans message

`python important_macro.py --check` vérifie les programmes et identifiants des
annonces futures de la semaine, sans secret, Telegram ni changement d’état.
`python -m unittest discover -s tests -v` teste la sélection, les unités,
les comparaisons contradictoires, les captures figées et les réservations.

## Vérification des 3 et 4 novembre 2026

- JOLTS du 3 novembre : 7,52 M contre 7,15 M attendu, précédent7,08 M.
  Publication prévue16:00 Paris, détection16:00:20,552 et acceptation Telegram
  16:00:22,509 (+22,509 s). Le secours n’a pas renvoyé le résultat.
- Inflation zone euro du 4 novembre : 4,0 % et sous-jacente2,5 %, toutes deux
  conformes aux attentes. Détection11:00:30,525 Paris. Les journaux du run
  41810255613 confirment l’acceptation Telegram avant11:00:40,736 ; l’heure
  d’acceptation exacte n’a pas été conservée dans GitHub, car la sauvegarde
  finale a échoué après le POST. L’état distant est donc resté `send_pending`.
  Aucun second envoi n’a eu lieu.

La sauvegarde distante réessaie maintenant la synchronisation Git en cas de
concurrence avec les autres tâches, sans rejouer le POST Telegram. La confirmation
horodatée est écrite immédiatement dans les journaux et l’état local est conservé
en artefact, y compris après un échec de sauvegarde finale. Ces mesures donnent
une preuve d’envoi exploitable sans inventer une heure pour un événement passé.
