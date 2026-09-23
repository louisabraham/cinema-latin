"""Le Grand Action — https://www.legrandaction.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='grand-action',
    name='Le Grand Action',
    address='5 rue des Écoles, 75005 Paris',
    lat=48.847521,
    lon=2.352127,
    url='https://www.legrandaction.com/',
    allocine='C0072',
    group='Quartier Latin',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
