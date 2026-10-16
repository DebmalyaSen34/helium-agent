import pytest

from blog.posts import Post
from blog.text import slugify


@pytest.mark.parametrize("title, slug", [
    ("Hello,  World!", "hello-world"),
    ("Crème Brûlée", "creme-brulee"),
    ("  --a--b--  ", "a-b"),
    ("Python 3.12 is out", "python-3-12-is-out"),
    ("ALL CAPS", "all-caps"),
    ("", ""),
    ("!!!", ""),
    ("naïve café", "naive-cafe"),
])
def test_slugify(title, slug):
    assert slugify(title) == slug


def test_post_url_uses_clean_slug():
    assert Post("What's new?").url == "/posts/what-s-new/"
