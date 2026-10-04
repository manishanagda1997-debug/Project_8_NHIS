import pandas as pd
import pytest

from job_market.text import STOP_WORDS, count_ngrams, ngrams, tokenize, top_ngrams


def test_empty_string_has_no_tokens():
    assert tokenize("") == []
    assert tokenize(None) == []


def test_stop_words_are_removed():
    assert "for" in STOP_WORDS
    assert tokenize("looking for the data analyst") == ["data", "analyst"]


def test_top_bigrams_count_adjacent_tokens_after_stop_words():
    titles = pd.Series(["data analyst data analyst", "data analyst for dashboard"])
    result = top_ngrams(titles, n=2, k=2)
    assert result.iloc[0].to_dict() == {"term": "data analyst", "count": 3}


def test_non_latin_words_are_kept():
    assert tokenize("разработчик python") == ["разработчик", "python"]


def test_invalid_ngram_arguments_fail_clearly():
    with pytest.raises(ValueError, match="n"):
        top_ngrams(pd.Series(["data"]), n=0)
    with pytest.raises(ValueError, match="k"):
        top_ngrams(pd.Series(["data"]), k=0)


def test_phrases_never_jump_over_a_removed_stop_word():
    # "developer wordpress" was never written; it must not be counted.
    phrases = list(ngrams("web developer needed for wordpress", 2))
    assert phrases == ["web developer"]
    assert "developer wordpress" not in phrases


def test_single_word_ngrams_equal_tokenize():
    title = "looking for a react native developer"
    assert list(ngrams(title, 1)) == tokenize(title) == ["react", "native", "developer"]


def test_count_ngrams_over_many_titles():
    counts = count_ngrams(["logo design", "logo design for a cafe", None], 2)
    assert counts["logo design"] == 2
    assert counts["design for"] == 0


def test_programming_tokens_with_plus_and_hash_survive():
    from job_market.steps.clean import title_key

    key = title_key("Senior C++ and C# developer for A+ content")
    assert tokenize(key) == ["senior", "c++", "c#", "developer", "a+", "content"]
    assert list(ngrams(key, 2)) == ["senior c++", "c# developer", "a+ content"]
    assert count_ngrams([title_key("C++ dev"), title_key("C dev")])["c++"] == 1
