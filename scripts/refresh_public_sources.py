"""Run independent public maintenance stages; never hide a partial failure."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile


def main(*,run=subprocess.run):
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
                process=run([sys.executable,'-m','app.public_cli',*args],check=False,capture_output=name=='articles',text=True)
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
    discovery_report=None
    if os.environ.get('NKUST_OFFICE_DISCOVERY_TRIGGER_SECRET'):
        print('Public maintenance stage: discovery',flush=True)
        try:
            process=run([sys.executable,str(Path(__file__).with_name('trigger_office_discovery.py'))],check=False,capture_output=True,text=True)
            results['discovery']=process.returncode
            try:
                from scripts.trigger_office_discovery import CODES
            except ModuleNotFoundError:
                from trigger_office_discovery import CODES
            try:
                report=json.loads(process.stdout.splitlines()[0])
                allowed=CODES|{'OFFICE_DISCOVERY_NOT_CONFIGURED','OFFICE_DISCOVERY_TRIGGER_CONFIG','OFFICE_DISCOVERY_TRIGGER_AUTH','OFFICE_DISCOVERY_TRIGGER_HTTP','OFFICE_DISCOVERY_TRIGGER_RESPONSE','OFFICE_DISCOVERY_TRIGGER_UNCONFIRMED'}
                if not isinstance(report,dict) or report.get('error_code') not in allowed|{None}:raise ValueError()
                if set(report)-{'status','error_code','scanned','discovered','published','rejected','pending'}:raise ValueError()
                if report.get('status') not in ('success','partial','failed','busy','skipped'):raise ValueError()
                counts={k:report[k] for k in ('scanned','discovered','published','rejected','pending') if k in report}
                if any(type(v) is not int or v<0 for v in counts.values()):raise ValueError()
                if report['status'] in ('success','partial') and len(counts)!=5:raise ValueError()
                discovery_report=report
                print(json.dumps(report),flush=True)
                if process.returncode==0 and (report['status']=='busy' or report['status']=='partial' and report.get('error_code')=='OFFICE_DISCOVERY_PENDING'):
                    warnings.append('discovery');print('::warning::Office discovery has pending work.',flush=True)
                elif process.returncode==0 and report['status'] not in ('success','skipped'):results['discovery']=1
            except (ValueError,TypeError,IndexError,AttributeError):
                results['discovery']=1;print('OFFICE_DISCOVERY_TRIGGER_RESULT_INVALID',flush=True)
        except OSError:results['discovery']=1;print('OFFICE_DISCOVERY_TRIGGER_START_FAILED',flush=True)
    else:print('Office discovery: skipped (not configured).',flush=True)
    success=all(code==0 or name in warnings for name,code in results.items())
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a',encoding='utf-8') as report:
            report.write('## Public maintenance results\n\n| Stage | Result |\n| --- | --- |\n')
            for name,code in results.items():
                label='warning (partial)' if name in warnings else 'success' if code==0 else 'failure'
                report.write(f'| {name} | {label} |\n')
            if discovery_report:
                report.write('\nDiscovery: '+', '.join(f'{key}: {discovery_report[key]}' for key in ('scanned','discovered','published','rejected','pending') if key in discovery_report)+'\n')
            else:report.write('\nDiscovery: not configured or no valid result.\n')
            report.write('\nOffice refresh rereads known URLs. The separate discovery stage finds new URLs only when configured.\n')
    print(json.dumps({'status':'success' if success else 'partial','stage_results':results,'warnings':warnings}),flush=True)
    return 0 if success else 1


if __name__=='__main__':raise SystemExit(main())
