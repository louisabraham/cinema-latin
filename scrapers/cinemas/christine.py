"""Christine Cinéma Club — https://pariscinemaclub.com/christine-cinema-club/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='christine',
    name='Christine Cinéma Club',
    address='4 rue Christine, 75006 Paris',
    lat=48.854495,
    lon=2.340174,
    url='https://pariscinemaclub.com/christine-cinema-club/',
    allocine='C0015',
    group='Quartier Latin',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
