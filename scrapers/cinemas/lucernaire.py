"""Le Lucernaire — https://www.lucernaire.fr/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='lucernaire',
    name='Le Lucernaire',
    address='53 rue Notre-Dame des Champs, 75006 Paris',
    lat=48.844259,
    lon=2.33046,
    url='https://www.lucernaire.fr/',
    allocine='C0093',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
