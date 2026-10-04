from io import BytesIO

from PIL import Image

from tests.test_gps import gps_photo
from tests.test_submissions import SubmissionCase


class PhotoMetadataTests(SubmissionCase):
    def metadata(self, data):
        return self.client.post('/api/photos/metadata', files={'photo': ('demo-photo', data, 'application/octet-stream')})

    def test_gps_all_supported_formats_and_no_persistence(self):
        # Synthetic JPEG GPS uses inline hemisphere tags, unlike the former JS parser.
        original = gps_photo(north='S', west='E')
        for format in ('JPEG', 'PNG', 'WEBP'):
            with Image.open(BytesIO(original)) as image:
                output = BytesIO()
                image.save(output, format=format, exif=image.getexif())
            response = self.metadata(output.getvalue())
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()['gps_found'])
            location = response.json()['location']
            self.assertAlmostEqual(location['lat'], -(53 + 20 / 60))
            self.assertAlmostEqual(location['lng'], 6.25)
            self.assertEqual(location['source'], 'photo_gps')
            self.assertFalse(location['confirmed'])
        self.assertEqual(self.client.get('/api/issues').json(), [])
        self.assertEqual(list(self.settings.photo_dir.iterdir()), [])

    def test_missing_or_invalid_gps_is_absent(self):
        for data in (self.photo, gps_photo(degrees=100), gps_photo(north='X')):
            response = self.metadata(data)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(response.json()['gps_found'])
            self.assertIsNone(response.json()['location']['lat'])

    def test_bad_image_and_oversized_are_rejected(self):
        self.assertEqual(self.metadata(b'not an image').status_code, 422)
        self.assertEqual(self.metadata(b'x' * (self.settings.max_photo_bytes + 1)).status_code, 413)
        self.assertEqual(list(self.settings.photo_dir.iterdir()), [])
