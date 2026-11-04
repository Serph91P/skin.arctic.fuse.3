"""Real Git merge fixtures, plus no-change/dedup side-effect guards."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('upstream_update',ROOT/'scripts/upstream_update.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class TrackingTests(unittest.TestCase):
    def test_versions_are_monotonic(self):
        self.assertEqual(m.next_version('3.4.18','3.4.18.1'),'3.4.18.2')
        self.assertEqual(m.next_version('3.4.19','3.4.18.1'),'3.4.19.1')
        with self.assertRaises(ValueError):m.next_version('3.4.17','3.4.18.1')

    def test_unchanged_never_builds_or_writes(self):
        state=json.loads((ROOT/'.maintenance/upstream.json').read_text())
        with patch.object(m,'STATE',ROOT/'.maintenance/upstream.json'):
            with patch.object(m,'git',return_value=state['sha']+' refs/heads/omega') as git,patch.object(m,'run') as run,patch.object(m,'prepare') as prepare:
                m.main()
                git.assert_called_once_with('ls-remote',m.UPSTREAM,'refs/heads/omega')
                run.assert_not_called();prepare.assert_not_called()

    def test_already_checked_revision_does_not_repeat_build(self):
        sha='f'*40
        with patch.object(m,'STATE',ROOT/'.maintenance/upstream.json'),patch.dict(os.environ,{'GITHUB_REPOSITORY':'Serph91P/skin.arctic.fuse.3'}),patch.object(m,'git',return_value=sha+' refs/heads/omega') as git,patch.object(m,'run',return_value=Mock(stdout=json.dumps([{'number':3,'body':'<!-- upstream:'+sha+' -->'}]))) as run,patch.object(m,'prepare') as prepare:
            m.main()
            self.assertEqual(git.call_count,1);self.assertEqual(run.call_count,1);prepare.assert_not_called()

    def test_failed_validation_is_recorded_without_push_or_repeated_dispatch(self):
        sha='e'*40
        issue_commands=[]
        def git(*args):
            return sha+' refs/heads/omega' if args[0]=='ls-remote' and args[1]==m.UPSTREAM else ''
        def run(*args,**kwargs):
            issue_commands.append(args)
            return Mock(stdout='[]')
        with patch.object(m,'STATE',ROOT/'.maintenance/upstream.json'),patch.dict(os.environ,{'GITHUB_REPOSITORY':'Serph91P/skin.arctic.fuse.3'}),patch.object(m,'git',side_effect=git) as git_mock,patch.object(m,'run',side_effect=run),patch.object(m,'prepare',side_effect=subprocess.CalledProcessError(1,['python3','-m','unittest'])):
            m.main()
        self.assertFalse(any(call.args[0]=='push' for call in git_mock.call_args_list))
        create=next(cmd for cmd in issue_commands if cmd[:3]==('gh','issue','create'))
        self.assertIn('<!-- upstream:'+sha+' -->',create[-1])
        self.assertIn('validation-failed',create[-1])
        self.assertFalse(any(cmd[:3]==('gh','workflow','run') for cmd in issue_commands))

    def fixture(self,conflict=False):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'));self.addCleanup(self.tmp.cleanup)
        self.cwd=os.getcwd();os.chdir(self.tmp.name);self.addCleanup(os.chdir,self.cwd)
        def g(*args):return subprocess.check_output(['git',*args],text=True,stderr=subprocess.DEVNULL).strip()
        g('init','-b','omega');g('config','user.name','Fixture');g('config','user.email','fixture@example.invalid');g('config','commit.gpgsign','false')
        Path('addon.xml').write_text('<addon id="skin.arctic.fuse.3" version="3.4.18">\n</addon>\n')
        Path('title.txt').write_text('base\n');Path('.maintenance').mkdir();Path('tests').mkdir()
        Path('tests/test_fixture.py').write_text('import unittest\nclass Fixture(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n')
        g('add','.');g('commit','-m','base');base=g('rev-parse','HEAD')
        g('switch','-c','upstream')
        Path('addon.xml').write_text('<addon id="skin.arctic.fuse.3" version="3.4.19">\n</addon>\n')
        Path('upstream.txt').write_text('new feature')
        if conflict:Path('title.txt').write_text('upstream competing fix\n')
        g('add','.');g('commit','-m','upstream update');sha=g('rev-parse','HEAD')
        g('switch','omega');Path('title.txt').write_text('retained local title fix\n')
        Path('addon.xml').write_text('<addon id="skin.arctic.fuse.3" version="3.4.18.1">\n</addon>\n')
        Path('.maintenance/upstream.json').write_text(json.dumps({'sha':base}))
        g('add','.');g('commit','-m','fork patch')
        return sha,g

    def test_changed_version_merges_preserving_patch(self):
        sha,g=self.fixture()
        result=m.prepare(sha,'candidate')
        self.assertEqual(result,{'status':'candidate','version':'3.4.19.1'})
        self.assertEqual(Path('title.txt').read_text(),'retained local title fix\n')
        self.assertTrue(Path('upstream.txt').is_file())
        self.assertEqual(json.loads(Path('.maintenance/upstream.json').read_text())['sha'],sha)
        self.assertEqual(g('status','--porcelain'),'')

    def test_conflict_is_visible_and_never_resets_fork(self):
        sha,g=self.fixture(conflict=True)
        result=m.prepare(sha,'candidate')
        self.assertEqual(result,{'status':'conflict','files':['title.txt']})
        self.assertEqual(Path('title.txt').read_text(),'retained local title fix\n')
        self.assertEqual(g('status','--porcelain'),'')

if __name__=='__main__':unittest.main()
