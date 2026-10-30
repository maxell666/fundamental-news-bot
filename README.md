# Fundamental News Bot

Actualités sélectionnées pour EUR/USD, GBP/USD, GER30, USD/CHF, SP500, NAS100 et
US30, traduites en français et envoyées sur Telegram. Version de sélection :
**pertinence-v3.2-portefeuille**.

La sélection exige un lien économique identifié avec ce portefeuille. Le pétrole
et les Treasuries américains sont des moteurs d'analyse, sans ajout d'actifs
à trader. Les [règles de transmission et le format Telegram](docs/portefeuille.md)
expliquent les exclusions, les directions conditionnelles et leurs limites.

## Sources

La collecte utilise des flux publics sans nouvelle clé API :

- Reuters via Google News : agrégation explicitement identifiée, avec contrôle du
  nom et du domaine de l'éditeur. Ce n'est pas un abonnement au flux professionnel Reuters.
- InvestingLive : actualités et banques centrales.
- Investing.com : marchés actions, matières premières, économie et résultats.
- CNBC Top News.
- The Guardian Business.
- BBC Business et BBC World en complément.

Le flux BBC Politics a été retiré. Le flux CNBC Market Insider, dont le relevé
réel était figé, a été remplacé. Chaque source est contrôlée séparément :
réponse HTTP, RSS exploitable, nombre d'articles, dates et dernière publication.
Les requêtes ont un délai maximal, une taille bornée et une concurrence limitée.
Une panne partielle laisse les autres sources fonctionner ; une collecte
entièrement vide échoue explicitement.

Les flux ont été vérifiés depuis le runner GitHub utilisé pour les alertes.
L'outil reproductible est :

```bash
python scripts/check_sources.py --max-items 50
```

## Sélection

Le filtre reconnaît des mécanismes de marché :

- décisions de taux, statistiques des économies de référence et indications
  officielles des banques centrales ;
- décisions fiscales, budgétaires et commerciales de portée nationale ;
- résultats, perspectives et mouvements importants de grandes sociétés cotées ;
- acquisitions ou fusions majeures annoncées ;
- ruptures/reprises d'approvisionnement et événements géopolitiques stratégiques ;
- mouvements explicites des indices, devises, taux, de l'or et du pétrole.

Le titre doit porter l'annonce. Le résumé peut préciser l'acteur, le montant,
la portée nationale ou le mécanisme financier. Un témoignage sur le chauffage,
une compétition sportive ou un rappel d'invasion passé ne devient pas une
alerte parce que son résumé mentionne la guerre.

Une déclaration officielle de banque centrale peut être pertinente avec
« could/may ». Un pari d'analyste, une probabilité implicite de hausse de taux
ou des négociations sans décision ne sont pas traités comme une décision effective.
Les petites sanctions sans portée commerciale/financière explicite, les faits
divers et les commentaires politiques généraux restent écartés.

Les scores indiquent une priorité de sélection, pas une prévision de gain ni
une probabilité de mouvement. Le seuil par défaut reste 5. Les catégories
sont MACRO, FISCAL, TRADE, EQUITIES, ENERGY, GEO et MARKET.

La portée est décidée dans portfolio.py et la lecture dans mapping.py.
Une annonce sans lien argumenté ne consomme pas de place dans le lot envoyé.
Les messages regroupent les actifs concernés autour de mécanismes concrets ;
le biais global, le score et la liste d'actifs répétitive ont été retirés.
Les scores restent internes au classement. La date est affichée en heure de Paris.
Les messages d'actualités utilisent HTML avec textes et liens échappés ;
le test macro séparé conserve son texte simple.

## Fraîcheur et doublons

Par défaut, seules les publications datées de moins de 24 heures sont envoyées.
Les dates manquantes, trop anciennes ou incohérentes restent visibles dans
l'audit. Aucun horodatage de publication n'est inventé.

Les URL de suivi sont normalisées. Les titres identiques présents chez plusieurs
fournisseurs sont regroupés ; leur dédoublonnage persistant expire après 24 heures,
pour laisser passer une nouvelle annonce ultérieure au même intitulé.
Les décisions de taux, publications de PIB et acquisitions explicitement
identifiables sont aussi rapprochées de façon conservatrice. Des actions ou
valeurs contradictoires ne sont pas fusionnées.

