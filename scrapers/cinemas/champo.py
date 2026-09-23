"""Le Champo — https://cinema-lechampo.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='champo',
    name='Le Champo',
    address='51 rue des Écoles, 75005 Paris',
    lat=48.849989,
    lon=2.343227,
    url='https://cinema-lechampo.com/',
    allocine='C0073',
    group='Quartier Latin',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
