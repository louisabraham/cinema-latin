"""Espace Saint-Michel — https://espacesaintmichel.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='espace-saint-michel',
    name='Espace Saint-Michel',
    address='7 place Saint-Michel, 75005 Paris',
    lat=48.853066,
    lon=2.344186,
    url='https://espacesaintmichel.com/',
    allocine='C0117',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
