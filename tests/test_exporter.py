import unittest
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from apps.api.asdos_api.exporter import build_workbook


NS = {"x":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def payload():
    long_text = "Jawaban panjang sintetis — " * 1500
    return {
        "mode":"draft", "assessment":{"title":"Ujian Formula =SUM(1,1)"},
        "info":{"project":"ASDOS","mode":"DRAFT — BELUM DISAHKAN","assessment":"UTS Sintetis","w_total":"10"},
        "questions":[{"id":"q1","label":"1","order":1}],
        "summary":[["submission-id","0012345678","Mahasiswa Sintetis",1,"7.9","7.9",None,"draft",""]],
        "question_details":[["submission-id","0012345678","q1","1","8","10","10","7.9","reviewed","reviewed_criteria","draft",None,"review-id"]],
        "criterion_details":[["submission-id","q1","c1","0.8","10","8",[{"region_id":"r1"}],"=HYPERLINK(\"https://invalid\")","human"]],
        "transcriptions":[["submission-id","q1","s1","r1",1,1,long_text,["synthetic"],"transcript-id"]],
        "rubric":[["revision-id","q1","1","Soal sintetis","10","10","c1","Kriteria", "10",{"0":"kosong"},"Kunci","Alternatif"]],
        "history":[], "metadata":{"schema":"asdos-export.v1","test":"formula-like =1+1"}
    }


class ExporterTests(unittest.TestCase):
    def test_workbook_has_required_sheets_numeric_scores_and_literal_strings(self):
        blob = build_workbook(payload())
        with zipfile.ZipFile(BytesIO(blob)) as archive:
            names = {path.rsplit("/",1)[-1] for path in archive.namelist() if path.startswith("xl/worksheets/sheet") and path.endswith(".xml")}
            self.assertEqual(len(names), 9)  # 8 contract sheets plus the overflow text sheet.
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet_names = {item.attrib["name"] for item in workbook.findall("x:sheets/x:sheet", NS)}
            self.assertTrue({"Informasi","Rekap_Nilai","Detail_Nomor","Detail_Kriteria","Transkripsi","Rubrik","Riwayat","Metadata","Teks_Lanjutan"}.issubset(sheet_names))
            for path in archive.namelist():
                if path.startswith("xl/worksheets/") and path.endswith(".xml"):
                    root = ET.fromstring(archive.read(path))
                    self.assertEqual(root.findall(".//x:f", NS), [])
                    self.assertEqual(root.findall(".//x:hyperlink", NS), [])
            self.assertNotIn("xl/externalLinks/externalLink1.xml", archive.namelist())
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            texts = ["".join(node.itertext()) for node in shared.findall("x:si", NS)]
            self.assertIn("0012345678", texts)
            self.assertIn("=HYPERLINK(\"https://invalid\")", texts)
            self.assertIn("test", texts)
            self.assertTrue(any("Teks_Lanjutan" in text for text in texts))


if __name__ == "__main__":
    unittest.main()
