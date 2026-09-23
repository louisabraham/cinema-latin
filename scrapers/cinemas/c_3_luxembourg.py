"""Les 3 Luxembourg — https://www.lestroisluxembourg.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='3-luxembourg',
    name='Les 3 Luxembourg',
    address='67 rue Monsieur le Prince, 75006 Paris',
    lat=48.848402,
    lon=2.340845,
    url='https://www.lestroisluxembourg.com/',
    allocine='C0095',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
