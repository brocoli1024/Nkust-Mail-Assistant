import json
import os
from pathlib import Path
import subprocess
import sys


def run_pipeline(tmp_path,fail='',announcement_id='',office_url='',article_result=''):
    app=tmp_path/'app';app.mkdir();(app/'__init__.py').write_text('')
    fake="import json,os,sys\nfrom pathlib import Path\np=Path(os.environ['QA_RECORD'])\nwith p.open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\n"
    fake+="if sys.argv[1]=='office-import':Path(os.environ['QA_IMPORTED']).write_text(Path(sys.argv[-1]).read_text())\n"
    fake+="if sys.argv[1]=='articles' and os.environ.get('QA_ARTICLE_RESULT'):print(os.environ['QA_ARTICLE_RESULT'])\n"
    fake+="sys.exit(1 if sys.argv[1] in os.environ.get('QA_FAIL','').split(',') else 0)\n"
    (app/'public_cli.py').write_text(fake)
    record=tmp_path/'calls.jsonl';env=os.environ.copy()
    # Never pass real connection strings or OAuth settings into the synthetic CLI.
    env.pop('DATABASE_URL',None);env.update(QA_RECORD=str(record),QA_FAIL=fail,QA_ARTICLE_RESULT=article_result,NKUST_PUBLIC_ANNOUNCEMENT_ID=announcement_id,NKUST_PUBLIC_OFFICE_URL=office_url,QA_IMPORTED=str(tmp_path/'imported.txt'))
    result=subprocess.run([sys.executable,str(Path('scripts/refresh_public_sources.py').resolve())],cwd=tmp_path,env=env,capture_output=True,text=True)
    calls=[json.loads(line) for line in record.read_text().splitlines()] if record.exists() else []
    return result,calls


def test_rss_failure_does_not_skip_other_public_sources(tmp_path):
    r,calls=run_pipeline(tmp_path,fail='sync')
    assert r.returncode==1 and [c[0] for c in calls]==['sync','articles','office-refresh']
    assert 'partial' in r.stdout


def test_article_failure_does_not_skip_office_and_target_id_is_preserved(tmp_path):
    r,calls=run_pipeline(tmp_path,fail='articles',announcement_id='48')
    assert r.returncode==1 and calls[1]==['articles','--limit','1','--announcement-id','48']
    assert calls[2]==['office-refresh','--limit','8']


def test_all_sources_success_and_invalid_id_are_explicit(tmp_path):
    ok,calls=run_pipeline(tmp_path)
    assert ok.returncode==0 and len(calls)==3
    other=tmp_path/'other';other.mkdir()
    invalid,calls=run_pipeline(other,announcement_id='48; PRIVATE')
    assert invalid.returncode==1 and [c[0] for c in calls]==['sync','office-refresh']
    assert 'PRIVATE' not in invalid.stdout+invalid.stderr


def test_explicit_office_url_import_uses_temporary_file_and_cleans_it(tmp_path):
    url='https://officemail.nkust.edu.tw/Mail/MailView/69929'
    r,calls=run_pipeline(tmp_path,office_url=url)
    assert r.returncode==0 and [c[0] for c in calls]==['sync','articles','office-import']
    assert (tmp_path/'imported.txt').read_text().strip()==url
    assert not Path(calls[-1][-1]).exists()


def test_known_article_partial_is_warning_but_malformed_result_is_failure(tmp_path):
    partial=json.dumps({'updated':0,'failed':1,'status':'partial'})
    r,calls=run_pipeline(tmp_path,fail='articles',article_result=partial)
    assert r.returncode==0 and calls[-1][0]=='office-refresh'
    assert '::warning::' in r.stdout and 'warning' in r.stdout
    bad=tmp_path/'bad';bad.mkdir()
    r,_=run_pipeline(bad,fail='articles',article_result=json.dumps({'updated':0,'failed':0,'status':'partial'}))
    assert r.returncode==1
