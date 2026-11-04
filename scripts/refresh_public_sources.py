"""Run independent public maintenance stages; never hide a partial failure."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    selected=os.environ.get('NKUST_PUBLIC_ANNOUNCEMENT_ID','').strip()
    office_url=os.environ.get('NKUST_PUBLIC_OFFICE_URL','').strip()
    stages=[('feed',['sync','--source','nkust-latest'])]
    invalid=bool(selected and not re.fullmatch(r'[1-9][0-9]{0,17}',selected))
    if not invalid:
        stages.append(('articles',['articles','--limit','1','--announcement-id',selected] if selected else ['articles','--limit','8']))
    warnings=[]
    results={'articles':1} if invalid else {}
    if invalid:print('PUBLIC_ANNOUNCEMENT_ID_INVALID',flush=True)
    # The explicit administrator URL is validated again by office-import. Never
    # accept shell commands, scan IDs, or inspect Gmail credentials here.
    with tempfile.TemporaryDirectory(prefix='nkust-public-office-') as temporary:
        if office_url and len(office_url)<=4096 and not any(c in office_url for c in '\r\n'):
            urls_file=Path(temporary)/'urls.txt';urls_file.write_text(office_url+'\n',encoding='utf-8')
            stages.append(('office_mail',['office-import','--urls-file',str(urls_file)]))
        else:
            if office_url:results['office_import']=1;print('PUBLIC_OFFICE_URL_INVALID',flush=True)
            stages.append(('office_mail',['office-refresh','--limit','8']))
        for name,args in stages:
            print('Public maintenance stage: '+name,flush=True)
            try:
                process=subprocess.run([sys.executable,'-m','app.public_cli',*args],check=False,capture_output=name=='articles',text=True)
                results[name]=process.returncode
                if name=='articles':
                    print(process.stdout or '',end='',flush=True)
                    if process.stderr:print(process.stderr,end='',file=sys.stderr,flush=True)
                    try:
                        result=json.loads(process.stdout)
                        valid=all(type(result[k]) is int and result[k]>=0 for k in ('updated','failed'))
                        partial=(valid and process.returncode==1 and result['status']=='partial' and result['failed']>0)
                    except (ValueError,KeyError,TypeError):partial=False
                    if partial:
                        warnings.append(name)
                        print('::warning::Article enrichment partially failed; existing public data is retained.',flush=True)
            except OSError:results[name]=1;print('PUBLIC_STAGE_START_FAILED',flush=True)
    success=all(code==0 or name in warnings for name,code in results.items())
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as report:
            report.write('## Public maintenance results\n\n| Stage | Result |\n| --- | --- |\n')
            for name,code in results.items():
                label='warning (partial)' if name in warnings else 'success' if code==0 else 'failure'
                report.write(f'| {name} | {label} |\n')
            report.write('\nOffice refresh rereads known public URLs; it does not discover new mail.\n')
    print(json.dumps({'status':'success' if success else 'partial','stage_results':results,'warnings':warnings}),flush=True)
    return 0 if success else 1


if __name__=='__main__':raise SystemExit(main())
