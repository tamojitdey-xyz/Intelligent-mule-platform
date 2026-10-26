import tempfile, unittest
from pathlib import Path
import app as project
class SmokeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); project.DB=Path(self.temp.name)/'test.db'; project.init_db(); project.app.config['TESTING']=True; self.client=project.app.test_client()
 def tearDown(self): self.temp.cleanup()
 def test_health(self): self.assertEqual(self.client.get('/health').json['status'],'ok')
 def test_dashboard(self): self.assertEqual(self.client.get('/').status_code,200)
 def test_transactions(self): self.assertEqual(self.client.get('/transactions').status_code,200)
if __name__=='__main__': unittest.main()