L'historique conserve les URL déjà envoyées, le cache de traduction, les titres
récents et les événements récemment confirmés. Un article n'est marqué envoyé
qu'après confirmation de Telegram. L'état est sauvegardé après chaque envoi ;
les traitements automatiques sont sérialisés.

La limite par défaut est **10 alertes par passage**, après tri et dédoublonnage.
Les autres candidats restent à examiner au passage suivant ; ils ne sont pas
marqués envoyés. L'activation de nouvelles sources peut donc rattraper des
informations récentes sans réexpédier plusieurs jours d'archives.

## Audit reproductible

Chaque passage produit :

- audit/news_audit.json : décision détaillée pour chaque article ;
- audit/news_audit.csv : tableau des décisions, catégories, scores et motifs ;
- audit/source_health.json : état de chaque fournisseur.

Les rapports sont conservés sept jours comme artefacts GitHub Actions. Les
décisions distinguent notamment envoyé, déjà envoyé, doublon, rejet du filtre,
hors portefeuille, lecture inexploitable, publication ancienne/non datée et
attente de la limite d'envoi. Chaque ligne expose les actifs, moteurs et raisons
de portée, ainsi que la lecture préparée avant envoi. Le résumé
ne confond donc plus panne d'une source et absence d'article retenu.

Le workflow **Audit des sources et du tri** effectue une collecte et un rejeu
sans token Telegram, sans DeepL et sans modification de l'historique :

```bash
python scripts/check_sources.py
python bot.py --dry-run --replay audit/source_check.json
python scripts/validate_audit.py --require-candidates
```

Un rejeu de fichier exige le mode dry-run. Une simulation ne doit jamais envoyer
de message ou enregistrer des articles comme envoyés. La validation exige au
moins deux sources de marchés récemment mises à jour et, avec l'option indiquée,
au moins une actualité pertinente dans l'échantillon.

Le filtre reste une analyse déterministe des titres et résumés RSS, sans lecture
systématique de l'article entier. Les audits servent à contrôler ses rejets
et à ajouter des cas réels aux tests. Il n'existe pas de quota artificiel
d'alertes à remplir chaque jour.

## Configuration

Créer ces secrets Actions dans le dépôt :

- TELEGRAM_BOT_TOKEN : token actuel fourni par le BotFather officiel.
- CHAT_ID : destinataire des alertes.
- DEEPL_API_KEY : traduction des titres.

Les workflows transmettent TELEGRAM_BOT_TOKEN à Python sous la variable BOT_TOKEN.
L'ancien secret GitHub BOT_TOKEN n'est plus utilisé. Après rotation dans BotFather,
mettre à jour TELEGRAM_BOT_TOKEN.

Le jeton placé dans l'en-tête Authorization de cron-job est un **jeton GitHub** :
il déclenche news-bot.yml avec le corps {"ref":"main"}. Il est distinct du token
Telegram et reste inchangé lors d'une rotation du token Telegram.

Variables locales :

```bash
BOT_TOKEN=...
CHAT_ID=...
DEEPL_API_KEY=...

# Valeurs par défaut
MIN_SCORE_SEND=5
MAX_ARTICLES_PER_RUN=10
MAX_NEWS_AGE_HOURS=24
MAX_ITEMS_PER_SOURCE=50
ALLOW_UNDATED_NEWS=0
USE_NEWSAPI=0
NEWS_DRY_RUN=0
```

NewsAPI reste facultatif et désactivé par défaut ; sa clé est envoyée dans
un en-tête, sans journalisation d'une URL contenant la clé. Le module
d'actualités ne nécessite aucun abonnement de calendrier économique.

Un [essai macro séparé](docs/macro-test.md) compare le résultat public du
Chicago PMI du 30 octobre 2026 au consensus enregistré avant sa publication.
Il mesure le délai de détection et de confirmation Telegram, sans garantie
préalable de latence ni modification du filtre d'actualités.

## Installation et tests

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python bot.py
```

Les tests unitaires simulent le réseau, Telegram et DeepL. Ils couvrent les
exemples indésirables reçus, les annonces financières retrouvées, la guidance,
les vrais rejets observés, la collecte, la fraîcheur, les doublons, l'audit et
la reprise d'un lot interrompu.

Le lancement réel vérifie getMe, puis sendMessage pour les articles sélectionnés.
Les journaux ne contiennent ni token, ni empreinte de token, ni réponse privée
du destinataire. Le cache DeepL est réutilisé ; une absence de clé ne bloque
pas le cache avec le titre anglais.
