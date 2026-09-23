"""Studio des Ursulines — https://www.studiodesursulines.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='ursulines',
    name='Studio des Ursulines',
    address='10 rue des Ursulines, 75005 Paris',
    lat=48.842722,
    lon=2.342033,
    url='https://www.studiodesursulines.com/',
    allocine='C0083',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
