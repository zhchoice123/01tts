import unittest

from src.speech_text import number_to_words, to_spoken_text


class SpeechTextTest(unittest.TestCase):
    def test_numbers_are_spelled_out(self):
        self.assertEqual("ninety-nine", number_to_words(99))
        self.assertEqual("five hundred twelve", number_to_words(512))
        self.assertEqual("twenty", number_to_words(20))

    def test_technical_terms_become_speakable(self):
        cases = {
            "The p99 latency rose to 200ms.": "The P ninety-nine latency rose to 200 milliseconds.",
            "Watch the p999 tail.": "Watch the P nine nine nine tail.",
            "Deploy it on k8s with CI/CD.": "Deploy it on Kubernetes with C I C D.",
            "This is an N+1 query.": "This is an N plus one query.",
            "Set a 512MB heap and a 2 GB cache.": "Set a 512 megabytes heap and a 2 gigabytes cache.",
            "Traffic grew 10x overnight.": "Traffic grew 10 times overnight.",
            "Use Redis, e.g. for sessions.": "Use Redis, for example, for sessions.",
            "Cache vs. database": "Cache versus database",
            "request -> queue": "request to queue",
        }
        for written, spoken in cases.items():
            with self.subTest(written=written):
                self.assertEqual(spoken, to_spoken_text(written))

    def test_code_identifiers_are_read_as_words(self):
        self.assertEqual(
            "Add the Transactional annotation to the method.",
            to_spoken_text("Add the @Transactional annotation to the method."),
        )
        self.assertEqual(
            "Call find By Id and raise max pool size.",
            to_spoken_text("Call `findById()` and raise max_pool_size."),
        )
        self.assertEqual("Call flush now.", to_spoken_text("Call flush() now."))

    def test_plain_prose_is_unchanged(self):
        prose = "The service retried the request, so the order was charged twice."
        self.assertEqual(prose, to_spoken_text(prose))
        self.assertEqual("MySQL and JSON stay readable.", to_spoken_text("MySQL and JSON stay readable."))


if __name__ == "__main__":
    unittest.main()
