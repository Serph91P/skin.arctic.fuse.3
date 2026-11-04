"""Evaluate actual Info_Title visibility expressions without changing Kodi UI."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
TREE=ET.parse(ROOT/'1080i/Includes_Info.xml')

def visible(expression,values,prefer):
    expression=expression.replace('$PARAM[prefer_title]',str(prefer))
    def replace(match):
        return str(not values.get(match[1].rsplit('.',1)[-1],''))
    expression=re.sub(r'String.IsEmpty\(([^)]+)\)',replace,expression)
    expression=expression.replace('[','(').replace(']',')').replace('+',' and ').replace('|',' or ').replace('!',' not ')
    return bool(eval(expression,{'__builtins__':{}},{}))

class TitleTests(unittest.TestCase):
    def test_all_skin_xml_parses(self):
        for folder in ('1080i','colors','extras','shortcuts'):
            for path in (ROOT/folder).rglob('*.xml'):
                ET.parse(path)

    def test_actual_title_branches_keep_music_and_fallbacks(self):
        calls=TREE.findall(".//include[@name='Info_Title']/definition//include[@content='Info_Title_Text']")
        self.assertEqual(len(calls),4)
        cases=[
            ({'Artist':'Channel','Title':'Video'},True,'Title'),
            ({'Artist':'Musician','Title':'Song'},False,'Artist'),
            ({'Title':'Movie'},False,'Title'),
            ({'Artist':'Channel','Label':'Fallback'},True,'Label'),
            ({'TVShowTitle':'Show','Artist':'Actor','Title':'Episode'},True,'TVShowTitle'),
            ({'Label':'Fallback'},False,'Label'),
        ]
        for values,prefer,expected in cases:
            actual=[]
            for call in calls:
                condition=call.find("param[@name='visible']").text
                if visible(condition,values,prefer):
                    actual.append(call.find("param[@name='title']").text.rsplit('.',1)[-1])
            self.assertEqual(actual,[expected],(values,prefer))

    def test_opt_in_browsing_and_player_scope(self):
        self.assertEqual(TREE.find(".//include[@name='Info_Title']/param[@name='prefer_title']").text,'false')
        browsing=TREE.findall(".//param[@name='prefer_title']")
        self.assertIn('String.IsEqual($PARAM[container]$PARAM[listitem].DBType,video)',[n.text for n in browsing])
        player=ET.parse(ROOT/'1080i/Includes_OSD.xml')
        self.assertEqual([n.text for n in player.findall(".//param[@name='prefer_title']")],['!Player.HasAudio + !VideoPlayer.Content(musicvideos)']*2)

    def test_youtube_box_is_static_small_and_mutually_exclusive(self):
        definition=TREE.find(".//include[@name='Info_Title_Text']/definition")
        box=definition.find("control[@type='textbox']")
        label=definition.find("control[@type='label']")
        self.assertEqual(box.findtext('font'),'font_head_bold')
        self.assertEqual(box.findtext('height'),'info_title_h')
        self.assertEqual(box.findtext('autoscroll'),'false')
        self.assertEqual(box.findtext('visible'),'[$PARAM[visible]] + [$PARAM[youtube_video]]')
        self.assertEqual(label.findtext('visible'),'[$PARAM[visible]] + ![$PARAM[youtube_video]]')

if __name__=='__main__': unittest.main()
