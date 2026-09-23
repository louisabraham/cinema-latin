"""Studio 28 — https://www.cinema-studio28.fr/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='studio-28',
    name='Studio 28',
    address='10 rue Tholozé, 75018 Paris',
    lat=48.886138,
    lon=2.335388,
    url='https://www.cinema-studio28.fr/',
    allocine='P0149',
    group='Ailleurs',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
