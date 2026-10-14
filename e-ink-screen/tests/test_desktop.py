import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from hink_diag.desktop import convert
from hink_diag.cli import main
from hink_diag.images import pack


class DesktopTest(unittest.TestCase):
    def test_fit_preserves_whole_image_and_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'screen.png'
            im=Image.new('RGB',(1600,900),'white')
            im.paste('black',(0,0,200,900));im.save(p)
            for rotation in (0,90,180,270):
                result,info=convert(p,'unique-id',rotation,'threshold')
                self.assertEqual(result.size,(400,300))
                self.assertEqual(len(pack(result)),15000)
                self.assertEqual(info['source_size'],[1600,900])
                self.assertAlmostEqual(info['scaled_size'][0]/info['scaled_size'][1],1600/900,delta=0.02)
                self.assertFalse(info['desktop_resolution_changed'])
                self.assertEqual(result.rotate(rotation,expand=True).getpixel((info['position'][0]+5,info['position'][1]+5)),0)

    def test_dither_and_alpha(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'grey.png';Image.new('RGBA',(400,280),(128,128,128,255)).save(p)
            frame,_=convert(p,'id')
            values=list(frame.crop((0,0,400,280)).getdata())
            black=sum(v==0 for v in values)/len(values)
            self.assertTrue(0.45<black<0.55)
            Image.new('RGBA',(400,280),(0,0,0,0)).save(p)
            frame,_=convert(p,'id')
            self.assertEqual(frame.getpixel((100,100)),255)

    def test_dry_run_no_capture_or_transport(self):
        with tempfile.TemporaryDirectory() as d,patch('hink_diag.desktop.capture') as capture,patch('hink_diag.cli.live_transport') as live:
            p=Path(d)/'input.png';Image.new('RGB',(800,600),'white').save(p)
            self.assertEqual(main(['desktop','--image',str(p),'--runs',d,'--run-id','dry']),0)
            self.assertEqual(main(['desktop','--runs',d,'--run-id','no-image']),2)
            capture.assert_not_called();live.assert_not_called()

    def test_mock_exactly_one_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.png';Image.new('RGB',(800,600),'white').save(p)
            self.assertEqual(main(['desktop','--mock','--image',str(p),'--runs',d,'--run-id','mock-desktop']),0)
            r=json.loads((Path(d)/'mock-desktop/result.json').read_text())
            self.assertEqual(r['refresh_count'],1)
            self.assertEqual(r['steps'][0]['name'],'desktop')
