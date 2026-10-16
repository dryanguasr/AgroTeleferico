"""Structural asset tests: XML parsing is not a Gazebo/SDF schema validation."""
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('generate_loop',ROOT/'scripts/generate_loop.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Assets(unittest.TestCase):
    def test_mesh_path_with_spaces_and_xml_characters(self):
        with tempfile.TemporaryDirectory() as t:
            p=m.generate(ROOT/'config/loop.yaml',Path(t)/'workspace with spaces & accents á')
            uri=ET.parse(p).find('.//mesh/uri').text
            self.assertEqual(Path(uri),p.parent/'terrain.dae')
            self.assertTrue(Path(uri).is_file())
            self.assertNotIn('%20',uri)
            self.assertEqual(float(ET.parse(p).find('.//max_step_size').text),.01)
            self.assertEqual(m.read_config(p.parent/'loop.yaml')['dt'],.002)

    def test_terrain_normals_and_triangle_indices(self):
        with tempfile.TemporaryDirectory() as t:
            p=m.generate(ROOT/'config/loop.yaml',Path(t)/'case')
            ns={'c':'http://www.collada.org/2005/11/COLLADASchema'}
            mesh=ET.parse(p.parent/'terrain.dae')
            triangles=mesh.find('.//c:triangles',ns)
            indices=list(map(int,triangles.find('c:p',ns).text.split()))
            self.assertEqual(len(indices),int(triangles.attrib['count'])*3*2)
            normals=list(map(float,mesh.find('.//c:float_array[@id="normal-data"]',ns).text.split()))
            self.assertLess(max(indices),len(normals)//3)
            for i in range(0,len(normals),3):
                self.assertAlmostEqual(math.sqrt(sum(x*x for x in normals[i:i+3])),1)
                self.assertGreater(normals[i+2],0)

    def test_model_inventory_and_local_assets(self):
        with tempfile.TemporaryDirectory() as t:
            p=m.generate(ROOT/'config/loop.yaml',Path(t)/'case')
            xml=ET.parse(p);names=[a.attrib['name'] for a in xml.findall('.//model')]
            self.assertEqual(len(names),len(set(names)))
            for prefix,n in [('bogie_',6),('pallet_',6),('portal_',9),('flex_',384)]:
                self.assertEqual(sum(x.startswith(prefix) for x in names),n)
            self.assertIn('main_motor_lower',names)
            self.assertEqual(len(xml.findall('.//visual[@name="central_mast"]')),9)
            self.assertEqual(len(xml.findall('.//visual[@name="column_-1"]')),0)
            self.assertEqual(len(xml.findall('.//collision')),0)
            ET.parse(p.parent/'terrain.dae')
            self.assertNotIn('fuel.gazebosim',p.read_text())
            with self.assertRaises(FileExistsError):m.generate(ROOT/'config/loop.yaml',p.parent)
    def test_supports_not_double_counted(self):
        c=m.read_config(ROOT/'config/loop.yaml')
        for n,total in [(3,9),(4,13),(5,17)]:
            c['supports_per_segment']=n;xs=m.supports(c)
            self.assertEqual(len(xs),total);self.assertEqual(len(set(xs)),total)
    def test_terrain_has_no_extra_extrema(self):
        c=m.read_config(ROOT/'config/loop.yaml')
        for a,b in zip(c['terrain'],c['terrain'][1:]):
            samples=[m.ground(c,a[0]+(b[0]-a[0])*i/100) for i in range(101)]
            self.assertTrue(all((y-x)*(b[1]-a[1])>=0 for x,y in zip(samples,samples[1:])))

if __name__=='__main__':unittest.main()
