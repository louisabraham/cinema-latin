"""Le Louxor — https://www.cinemalouxor.fr/"""

from ..common import Cinema
from ..platforms import webedia

CINEMA = Cinema(
    id='louxor',
    name='Le Louxor',
    address='170 boulevard de Magenta, 75010 Paris',
    lat=48.883475,
    lon=2.349847,
    url='https://www.cinemalouxor.fr/',
    allocine='W7510',
    group='Ailleurs',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    return webedia.scrape(CINEMA.id, CINEMA.url, CINEMA.allocine)
