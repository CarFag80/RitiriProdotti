import copy
import unittest
from repair_dates import repair_records, to_iso


class DateTests(unittest.TestCase):
    def test_supported_formats(self):
        for value in ("23 ottobre 2026", "23/10/2026", "23/ottobre/2026",
                      " 23  OTTOBRE  2026 ", "23\u00a0ottobre\u00a02026",
                      "2026-10-23", "23 / ottobre / 2026"):
            with self.subTest(value=value):
                self.assertEqual(to_iso(value), "2026-10-23")

    def test_all_months(self):
        from repair_dates import MONTHS
        for name, number in MONTHS.items():
            with self.subTest(month=name):
                self.assertEqual(to_iso(f"1 {name} 2026"), f"2026-{number:02d}-01")

    def test_invalid_dates(self):
        for value in ("31 febbraio 2026", "29 febbraio 2026", "31/04/2026",
                      "00/10/2026", "23/13/2026", "23 sconosciuto 2026",
                      "23 ottobre 26", "testo 23 ottobre 2026", "", None, 23):
            with self.subTest(value=value):
                self.assertEqual(to_iso(value), "")

    def test_leap_year(self):
        self.assertEqual(to_iso("29 febbraio 2024"), "2024-02-29")

    def test_repair_and_preserve(self):
        records = [
            {"id": "a", "published": "", "noticeDate": "23 ottobre 2026", "lots": ["A"]},
            {"id": "b", "published": "2026-10-21", "noticeDate": "23 ottobre 2026"},
            {"id": "c", "campi": {"data pubblicazione": "23 ottobre 2026"}},
            {"id": "d", "noticeDate": "31 febbraio 2026"},
        ]
        before = copy.deepcopy(records)
        self.assertEqual(repair_records(records), 2)
        self.assertEqual(records[0]["published"], "2026-10-23")
        self.assertEqual(records[2]["published"], "2026-10-23")
        self.assertEqual(records[0]["lots"], before[0]["lots"])
        self.assertEqual(records[1], before[1])
        self.assertEqual(records[3], before[3])
        self.assertEqual(len(records), len(before))
        self.assertEqual(repair_records(records), 0)

    def test_fallback_field(self):
        records = [{"noticeDate": "non riconosciuta", "campi": {"data pubblicazione": "23/10/2026"}}]
        self.assertEqual(repair_records(records), 1)

    def test_invalid_archive(self):
        for records in ({}, [None]):
            with self.assertRaises(ValueError):
                repair_records(records)


if __name__ == "__main__":
    unittest.main()
