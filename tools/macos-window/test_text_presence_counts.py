"""Presence assertions may accept repeated labels; target resolution stays unique."""
import unittest
from pathlib import Path
import window_macro as m


class TextPresenceCountsTests(unittest.TestCase):
    def observe(self, labels):
        lines=[{'text':s,'confidence':.5,'bounds':[.1,.1,.2,.2]} for s in labels]
        o=m.Observation('PAGE',Path('unused.png'),{'width':100,'height':100,'lines':lines}, {'binary':'unused','language':'zh-Hans'})
        o.timer_regions[('text',0,0,100,100)]=lines
        return o

    def test_repeated_presence_is_explicit_and_zero_still_fails(self):
        for cropped,preferred in [(True,False),(False,False),(True,True)]:
            region={'bounds':[0,0,100,100],'pattern':'RALLY','crop_ocr':cropped,'prefer_frame_ocr':preferred}
            condition={'all':['PAGE'],'text_regions':[region]}
            with self.assertRaises(RuntimeError):m.require_text(self.observe(['RALLY','RALLY']),condition)
            region['max_matches']=6
            m.validate_condition(condition,[100,100])
            m.require_text(self.observe(['RALLY','RALLY']),condition)
            with self.assertRaises(RuntimeError):m.require_text(self.observe([]),condition)
            with self.assertRaises(RuntimeError):m.require_text(self.observe(['RALLY']*7),condition)

    def test_invalid_count_limits_are_rejected(self):
        for value in [0,11,True,1.5,'6']:
            with self.assertRaises(ValueError):
                m.validate_condition({'text_regions':[{'bounds':[0,0,100,100],'pattern':'RALLY','max_matches':value}]},[100,100])


if __name__=='__main__':unittest.main()
