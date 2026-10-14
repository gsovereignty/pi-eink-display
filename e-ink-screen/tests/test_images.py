import unittest
from PIL import Image
from hink_diag.images import pack, pattern, reconstruct, split_rows


class ImagesTest(unittest.TestCase):
    def test_pixel_oracle_every_controller_byte(self):
        # Independent coordinate oracle: alternating rows and uneven x patterns
        # expose contiguous-half mistakes, bit reversal, polarity and seam errors.
        image = Image.new("1", (400, 300), 1)
        def white(x, y):
            return (x * 11 + y * 7 + x//199) % 17 >= 8
        for y in range(300):
            for x in range(400):
                image.putpixel((x, y), int(white(x, y)))
        frame = pack(image)
        self.assertEqual(len(frame), 15000)
        left, right = split_rows(frame)
        for half, start_x in ((left, 0), (right, 200)):
            self.assertEqual(len(half), 7500)
            expected = bytes(sum(int(white(start_x + b*8 + bit, y)) << (7-bit)
                                 for bit in range(8))
                             for y in range(300) for b in range(25))
            self.assertEqual(half, expected)
        self.assertNotEqual(left, frame[:7500])
        self.assertEqual(reconstruct(left, right).tobytes(), frame)

    def test_msb_polarity_and_boundary(self):
        im = Image.new("1", (400, 300), 1)
        for xy in ((0, 0), (7, 0), (199, 0), (200, 0), (399, 299)):
            im.putpixel(xy, 0)
        l, r = split_rows(pack(im))
        self.assertEqual(l[0], 0x7e)
        self.assertEqual(l[24], 0xfe)
        self.assertEqual(r[0], 0x7f)
        self.assertEqual(r[-1], 0xfe)

    def test_solid_and_opposite_halves(self):
        self.assertEqual(pack(pattern("white", "ID")), b"\xff"*15000)
        self.assertEqual(pack(pattern("black", "ID")), b"\x00"*15000)
        self.assertEqual(split_rows(pack(pattern("halves", "ID"))),
                         (b"\x00"*7500, b"\xff"*7500))
        self.assertEqual(split_rows(pack(pattern("halves-swapped", "ID"))),
                         (b"\xff"*7500, b"\x00"*7500))

    def test_rotated_labels_and_size(self):
        im = pattern("diagnostic", "UNIQUE", 0)
        self.assertEqual(pattern("diagnostic", "UNIQUE", 180).tobytes(),
                         im.rotate(180).tobytes())
        for degrees in (0, 90, 180, 270):
            rotated = pattern("smoke", "UNIQUE", degrees)
            self.assertEqual(rotated.size, (400, 300))
            self.assertEqual(len(pack(rotated)), 15000)
        self.assertNotEqual(pack(pattern("smoke", "RUN-A")), pack(pattern("smoke", "RUN-B")))

    def test_invalid_sizes(self):
        with self.assertRaises(ValueError): pack(Image.new("1", (300, 400)))
        with self.assertRaises(ValueError): split_rows(b"\0"*14999)
        with self.assertRaises(ValueError): reconstruct(b"\0", b"\0")
