from wordcount.counting import count_words


def test_count_words_is_case_insensitive():
    assert count_words("The the THE cat")["the"] == 3
