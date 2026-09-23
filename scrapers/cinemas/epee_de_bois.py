"""L'Épée de Bois — https://www.cine-epeedebois.fr/"""

from ..common import Cinema
from ..platforms import webedia

CINEMA = Cinema(
    id='epee-de-bois',
    name="L'Épée de Bois",
    address='100 rue Mouffetard, 75005 Paris',
    lat=48.841304,
    lon=2.349569,
    url='https://www.cine-epeedebois.fr/',
    allocine='W7504',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    return webedia.scrape(CINEMA.id, CINEMA.url, CINEMA.allocine)
