from dataclasses import dataclass, field

from blog.text import slugify


@dataclass
class Post:
    title: str
    body: str = ""
    slug: str = field(init=False)

    def __post_init__(self):
        self.slug = slugify(self.title)

    @property
    def url(self) -> str:
        return f"/posts/{self.slug}/"
