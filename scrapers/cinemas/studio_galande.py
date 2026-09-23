"""Studio Galande — http://www.studiogalande.fr/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='studio-galande',
    name='Studio Galande',
    address='42 rue Galande, 75005 Paris',
    lat=48.851634,
    lon=2.347107,
    url='http://www.studiogalande.fr/',
    allocine='C0016',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
