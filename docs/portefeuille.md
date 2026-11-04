# Périmètre et lecture des alertes

Instruments suivis : **EUR/USD, GBP/USD, GER30, USD/CHF, SP500, NAS100, US30**.
Les identifiants internes sont EURUSD, GBPUSD, GER30, USDCHF, SP500, NAS100, US30.
GER30 conserve le nom du symbole fourni par l'utilisateur ; la référence
économique est le DAX, qui compte désormais quarante sociétés.

## Sélection

Le filtre fondamental identifie une annonce effective, puis portfolio.py
identifie son lien avec les instruments suivis. Aucun pays, secteur ou nom
de société inconnu n'est rattaché automatiquement au SP500.

| Événement | Canal retenu |
| --- | --- |
| Décision Fed | Dollar, coût mondial du capital et indices |
| Chiffres américains majeurs | Anticipations de taux USD, croissance et bénéfices des sociétés US |
| BCE, statistiques agrégées de la zone euro et allemandes | Euro, financement et perspectives des entreprises du GER30 |
| BoE, statistiques britanniques majeures | Livre et différentiel de taux avec les États-Unis |
| BNS, statistiques suisses majeures | Franc et différentiel de taux USD/CHF |
| Treasuries, notamment rendement et prix du 10 ans | Actualisation des bénéfices, coût du capital et taux relatifs |
| Rupture d'offre pétrolière, restrictions, stocks ou mouvement important | Coûts énergétiques, marges, inflation et facture d'importation |
| Résultats ou guidance des grandes composantes reconnues | Contribution bénéficiaire et poids de la société dans les seuls indices concernés |
| Choc mondial avéré | Prime de risque, financement, logistique et flux refuges |

Le Canada, l'Australie, la Nouvelle-Zélande ou les commentaires japonais
courants ne sont pas retenus pour leur seule portée nationale. Une décision
commerciale visant les entreprises américaines reste pertinente, quelle que
soit l'origine du décideur. Une surprise japonaise avec transmission financière
mondiale peut aussi rester pertinente. Un mouvement limité à l'or est écarté.
Le résumé d'un PIB canadien mentionnant la Fed ne transforme pas ce PIB en
annonce américaine.

Les résultats d'une petite société ne suffisent pas : la couverture des indices
est un noyau curaté et certaines composantes secondaires exigent un événement
exceptionnel. Les appartenances sont explicites, sans poids supposé : Intel
n'est plus rattaché au US30, et une société du SP500 n'est pas automatiquement
une composante du NAS100. La composition doit être revue lors des changements
officiels d'indices.

## Directions et faits

- Une variation de rendement et une variation de prix obligataire ont des sens
  opposés. La variation du 2 ans ne devient pas celle du 10 ans.
- Une hausse du 10 ans US peut peser sur les valorisations ; elle ne prouve ni
  une hausse effective du dollar ni un changement du taux directeur de la Fed.
- Une surprise d'inflation exige une comparaison au consensus du même chiffre.
  Le précédent, un chiffre britannique, un résultat d'entreprise ou une unité
  différente ne remplacent pas le consensus américain.
- Des composantes, des résultats et une guidance contradictoires imposent une
  lecture contrastée. Un meilleur PIB peut soutenir les bénéfices et relever
  les taux attendus : les deux effets ne sont pas fusionnés en une flèche.
- Une décision annoncée de la BCE, de la BoE ou de la BNS est reliée à la bonne
  devise. Une décision de la Fed citée dans une autre proposition ne lui est
  pas attribuée.
- Une variation explicitement observée d'une paire ne démontre pas celle des
  autres paires. USD/CHF peut être affecté par deux devises refuges.

La lecture reste conditionnelle aux attentes déjà intégrées dans les cours et
aux autres données de l'annonce. Elle utilise les faits disponibles dans les
titres et résumés RSS ; elle ne consulte pas systématiquement l'article complet
et ne dispose pas d'un flux de prix temps réel. Le prototype de capture d'un
résultat officiel est un module séparé ; ce changement ne valide pas sa latence.

## Message Telegram et audit

