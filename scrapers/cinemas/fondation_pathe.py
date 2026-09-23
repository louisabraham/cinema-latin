"""Fondation Jérôme Seydoux-Pathé — https://www.fondation-jeromeseydoux-pathe.com/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='fondation-pathe',
    name='Fondation Jérôme Seydoux-Pathé',
    address='73 avenue des Gobelins, 75013 Paris',
    lat=48.833378,
    lon=2.354526,
    url='https://www.fondation-jeromeseydoux-pathe.com/',
    allocine='W7513',
    group='Ailleurs',
    tags=['Muet', 'Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
