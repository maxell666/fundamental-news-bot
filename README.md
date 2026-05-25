# fundamental-news-bot

Bot Telegram de news fondamentales pour le trading.

## Ce que fait le bot

- Récupère des news via RSS BBC.
- Peut utiliser NewsAPI si `USE_NEWSAPI=1`.
- Filtre les news macro/géo/énergie importantes.
- Calcule un score d'importance.
- Envoie une alerte Telegram avec les actifs à surveiller.
- Traduit les titres anglais en français via DeepL.

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

## Lancement

```bash
python bot.py
```