Le message contient le titre traduit, les mécanismes utiles regroupés par
instruments, l'heure de Paris et un lien lisible vers la source. Il ne contient
plus de Bias « À confirmer », de score opaque ou de deuxième liste répétant les
actifs. Aucun instrument extérieur au portefeuille ne peut être ajouté par le
mapping. Pétrole et US10Y sont décrits comme des moteurs, pas comme des positions.

Les lectures sont préparées avant classement et dédoublonnage. Un mapping vide
ou extérieur aux actifs autorisés est bloqué avant traduction et envoi.
L'audit JSON/CSV conserve portefeuille, moteurs, motifs de rejet et textes
d'impact. Un rejeu de l'historique reste possible sans Telegram ni DeepL.

## Références

- [Transmission et effets internationaux de la politique Fed](https://www.federalreserve.gov/econres/notes/feds-notes/international-spillovers-of-tighter-monetary-policy-20221222.html)
- [Transmission monétaire — Banque d'Angleterre](https://www.bankofengland.co.uk/quarterly-bulletin/2024/2024/about-a-rate-of-general-interest-how-monetary-policy-transmits)
- [Taux américains et prime de terme — New York Fed](https://www.newyorkfed.org/research/data_indicators/term-premia-tabs)
- [DAX — STOXX](https://stoxx.com/index/daxnr/)

## Reprises des résultats d’entreprise

Les reprises sont regroupées par entreprise et sujet pendant 24 heures glissantes,
y compris au changement de date. La règle couvre Apple et les grandes sociétés
technologiques explicitement reconnues dans `company_stories.py`.

Un article sur les résultats, une nouvelle prévision de marge/chiffre d’affaires
et une réaction de l’action sont des sujets distincts. Les titres reformulant
le même sujet ne donnent pas de nouvel envoi. Une correction explicite, un autre
trimestre, une prévision chiffrée modifiée, un sens de réaction opposé ou un
nouveau palier de variation de l’action (5/10/20/30 %) restent séparés.
Un pourcentage de marge ne devient pas un pourcentage de mouvement de l’action.
Les acquisitions, sanctions, rappels de produits et nouvelles de direction ne
sont pas bloqués par ce regroupement. Un titre multi-entreprises passe encore
si une entreprise apporte une information non couverte.

Les simples aperçus avant résultats sont écartés. Une entreprise qui annonce
une baisse de prévisions avant ses résultats reste une annonce effective.
La comparaison est déterministe et limitée aux faits reconnus dans les titres ;
un nouveau fait présent seulement dans le résumé peut échapper à cette lecture.

L’audit distingue `duplicate_company_story` des articles identiques par URL.
Les signatures sont inscrites dans `seen_events` après confirmation Telegram.
Lors de l’installation, seuls les titres déjà confirmés dans `seen_titles`
peuvent initialiser cet historique à partir du cache de traduction, avec leur
heure d’envoi d’origine. Le cache seul ne prouve pas qu’un message a été envoyé.
Aucun titre rejeté ou en attente de quota n’est marqué comme envoyé.

Le rejeu des huit titres Apple envoyés les 2 et 3 novembre 2026 garde trois
messages : résultats supérieurs aux attentes, baisse prévue des marges et
réaction boursière. Il enlève un aperçu et quatre reprises. Ce n’est pas une
limite fixe de trois alertes par entreprise.

## Reprises d’une publication d’inflation

Les titres décrivant le même chiffre d’inflation sont rapprochés pendant 24 heures
par économie et métrique : inflation totale ou sous-jacente, variation mensuelle
ou annuelle, période nommée, estimation préliminaire ou résultat final lorsque
ces précisions sont présentes. Une valeur différente reste une information
nouvelle. Une révision sans nouveau chiffre explicite reste visible.

Les trois titres « Euro zone inflation rises to three-year high »,
« Euro zone inflation hits 4% for first time in three years as interest rate hike
looms » et « Eurozone inflation hits 4% for first time since 2023, piling pressure
on ECB » représentent une seule publication. Une analyse de sondage ou
anticipations, une nouvelle décision/commentaire de banque centrale et une
réaction explicite de marché restent séparés.

Les titres historiquement confirmés initialisent ce rapprochement au déploiement.
Un résultat CPI du lecteur structuré peut aussi éviter les reprises RSS, uniquement
si son envoi Telegram est confirmé dans l’état. Une intention d’envoi en attente
ou incertaine n’est pas assimilée à une livraison réussie.
