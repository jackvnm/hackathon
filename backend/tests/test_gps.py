from io import BytesIO
from unittest.mock import patch

from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.photos import photo_gps
from tests import test_submissions as submissions


def gps_photo(*, north="N", west="W", degrees=53):
    exif = Image.Exif()
    exif[34853] = {
        1: north, 2: (IFDRational(degrees), IFDRational(20), IFDRational(0)),
        3: west, 4: (IFDRational(6), IFDRational(15), IFDRational(0)),
    }
    buffer = BytesIO()
    Image.new("RGB", (16, 16), "blue").save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


class GPSTests(submissions.SubmissionCase):
    def test_original_gps_is_extracted_and_requires_confirmation(self):
        self.photo = gps_photo()
        for confirmed in (False, True):
            response = self.submit(location_confirmed=str(confirmed).lower())
            self.assertEqual(response.status_code, 201, response.text)
            location = response.json()["location"]
            self.assertAlmostEqual(location["lat"], 53 + 20 / 60)
            self.assertAlmostEqual(location["lng"], -6.25)
            self.assertEqual(location["source"], "photo_gps")
            self.assertEqual(location["confirmed"], confirmed)
            self.assertEqual(self.client.get(response.json()["photo_url"]).content, self.photo)

    def test_pin_can_correct_photo_gps(self):
        self.photo = gps_photo()
        response = self.submit(lat="53.34", lng="-6.26", location_confirmed="true")
        self.assertEqual(response.json()["location"]["source"], "map_pin")
        self.assertEqual(response.json()["location"]["lat"], 53.34)

    def test_confirming_same_photo_coordinates_keeps_gps_source(self):
        self.photo = gps_photo()
        response = self.submit(lat=str(53 + 20 / 60), lng="-6.25", location_confirmed="true")
        self.assertEqual(response.json()["location"]["source"], "photo_gps")

    def test_south_and_east_references(self):
        lat, lng = photo_gps(gps_photo(north="S", west="E"))
        self.assertLess(lat, 0)
        self.assertEqual(lng, 6.25)

    def test_invalid_gps_falls_back_to_unlocated(self):
        for data in (gps_photo(degrees=100), gps_photo(north="X")):
            self.assertIsNone(photo_gps(data))
            self.photo = data
            response = self.submit()
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["location"]["source"], "none")

    def test_broken_exif_does_not_break_submission(self):
        with patch("PIL.Image.Image.getexif", side_effect=ValueError("bad EXIF")):
            self.assertIsNone(photo_gps(self.photo))
