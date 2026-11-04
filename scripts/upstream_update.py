#!/usr/bin/env python3
"""One daily ref check; prepare a non-destructive, tested candidate on change."""
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

STATE=Path('.maintenance/upstream.json')
UPSTREAM='https://github.com/jurialmunkey/skin.arctic.fuse.3.git'


def run(*args, check=True):
    return subprocess.run(args,check=check,text=True,capture_output=True)


def git(*args):
    return run('git',*args).stdout.strip()


def set_version(text,version):
    return re.sub(r'(<addon\s[^>]*\bversion=")[^"]+(")',lambda m:m[1]+version+m[2],text,count=1)


def next_version(upstream,current):
    parts=upstream.split('.')
    if not all(p.isdigit() for p in parts):
        raise ValueError('upstream version must be numeric')
    old=current.split('.')
    if old[:-1]==parts:
        return upstream+'.'+str(int(old[-1])+1)
    if tuple(map(int,parts)) <= tuple(map(int,old)):
        raise ValueError('upstream version would not increase fork version')
    return upstream+'.1'


def prepare(sha,branch):
    """Caller supplies a clean checkout and fetched immutable upstream commit."""
    state=json.loads(STATE.read_text())
    manifest=Path('addon.xml')
    current=ET.fromstring(manifest.read_text()).get('version')
    baseline=ET.fromstring(git('show',state['sha']+':addon.xml')).get('version')
    git('switch','-c',branch)
    # Remove only the fork version suffix before merging to avoid routine
    # first-line version conflicts. Attribution and every runtime fix remain.
    manifest.write_text(set_version(manifest.read_text(),baseline))
    git('add','addon.xml')
    git('commit','--allow-empty','-m','chore: prepare upstream version merge')
    merge=run('git','merge','--no-edit',sha,check=False)
    if merge.returncode:
        conflicts=git('diff','--name-only','--diff-filter=U')
        run('git','merge','--abort')
        return {'status':'conflict','files':conflicts.splitlines()}
    upstream_version=ET.fromstring(git('show',sha+':addon.xml')).get('version')
    version=next_version(upstream_version,current)
    manifest.write_text(set_version(manifest.read_text(),version))
    state['sha']=sha
    STATE.write_text(json.dumps(state,indent=2)+'\n')
    git('add','addon.xml',str(STATE))
    git('commit','-m','chore: track upstream '+sha[:12]+' as '+version)
    # Tests must pass before a candidate can be pushed or announced.
    run('python3','-m','unittest','discover','-s','tests','-v')
    return {'status':'candidate','version':version}


def main():
    state=json.loads(STATE.read_text())
    sha=git('ls-remote',UPSTREAM,'refs/heads/omega').split()[0]
    if not re.fullmatch('[0-9a-f]{40}',sha):
        raise ValueError('invalid upstream SHA')
    if sha==state['sha']:
        print('Unchanged upstream; no branch, build, dispatch or issue write.')
        return
    repo=os.environ['GITHUB_REPOSITORY']
    issues=json.loads(run('gh','issue','list','--repo',repo,'--state','open','--label','upstream-update','--json','number,body').stdout)
    if len(issues)>1:
        raise ValueError('multiple upstream tracker issues; reconcile explicitly')
    marker='<!-- upstream:'+sha+' -->'
    if issues and marker in issues[0]['body']:
        print('Already checked this upstream revision; no repeated build.')
        return
    git('fetch',UPSTREAM,'omega')
    branch='maintenance/upstream-'+sha[:16]
    if git('ls-remote','origin','refs/heads/'+branch):
        result={'status':'candidate','note':'existing immutable candidate recovered'}
    else:
        try:
            result=prepare(sha,branch)
        except subprocess.CalledProcessError:
            # Record a failed revision once as well; workflow logs hold details.
            result={'status':'validation-failed'}
        if result['status']=='candidate':
            git('push','origin','HEAD:refs/heads/'+branch)
    body=marker+'\nUpstream omega: `'+sha+'`\n\n'+json.dumps(result,indent=2)
    if result['status']=='candidate':
        # GITHUB_TOKEN pushes do not trigger CI; workflow_dispatch does.
        run('gh','workflow','run','addon-validations.yml','--repo',repo,'--ref',branch)
        body+='\n\nTest candidate: https://github.com/'+repo+'/compare/omega...'+branch+'?expand=1'
        body+='\nOpen/review a PR from this compare view; no auto-merge/publication.'
    else:
        body+='\n\nManual resolution required; inspect this workflow run for details. No candidate push, reset, force-push or publication performed.'
    if issues:
        run('gh','issue','edit',str(issues[0]['number']),'--repo',repo,'--body',body)
    else:
        run('gh','issue','create','--repo',repo,'--title','Upstream update candidate','--label','upstream-update','--assignee','Serph91P','--body',body)
    print(body)

if __name__=='__main__': main()
