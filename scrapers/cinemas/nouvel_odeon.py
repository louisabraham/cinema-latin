"""Nouvel Odéon — https://www.nouvelodeon.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='nouvel-odeon',
    name='Nouvel Odéon',
    address="6 rue de l'École de Médecine, 75006 Paris",
    lat=48.850808,
    lon=2.34178,
    url='https://www.nouvelodeon.com/',
    allocine='C0041',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
