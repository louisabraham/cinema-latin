# Ciné Latin

Prochaines séances des cinémas de répertoire et d'art et essai du Quartier Latin (et de quelques salles ailleurs dans Paris), avec résumé, notes et itinéraire.

Site : https://louisabraham.github.io/cinema-latin/

## Fonctionnement

1. `scrapers/cinemas/*.py` : un scraper par salle. Chaque module définit `CINEMA` (nom, adresse, coordonnées, code Allociné) et `scrape()`, qui renvoie une liste de séances au format standard (voir `scrapers/common.py`).
2. `scrapers/platforms/*.py` : code partagé par les salles qui utilisent le même site (Webedia, Dulac, Paris Cinéma Club…).
3. `scrapers/run.py` : lance tous les scrapers. Si le site d'une salle échoue, il prend les séances sur Allociné, puis sur les données publiées la veille. Ensuite il relie chaque film à sa fiche Allociné (résumé, affiche, réalisateur, durée) et ajoute les notes de [paris-cine.info](https://paris-cine.info) (IMDb, Letterboxd, SensCritique, Allociné, Rotten Tomatoes, Metacritic).
4. `site/` : page statique (HTML, CSS, JS sans build) qui lit `site/data/showtimes.json`.
5. `.github/workflows/scrape.yml` : tous les jours à 6 h 15, scrape et déploie sur GitHub Pages.

## Commandes

```sh
uv run python -m scrapers.run                 # tout scraper -> site/data/
uv run python -m scrapers.run --only champo   # une seule salle
uv run python -m scrapers.check champo        # tester un scraper et le comparer à Allociné
python3 -m http.server -d site 8000           # voir le site en local
```

## Format des données

`site/data/showtimes.json` :

```json
{
  "generated_at": "2026-09-23T06:15:00+02:00",
  "cinemas": [
    {
      "id": "champo",
      "name": "Le Champo",
      "address": "…",
      "lat": 48.85,
      "lon": 2.34,
      "url": "…",
      "allocine": "C0073",
      "group": "Quartier Latin",
      "source": "site",
      "count": 71
    }
  ],
  "films": {
    "a1276": {
      "title": "La Horde sauvage",
      "original_title": "The Wild Bunch",
      "year": 1969,
      "directors": ["Sam Peckinpah"],
      "duration": 145,
      "synopsis": "…",
      "poster": "…",
      "ratings": { "imdb": 7.9, "letterboxd": 4.1 },
      "links": { "allocine": "…" }
    }
  },
  "showtimes": [
    {
      "film": "a1276",
      "cinema": "christine",
      "start": "2026-09-23T13:45:00+02:00",
      "version": "VO",
      "url": "…",
      "tags": ["35mm"]
    }
  ]
}
```

`site/data/cinemas/<id>.json` contient les séances brutes de chaque salle, au format standard.

## Ajouter une salle

1. Copier un module de `scrapers/cinemas/`, remplir `CINEMA` (le code Allociné se trouve avec `https://www.allocine.fr/_/autocomplete/mobile/theater/<nom>`).
2. Écrire `scrape()`.
3. Vérifier avec `uv run python -m scrapers.check <id>`.
