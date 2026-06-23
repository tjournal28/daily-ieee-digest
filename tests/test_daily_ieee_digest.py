import unittest
from unittest.mock import patch
import datetime as dt

from scripts import daily_ieee_digest as digest


class CollectCandidatesTests(unittest.TestCase):
    def test_collect_candidates_can_limit_to_one_selected_journal(self):
        config = {
            "include_keywords": ["wireless"],
            "exclude_keywords": [],
            "journals": [
                {
                    "key": "TWC",
                    "title": "IEEE Transactions on Wireless Communications",
                    "issn": "1111-1111",
                    "eissn": None,
                    "metrics": {
                        "system": "JCR-JIF",
                        "year": 2024,
                        "quartile": "Q1",
                        "impact_factor": "8.9",
                        "source": "IEEE Title List",
                        "source_url": "https://example.com/twc",
                    },
                },
                {
                    "key": "TAP",
                    "title": "IEEE Transactions on Antennas and Propagation",
                    "issn": "2222-2222",
                    "eissn": None,
                    "metrics": {
                        "system": "JCR-JIF",
                        "year": 2024,
                        "quartile": "Q1",
                        "impact_factor": "5.8",
                        "source": "IEEE Title List",
                        "source_url": "https://example.com/tap",
                    },
                },
            ],
        }
        twc_response = {
            "message": {
                "items": [
                    {
                        "title": ["Wireless Candidate"],
                        "DOI": "10.1109/twc.2026.1000001",
                        "container-title": ["IEEE Transactions on Wireless Communications"],
                        "published-online": {"date-parts": [[2026, 6, 1]]},
                        "URL": "https://example.com/twc-paper",
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "abstract": "<jats:p>Wireless abstract.</jats:p>",
                    }
                ]
            }
        }

        with patch.object(digest, "get_json", return_value=twc_response) as get_json:
            candidates = digest.collect_candidates(
                config,
                days_back=30,
                rows_per_journal=10,
                selected_journal_keys={"TWC"},
            )

        self.assertEqual(1, len(candidates))
        self.assertEqual("TWC", candidates[0].journal_key)
        self.assertEqual(1, get_json.call_count)

    def test_collect_candidates_filters_non_paper_entries_and_keeps_authored_articles(self):
        config = {
            "include_keywords": ["antenna"],
            "exclude_keywords": [],
            "journals": [
                {
                    "key": "TAP",
                    "title": "IEEE Transactions on Antennas and Propagation",
                    "issn": "0000-0000",
                    "eissn": None,
                    "metrics": {
                        "system": "JCR-JIF",
                        "year": 2024,
                        "quartile": "Q1",
                        "impact_factor": "5.8",
                        "source": "IEEE Title List",
                        "source_url": "https://example.com/metrics",
                    },
                }
            ],
        }
        response = {
            "message": {
                "items": [
                    {
                        "title": ["IEEE Transactions on Antennas and Propagation Publication Information"],
                        "DOI": "10.1109/tap.2026.3696877",
                        "container-title": ["IEEE Transactions on Antennas and Propagation"],
                        "published-online": {"date-parts": [[2026, 6, 1]]},
                        "URL": "https://example.com/publication-information",
                        "author": [],
                        "abstract": "<jats:p>Administrative page.</jats:p>",
                    },
                    {
                        "title": ["W-Band Broadband Antenna for 3-D Integration"],
                        "DOI": "10.1109/tap.2026.3671385",
                        "container-title": ["IEEE Transactions on Antennas and Propagation"],
                        "published-online": {"date-parts": [[2026, 6, 1]]},
                        "URL": "https://example.com/paper",
                        "author": [
                            {"given": "Ada", "family": "Lovelace"},
                            {"given": "Grace", "family": "Hopper"},
                        ],
                        "abstract": "<jats:p>An antenna paper abstract.</jats:p>",
                    },
                ]
            }
        }

        with patch.object(digest, "get_json", return_value=response):
            candidates = digest.collect_candidates(config, days_back=30, rows_per_journal=10)

        self.assertEqual(1, len(candidates))
        self.assertEqual("10.1109/tap.2026.3671385", candidates[0].doi)
        self.assertEqual("Ada Lovelace, Grace Hopper", candidates[0].authors)
        self.assertEqual("An antenna paper abstract.", candidates[0].abstract)

    def test_collect_candidates_uses_landing_page_abstract_when_crossref_abstract_missing(self):
        config = {
            "include_keywords": ["antenna"],
            "exclude_keywords": [],
            "journals": [
                {
                    "key": "TAP",
                    "title": "IEEE Transactions on Antennas and Propagation",
                    "issn": "0000-0000",
                    "eissn": None,
                    "metrics": {
                        "system": "JCR-JIF",
                        "year": 2024,
                        "quartile": "Q1",
                        "impact_factor": "5.8",
                        "source": "IEEE Title List",
                        "source_url": "https://example.com/metrics",
                    },
                }
            ],
        }
        response = {
            "message": {
                "items": [
                    {
                        "title": ["A Low-RCS Circular Polarization High-Gain Antenna Based on Metasurfaces"],
                        "DOI": "10.1109/tap.2026.3666105",
                        "container-title": ["IEEE Transactions on Antennas and Propagation"],
                        "published-online": {"date-parts": [[2026, 6, 1]]},
                        "URL": "https://example.com/paper",
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                    }
                ]
            }
        }

        with patch.object(digest, "get_json", return_value=response), patch.object(
            digest,
            "fetch_landing_page_abstract",
            return_value="Fallback abstract from landing page.",
        ) as fallback:
            candidates = digest.collect_candidates(config, days_back=30, rows_per_journal=10)

        self.assertEqual("Fallback abstract from landing page.", candidates[0].abstract)
        fallback.assert_called_once_with("https://example.com/paper")

    def test_collect_candidates_can_skip_expensive_abstract_resolution_until_after_selection(self):
        config = {
            "include_keywords": ["antenna"],
            "exclude_keywords": [],
            "journals": [
                {
                    "key": "TAP",
                    "title": "IEEE Transactions on Antennas and Propagation",
                    "issn": "0000-0000",
                    "eissn": None,
                    "metrics": {
                        "system": "JCR-JIF",
                        "year": 2024,
                        "quartile": "Q1",
                        "impact_factor": "5.8",
                        "source": "IEEE Title List",
                        "source_url": "https://example.com/metrics",
                    },
                }
            ],
        }
        response = {
            "message": {
                "items": [
                    {
                        "title": ["Antenna Candidate One"],
                        "DOI": "10.1109/tap.2026.1000001",
                        "container-title": ["IEEE Transactions on Antennas and Propagation"],
                        "published-online": {"date-parts": [[2026, 6, 1]]},
                        "URL": "https://example.com/paper1",
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                    }
                ]
            }
        }

        with patch.object(digest, "get_json", return_value=response), patch.object(
            digest,
            "resolve_abstract",
            return_value="Should not be called.",
        ) as resolver:
            candidates = digest.collect_candidates(
                config,
                days_back=30,
                rows_per_journal=10,
                resolve_abstracts=False,
            )

        self.assertEqual("", candidates[0].abstract)
        resolver.assert_not_called()


