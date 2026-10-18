import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from generate_ballasted import generate,SCENARIOS

class Assets(unittest.TestCase):
    def test_revised_patio_uses_floor_height_without_decorations(self):
        with tempfile.TemporaryDirectory() as tmp:
            world=generate('buitrago_patio',Path(tmp)/'revised')
            meta=json.loads((world.parent/'metadata.json').read_text())
            self.assertEqual(meta['core']['terrain'],[[0,0],[8.6,3.2]])
            self.assertEqual(meta['scenario']['equipment_variant'],'revised_supports')
            root=ET.parse(world).getroot().find('world')
            names=[m.attrib['name'] for m in root.findall('model')]
            self.assertFalse(any(n.startswith(('palm_','planter_','leaf_','curved_stair_')) for n in names))
            self.assertIn('rail_top_1',names)
            self.assertIn('corridor_2',names)
            self.assertFalse(root.findall(".//visual[@name='mast']"))
            stations=[m for m in root.findall('model') if m.attrib['name'].startswith('ballasted_station_')]
            self.assertEqual(len(stations),2)
            for station in stations:
                self.assertIsNotNone(station.find(".//visual[@name='rear_post']"))
                self.assertIsNotNone(station.find(".//visual[@name='return_seat']"))

    def test_compact_preserves_building_and_places_base_on_corridor(self):
        with tempfile.TemporaryDirectory() as tmp:
            worlds=[generate('buitrago_entre_pisos',Path(tmp)/v,variant=v) for v in ('baseline','compact_candidate')]
            roots=[ET.parse(w).getroot().find('world') for w in worlds]
            def building(root):
                return [ET.tostring(m) for m in root.findall('model') if m.attrib['name'].startswith(('atrium_','corridor_','rail_','column_','roof_'))]
            self.assertEqual(building(roots[0]),building(roots[1]))
            station=roots[1].find("model[@name='ballasted_station_1_480L']")
            self.assertAlmostEqual(float(station.findtext('pose').split()[0]),9.5)
            self.assertIsNone(station.find(".//visual[@name='mast']"))
            self.assertEqual(len(station.findall(".//visual[@name='side_post_1']")),1)
            self.assertIsNone(roots[1].find(".//visual[@name='traction_mast']"))
            self.assertEqual(len([m for m in roots[1].findall('model') if m.attrib['name'].startswith('traction_link_')]),2)

    def test_three_worlds_same_atrium_and_two_stations(self):
        atria=[]
        with tempfile.TemporaryDirectory() as tmp:
            for scenario in SCENARIOS:
                world=generate(scenario,Path(tmp)/scenario)
                root=ET.parse(world).getroot().find('world');models=root.findall('model')
                names=[m.attrib['name'] for m in models]
                self.assertEqual(len(names),len(set(names)))
                self.assertEqual(sum(n.startswith('ballasted_station_') for n in names),2)
                self.assertEqual(sum(n.startswith('bogie_') for n in names),2)
                self.assertFalse(any(n.startswith('portal_') for n in names))
                self.assertFalse(root.findall(".//visual[@name='local_motor']"))
                self.assertEqual(root.find("plugin[@name='agro::LoopSystem']/mode").text,'central_only')
                self.assertEqual(root.find("plugin[@name='agro::LoopSystem']/gust").text,str(scenario=='ladera_agricola').lower())
                metadata=json.loads((world.parent/'metadata.json').read_text())
                self.assertEqual(metadata['static_visual_models'],len(models))
                if scenario.startswith('buitrago'):
                    atria.append([ET.tostring(m) for m in models if m.attrib['name'].startswith(('atrium_','corridor_','rail_','column_','roof_','palm_','planter_','curved_stair_'))])
            self.assertEqual(atria[0],atria[1])

if __name__=='__main__':unittest.main()
