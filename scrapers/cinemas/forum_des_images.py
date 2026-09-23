"""Forum des images — https://www.forumdesimages.fr/"""

from ..common import Cinema, show

CINEMA = Cinema(
    id='forum-des-images',
    name='Forum des images',
    address='2 rue du Cinéma, 75001 Paris',
    lat=48.8625,
    lon=2.3455,
    url='https://www.forumdesimages.fr/',
    allocine='C0119',
    group='Ailleurs',
    tags=['Répertoire'],
)


def scrape() -> list[dict]:
    raise NotImplementedError
