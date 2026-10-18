import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from review_ballasted_geometry import intersects,rotation

class BoxTests(unittest.TestCase):
    def test_overlap_separation_touch_and_rotation(self):
        z=np.zeros(3);r=np.eye(3);h=np.ones(3)
        self.assertTrue(intersects(z,r,h,np.array([1.9,0,0]),r,h))
        self.assertFalse(intersects(z,r,h,np.array([2.,0,0]),r,h))
        self.assertFalse(intersects(z,r,h,np.array([2.1,0,0]),r,h))
        self.assertTrue(intersects(z,r,h,np.array([2.1,0,0]),rotation(0,0,np.pi/4),h))
        self.assertFalse(intersects(z,r,np.array([2,.1,.1]),np.array([0,.3,0]),r,np.array([2,.1,.1])))

if __name__=='__main__':unittest.main()
