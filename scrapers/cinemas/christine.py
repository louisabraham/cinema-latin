"""Christine Cinéma Club — https://pariscinemaclub.com/christine-cinema-club/"""

from ..common import Cinema
from ..platforms import pariscinemaclub

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
    # schedule from the Cotecine booking site, metadata from pariscinemaclub.com
    return pariscinemaclub.scrape(CINEMA.id, sub='christinecinemaclub', wp_cinema=28)
