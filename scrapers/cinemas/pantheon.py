"""Cinéma du Panthéon — https://www.cinemadupantheon.fr/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='pantheon',
    name='Cinéma du Panthéon',
    address='13 rue Victor Cousin, 75005 Paris',
    lat=48.847467,
    lon=2.342464,
    url='https://www.cinemadupantheon.fr/',
    allocine='C0076',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
