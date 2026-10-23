# fundamental-news-bot

Bot Telegram de news fondamentales pour le trading.

## Ce que fait le bot

- Récupère des news via RSS BBC.
- Peut utiliser NewsAPI si `USE_NEWSAPI=1`.
- Sélectionne les événements macro/géo/énergie concrets à partir du titre et du résumé.
- Attribue une priorité à l'événement reconnu, sans additionner des mots-clés.
- Envoie une alerte Telegram avec les actifs à surveiller.
- Traduit les titres anglais en français via DeepL.

## Sélection des alertes

Le titre doit contenir un événement identifiable : décision de taux, publication
macroéconomique, orientation monétaire explicite, décision de production OPEP,
interruption ou reprise d'un approvisionnement stratégique, sanctions ou tarifs
douaniers, accord ou rupture de cessez-le-feu, attaque stratégique, mouvement
explicite d'un marché de référence.

Les témoignages individuels, difficultés de chauffage, faits divers, déclarations
générales de préparation à une crise et scénarios hypothétiques sont rejetés.
La présence d'Iran, de pétrole ou de missiles dans le résumé ne les réhabilite pas.
Les mots sont reconnus entièrement : `war` ne correspond plus à `award`, ni `gas`
à `Gaza`. Les règles s'appliquent aux titres anglais, avant traduction.

Version `pertinence-v2.1` : une pollution côtière ou une collision de pétrolier ne
suffit pas à déclencher une alerte. Il faut un effet explicite sur un flux, une
infrastructure stratégique ou un marché. Une plage fermée près d'un terminal
pétrolier ne signifie pas que le terminal est fermé. Le verbe `hits` ne suffit
plus à identifier une attaque militaire ; son caractère offensif doit être
présent dans le titre, sans être inventé à partir du résumé.

Les publications macro doivent concerner une économie de référence identifiable
dans le titre ou le résumé (États-Unis, Royaume-Uni, zone euro et principales
économies européennes, Chine, Japon, Canada, Australie, Nouvelle-Zélande, Suisse,
Inde). Les indicateurs américains spécifiques comme le PCE ou les NFP sont
reconnus sans nom de pays. Les statistiques locales des îles, comtés et conseils
locaux sont rejetées même si elles sont comparées à l'inflation britannique.

Exemples :

| Titre | Décision |
| --- | --- |
| UK needs to be ready for emergencies and hostile acts, warns Streeting | Rejeté |
| Woman 'scared to turn heating on' due to oil cost | Rejeté |
| Fed expected to cut interest rates | Rejeté : anticipation |
| Fed cuts interest rates | Retenu : décision de taux |
| Iran and Israel agree ceasefire | Retenu : accord de cessez-le-feu |
| Russia halts gas exports to Europe | Retenu : approvisionnement |
| Oil spill hits UAE beaches after tanker collision | Rejeté : pollution locale |
| Oil spill halts oil exports from UAE | Retenu : interruption des exportations |

Priorités : 9 pour les décisions monétaires, événements stratégiques et accords
de cessez-le-feu ; 8 pour les données macro et décisions commerciales ; 7 pour
l'orientation monétaire ; 6 pour les mouvements de marché. Un rejet vaut 0.
`MIN_SCORE_SEND` reste le seuil final. Ces scores expriment une priorité de règle,
pas une mesure de réaction du marché.

Chaque décision est expliquée dans les logs (`Motif`). La limite
`MAX_ARTICLES_PER_RUN` s'applique après le filtrage des articles non pertinents
et des URL déjà envoyées. Le format de `state.json` reste compatible.
Le début du run affiche aussi `Version du filtre : pertinence-v2.1` et le chemin
du fichier importé, pour vérifier quelle copie s'exécute réellement.

Ce filtre privilégie la précision : une annonce importante formulée autrement
peut être écartée. Il ne lit pas l'article complet et ne vérifie pas la fraîcheur
de l'événement. Les impacts directionnels de `mapping.py` restent des associations
génériques ; cette modification ne les transforme pas en analyse du sens de la nouvelle.

## Vérification locale

Après installation des dépendances, lancer :

```bash
python -m unittest discover -s tests -v
```

Les tests couvrent les deux exemples rejetés, les faux positifs de mots-clés,
les annonces à conserver et le parcours de sélection jusqu'à l'envoi simulé.
Ils n'appellent ni Telegram, ni DeepL, ni les sources d'actualités et ne modifient
pas l'état réel.

## Mise à jour d'une installation existante

Remplacer ensemble `bot.py`, `filter.py`, `scoring.py` et `mapping.py`.
Conserver le `state.json` de l'installation ainsi que ses variables d'environnement.
L'archive de mise à jour ne contient ni historique à restaurer, ni clés API.
Les dépendances et la commande de lancement restent identiques.

## Cache DeepL

Cette version contient une vraie mémoire de traduction dans `state.json`.

Structure :

```json
{
  "seen": [],
  "translations": {
    "english title normalized": "Titre traduit en français"
  }
}
```

Fonctionnement :

1. Le bot vérifie d'abord si le titre existe déjà dans `state["translations"]`.
2. Si oui, il réutilise la traduction sans appeler DeepL.
3. Si non, il appelle DeepL une seule fois.
4. Il sauvegarde ensuite la traduction dans `state.json`.

Important : si aucune clé DeepL n'est configurée, le bot ne sauvegarde pas le titre original dans le cache. Cela évite de bloquer les futures traductions après ajout de la clé API.

## Variables d'environnement nécessaires

```bash
BOT_TOKEN=...
CHAT_ID=...
DEEPL_API_KEY=...
```

Optionnel :

```bash
MIN_SCORE_SEND=5
MAX_ARTICLES_PER_RUN=60
USE_NEWSAPI=0
NEWSAPI_KEY=...
```

## Secrets GitHub Actions

Dans ce dépôt, créer le secret de dépôt `TELEGRAM_BOT_TOKEN` avec le token
actuel de BotFather, ainsi que `CHAT_ID` et `DEEPL_API_KEY`. Les workflows
transmettent `TELEGRAM_BOT_TOKEN` à Python sous le nom d'environnement
`BOT_TOKEN` ; le lancement local conserve donc ses variables habituelles.
Le secret de dépôt historique `BOT_TOKEN` n'est plus utilisé par les workflows.

Le jeton GitHub placé dans l'en-tête `Authorization` de cron-job sert uniquement
à déclencher le workflow `news-bot.yml` avec `{"ref":"main"}`. Il est distinct
du token Telegram et n'a pas à être remplacé lors d'une rotation dans BotFather.

## Lancement

```bash
python bot.py
```

Chaque lancement vérifie la variable `BOT_TOKEN` avec la méthode Telegram `getMe`,
même si aucun article n'est envoyé. Le log `Telegram authentifié : @...` permet
de confirmer le bot associé au token, sans afficher le secret ni envoyer de
message de test. Un refus de Telegram interrompt le run avant la collecte.
Après une rotation dans BotFather, remplacer le secret `TELEGRAM_BOT_TOKEN` dans GitHub
Actions pour les tâches qui exécutent ce workflow, même si leur déclenchement
est assuré par cron-job.
Le workflow de tests effectue aussi ce contrôle en lecture seule après un push
sur `main` ; les pull requests exécutent uniquement les tests simulés.
Les espaces en début et fin du secret sont retirés. Le contrôle distingue un
secret vide, un format incompatible et un refus d'authentification par Telegram,
sans afficher la valeur du secret ni l'URL d'authentification.
