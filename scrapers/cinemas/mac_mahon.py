"""Mac-Mahon — https://www.cinemamacmahon1938.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='mac-mahon',
    name='Mac-Mahon',
    address='5 avenue Mac-Mahon, 75017 Paris',
    lat=48.875543,
    lon=2.294491,
    url='https://www.cinemamacmahon1938.com/',
    allocine='C0172',
    group='Ailleurs',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
