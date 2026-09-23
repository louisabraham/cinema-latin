"""Reflet Médicis — https://www.dulaccinemas.com/cinema/reflet-medicis/2950"""

from ..common import Cinema
from ..platforms import dulac

CINEMA = Cinema(
    id='reflet-medicis',
    name='Reflet Médicis',
    address='3 rue Champollion, 75005 Paris',
    lat=48.849751,
    lon=2.343025,
    url='https://www.dulaccinemas.com/cinema/reflet-medicis/2950',
    allocine='C0074',
    group='Quartier Latin',
    tags=['Art et essai'],
)


def scrape() -> list[dict]:
    return dulac.scrape(CINEMA.id, 'Reflet Medicis')
