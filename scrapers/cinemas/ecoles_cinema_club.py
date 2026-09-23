"""Écoles Cinéma Club — https://pariscinemaclub.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='ecoles-cinema-club',
    name='Écoles Cinéma Club',
    address='23 rue des Écoles, 75005 Paris',
    lat=48.848362,
    lon=2.348977,
    url='https://pariscinemaclub.com/',
    allocine='C0071',
    group='Quartier Latin',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
