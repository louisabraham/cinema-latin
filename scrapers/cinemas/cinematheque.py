"""La Cinémathèque française — https://www.cinematheque.fr/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='cinematheque',
    name='La Cinémathèque française',
    address='51 rue de Bercy, 75012 Paris',
    lat=48.836826,
    lon=2.382384,
    url='https://www.cinematheque.fr/',
    allocine='C1559',
    group='Ailleurs',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
