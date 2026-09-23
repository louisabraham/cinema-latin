"""L'Arlequin — https://www.dulaccinemas.com/cinema/l-arlequin"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='arlequin',
    name="L'Arlequin",
    address='76 rue de Rennes, 75006 Paris',
    lat=48.851193,
    lon=2.330405,
    url='https://www.dulaccinemas.com/cinema/l-arlequin',
    allocine='C0054',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
