from blog.posts import Post


def test_post_url():
    assert Post("first").url == "/posts/first/"
