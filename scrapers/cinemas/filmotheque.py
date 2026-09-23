"""La Filmothèque du Quartier Latin — https://lafilmotheque.fr/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='filmotheque',
    name='La Filmothèque du Quartier Latin',
    address='9 rue Champollion, 75005 Paris',
    lat=48.849578,
    lon=2.342814,
    url='https://lafilmotheque.fr/',
    allocine='C0020',
    group='Quartier Latin',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