class MetadataHelpersTests(unittest.TestCase):
    def test_select_daily_journal_is_stable_for_same_day(self):
        journals = [
            {"key": "TWC"},
            {"key": "TAP"},
            {"key": "TMTT"},
        ]

        first = digest.select_daily_journal(journals, dt.date(2026, 6, 23))
        second = digest.select_daily_journal(journals, dt.date(2026, 6, 23))

        self.assertEqual(first["key"], second["key"])
        self.assertIn(first["key"], {"TWC", "TAP", "TMTT"})

    def test_select_daily_journal_varies_with_date(self):
        journals = [
            {"key": "TWC"},
            {"key": "TAP"},
            {"key": "TMTT"},
        ]

        selected = {
            digest.select_daily_journal(journals, dt.date(2026, 6, day))["key"]
            for day in range(20, 27)
        }

        self.assertGreaterEqual(len(selected), 2)

    def test_extract_authors_formats_names(self):
        item = {
            "author": [
                {"given": "Ada", "family": "Lovelace"},
                {"name": "Grace Hopper"},
                {"family": "Turing"},
            ]
        }

        self.assertEqual(
            "Ada Lovelace, Grace Hopper, Turing",
            digest.extract_authors(item),
        )

    def test_clean_abstract_strips_jats_markup(self):
        raw = "<jats:p>First <b>line</b>.</jats:p><jats:p>Second line.</jats:p>"

        self.assertEqual("First line. Second line.", digest.clean_abstract(raw))

    def test_extract_abstract_from_html_prefers_citation_abstract_meta(self):
        html_text = """
        <html>
          <head>
            <meta name="description" content="Generic description.">
            <meta name="citation_abstract" content="Specific paper abstract.">
          </head>
        </html>
        """

        self.assertEqual("Specific paper abstract.", digest.extract_abstract_from_html(html_text))

    def test_resolve_abstract_prefers_crossref_before_landing_page(self):
        item = {"abstract": "<jats:p>Crossref abstract.</jats:p>"}

        with patch.object(digest, "fetch_landing_page_abstract") as fallback:
            abstract = digest.resolve_abstract(item, "https://example.com/paper", "10.1109/tap.2026.1234567")

        self.assertEqual("Crossref abstract.", abstract)
        fallback.assert_not_called()

    def test_resolve_abstract_falls_back_to_openalex_after_landing_page(self):
        item = {}

        with patch.object(digest, "fetch_landing_page_abstract", return_value=""), patch.object(
            digest,
            "fetch_openalex_abstract",
            return_value="OpenAlex abstract.",
        ) as openalex:
            abstract = digest.resolve_abstract(item, "https://example.com/paper", "10.1109/tap.2026.3671263")

        self.assertEqual("OpenAlex abstract.", abstract)
        openalex.assert_called_once_with("10.1109/tap.2026.3671263")

    def test_openalex_abstract_from_inverted_index_reconstructs_text(self):
        inverted_index = {
            "Abstract": [0],
            "from": [1],
            "OpenAlex.": [2],
        }

        self.assertEqual(
            "Abstract from OpenAlex.",
            digest.abstract_from_inverted_index(inverted_index),
        )

    def test_enrich_candidates_with_abstracts_updates_only_selected_articles(self):
        candidates = [
            digest.Candidate(
                title="Paper One",
                journal="IEEE Transactions on Antennas and Propagation",
                journal_key="TAP",
                doi="10.1109/tap.2026.1000001",
                url="https://example.com/paper1",
                published="2026-06-01",
                metrics={
                    "system": "JCR-JIF",
                    "year": 2024,
                    "quartile": "Q1",
                    "impact_factor": "5.8",
                    "source": "IEEE Title List",
                    "source_url": "https://example.com/metrics",
                },
                score=2,
                authors="Ada Lovelace",
                abstract="",
            )
        ]

        with patch.object(digest, "resolve_abstract", return_value="Resolved abstract.") as resolver:
            enriched = digest.enrich_candidates_with_abstracts(candidates)

        self.assertEqual("Resolved abstract.", enriched[0].abstract)
        resolver.assert_called_once_with({}, "https://example.com/paper1", "10.1109/tap.2026.1000001")


class RenderingTests(unittest.TestCase):
    def test_render_text_and_html_include_authors_and_abstract(self):
        article = digest.Candidate(
            title="Example Antenna Paper",
            journal="IEEE Transactions on Antennas and Propagation",
            journal_key="TAP",
            doi="10.1109/tap.2026.1234567",
            url="https://example.com/paper",
            published="2026-06-01",
            metrics={
                "system": "JCR-JIF",
                "year": 2024,
                "quartile": "Q1",
                "impact_factor": "5.8",
                "source": "IEEE Title List",
                "source_url": "https://example.com/metrics",
            },
            score=2,
            authors="Ada Lovelace, Grace Hopper",
            abstract="This is the abstract.",
        )

        text_body = digest.render_text([article])
        html_body = digest.render_html([article])

        self.assertIn("Authors: Ada Lovelace, Grace Hopper", text_body)
        self.assertIn("Abstract: This is the abstract.", text_body)
        self.assertNotIn("copyright", text_body.lower())
        self.assertIn("Ada Lovelace, Grace Hopper", html_body)
        self.assertIn("This is the abstract.", html_body)


if __name__ == "__main__":
    unittest.main()
