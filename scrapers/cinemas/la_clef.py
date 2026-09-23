"""La Clef — https://laclefrevival.org/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='la-clef',
    name='La Clef',
    address='34 rue Daubenton, 75005 Paris',
    lat=48.841161,
    lon=2.352431,
    url='https://laclefrevival.org/',
    allocine='C0170',
    group='Quartier Latin',
    tags=['Associatif'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
