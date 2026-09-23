"""Saint-André des Arts — https://cinemasaintandre.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='saint-andre-des-arts',
    name='Saint-André des Arts',
    address='30 rue Saint-André des Arts, 75006 Paris',
    lat=48.853354,
    lon=2.342121,
    url='https://cinemasaintandre.com/',
    allocine='C0100',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
